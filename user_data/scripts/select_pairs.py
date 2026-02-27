#!/usr/bin/env python3
"""Select tradable pairs by volume/volatility/quality scoring for backtesting."""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import ccxt
import numpy as np
import pandas as pd


REPO_ROOT = Path("/Users/carlaherrera/Desktop/codex/freqtrade")
WHITELISTS_DIR = REPO_ROOT / "user_data" / "whitelists"
PROFILES = (
    "universal",
    "mean_reversion_1h",
    "mean_reversion_2h",
    "mean_reversion_3h",
    "mean_reversion_4h",
)
EXCLUDED_BASES = {
    "USDT",
    "USDC",
    "BUSD",
    "FDUSD",
    "TUSD",
    "USDP",
    "DAI",
    "PYUSD",
    "USDE",
    "EUR",
    "EURC",
}
EXCLUDED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


def tf_to_minutes(tf: str) -> int:
    unit = tf[-1].lower()
    val = int(tf[:-1])
    mul = {"m": 1, "h": 60, "d": 1440}
    if unit not in mul:
        raise ValueError(f"Unsupported timeframe: {tf}")
    return val * mul[unit]


def build_exchange(market: str) -> ccxt.Exchange:
    if market == "futures":
        return ccxt.binanceusdm({"enableRateLimit": True})
    return ccxt.binance({"enableRateLimit": True})


def normalize_symbol(symbol: str, market: str) -> str:
    if market == "futures":
        return symbol if ":USDT" in symbol else f"{symbol}:USDT"
    return symbol.split(":", 1)[0]


def base_asset(symbol: str) -> str:
    return symbol.split("/", 1)[0].upper()


def symbol_exclusion_reason(symbol: str, exclude_stables: bool, exclude_leveraged: bool) -> str | None:
    base = base_asset(symbol)
    if exclude_stables and base in EXCLUDED_BASES:
        return "excluded_stable_or_fiat_base"
    if exclude_leveraged and any(base.endswith(sfx) for sfx in EXCLUDED_SUFFIXES):
        return "excluded_leveraged_token"
    return None


def get_tickers_candidates(
    exchange: ccxt.Exchange,
    market: str,
    min_quote_volume: float,
    max_candidates: int,
    exclude_stables: bool,
    exclude_leveraged: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()

    out: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    stats = {
        "tickers_loaded": len(tickers),
        "after_market_quote_active": 0,
        "after_min_quote_volume": 0,
        "after_max_candidates": 0,
    }
    for symbol, t in tickers.items():
        m = markets.get(symbol)
        if not m or not m.get("active", True):
            continue
        if market == "spot" and not m.get("spot", False):
            continue
        if market == "futures" and not m.get("swap", False):
            continue
        if m.get("quote") != "USDT":
            continue
        stats["after_market_quote_active"] += 1

        normalized = normalize_symbol(symbol, market)
        reason = symbol_exclusion_reason(normalized, exclude_stables=exclude_stables, exclude_leveraged=exclude_leveraged)
        if reason:
            excluded.append(
                {
                    "symbol": normalized,
                    "quote_volume": float(t.get("quoteVolume") or 0.0),
                    "excluded_reason": reason,
                }
            )
            continue

        qv = float(t.get("quoteVolume") or 0.0)
        if qv < min_quote_volume:
            continue
        stats["after_min_quote_volume"] += 1

        out.append(
            {
                "symbol": normalized,
                "quote_volume": qv,
            }
        )

    out.sort(key=lambda x: x["quote_volume"], reverse=True)
    out = out[:max_candidates]
    stats["after_max_candidates"] = len(out)
    return out, excluded, stats


def fetch_ohlcv_range(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
) -> list[list[float]]:
    step_ms = tf_to_minutes(timeframe) * 60_000
    all_rows: list[list[float]] = []
    cursor = since_ms
    limit = 1000

    while cursor < until_ms:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        if not batch:
            break

        all_rows.extend(batch)
        last_ts = int(batch[-1][0])
        next_cursor = last_ts + step_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor

        if len(batch) < limit:
            break

    dedup = {}
    for r in all_rows:
        ts = int(r[0])
        if since_ms <= ts <= until_ms:
            dedup[ts] = r

    return [dedup[k] for k in sorted(dedup.keys())]


def aggregate_ohlcv(rows: list[list[float]], target_tf: str) -> list[list[float]]:
    if not rows:
        return rows
    target_ms = tf_to_minutes(target_tf) * 60_000
    buckets: dict[int, list[list[float]]] = {}
    for r in rows:
        ts = int(r[0])
        b = ts - (ts % target_ms)
        buckets.setdefault(b, []).append(r)

    out: list[list[float]] = []
    for b in sorted(buckets):
        chunk = sorted(buckets[b], key=lambda x: x[0])
        o = float(chunk[0][1])
        h = max(float(x[2]) for x in chunk)
        l = min(float(x[3]) for x in chunk)
        c = float(chunk[-1][4])
        v = float(sum(float(x[5]) for x in chunk))
        out.append([b, o, h, l, c, v])
    return out


def fetch_ohlcv_range_compatible(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
) -> list[list[float]]:
    try:
        return fetch_ohlcv_range(exchange, symbol, timeframe, since_ms, until_ms)
    except Exception as e:
        # Binance spot does not expose 3h candles in REST. Use 1h and aggregate.
        if timeframe == "3h" and "Invalid interval" in str(e):
            base_rows = fetch_ohlcv_range(exchange, symbol, "1h", since_ms, until_ms)
            return aggregate_ohlcv(base_rows, "3h")
        raise


def compute_metrics(df: pd.DataFrame, timeframe: str, days_lookback: int) -> dict:
    if df.empty:
        return {
            "atr_pct": 0.0,
            "wickiness": 1.0,
            "data_completeness": 0.0,
        }

    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean()
    atr_pct = float((atr / close).dropna().mean()) if not atr.dropna().empty else 0.0

    upper = high - df[["open", "close"]].max(axis=1)
    lower = df[["open", "close"]].min(axis=1) - low
    rng = (high - low).replace(0, np.nan)
    wickiness = ((upper + lower) / rng).fillna(0.0)
    wickiness_avg = float(wickiness.mean())

    expected = int((days_lookback * 24 * 60) / tf_to_minutes(timeframe))
    data_completeness = min(1.0, float(len(df)) / max(1, expected))

    return {
        "atr_pct": atr_pct,
        "wickiness": wickiness_avg,
        "data_completeness": data_completeness,
    }


def atr_target_score(atr_pct: float, target: float, sigma: float) -> float:
    if sigma <= 0:
        return 0.0
    z = (atr_pct - target) / sigma
    return float(math.exp(-0.5 * z * z))


def compute_reversion_friendliness(df: pd.DataFrame, horizon: int = 6) -> tuple[float, int, float]:
    if df.empty or len(df) < 40:
        return 0.0, 0, 0.0

    close = df["close"]
    bb_mid = close.rolling(20, min_periods=20).mean()
    bb_std = close.rolling(20, min_periods=20).std(ddof=0)
    bb_lower = bb_mid - (2.0 * bb_std)

    oversold = (close < bb_lower).fillna(False)
    events = 0
    successes = 0

    # event start = first oversold candle in a sequence
    prev_oversold = oversold.shift(1).fillna(False).astype(bool)
    starts = oversold & (~prev_oversold)
    idxs = list(df.index[starts])
    for idx in idxs:
        i = int(idx)
        if i + 1 >= len(df):
            continue
        events += 1
        j_end = min(len(df) - 1, i + horizon)
        reclaimed = False
        for j in range(i + 1, j_end + 1):
            if close.iat[j] >= bb_mid.iat[j]:
                reclaimed = True
                break
        if reclaimed:
            successes += 1

    if events == 0:
        return 0.0, 0, 0.0

    hit_rate = successes / events
    confidence = min(1.0, events / 12.0)
    score = float(hit_rate * confidence)
    return score, events, float(hit_rate)


def minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if math.isclose(hi, lo):
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def ranking_csv_path(out_path: Path, profile: str) -> Path:
    if profile == "universal":
        return out_path.parent / "pair_ranking.csv"
    return out_path.parent / f"pair_ranking_{profile}.csv"


def main() -> int:
    p = argparse.ArgumentParser(description="Select high-quality pairs for backtesting")
    p.add_argument("--exchange", default="binance")
    p.add_argument("--market", choices=["spot", "futures"], default="spot")
    p.add_argument("--timeframe", default="5m")
    p.add_argument("--profile", choices=PROFILES, default="universal")
    p.add_argument("--lookback-days", type=int, default=30)
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--min-age-days", type=int, default=180)
    p.add_argument("--min-quote-volume", type=float, default=10_000_000)
    p.add_argument("--max-candidates", type=int, default=150)
    p.add_argument("--exclude-stables", action="store_true", default=False)
    p.add_argument("--exclude-leveraged", action="store_true", default=False)
    p.add_argument("--atr-target", type=float, default=0.010)
    p.add_argument("--atr-sigma", type=float, default=0.006)
    p.add_argument("--reversion-horizon", type=int, default=6)
    p.add_argument("--w-volume", type=float, default=0.30)
    p.add_argument("--w-atr-target", type=float, default=0.20)
    p.add_argument("--w-cleanliness", type=float, default=0.20)
    p.add_argument("--w-reversion", type=float, default=0.20)
    p.add_argument("--w-completeness", type=float, default=0.10)
    p.add_argument(
        "--out",
        default=str(WHITELISTS_DIR / "whitelist.selected.json"),
        help="Output whitelist JSON path",
    )
    args = p.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = ranking_csv_path(out_path, args.profile)

    exchange = build_exchange(args.market)

    print(f"Loading tickers ({args.market}, profile={args.profile})...")
    candidates, excluded_rows, audit_counts = get_tickers_candidates(
        exchange,
        market=args.market,
        min_quote_volume=args.min_quote_volume,
        max_candidates=args.max_candidates,
        exclude_stables=args.exclude_stables,
        exclude_leveraged=args.exclude_leveraged,
    )
    print(
        "Selector audit: "
        f"tickers={audit_counts['tickers_loaded']} | "
        f"market_quote_active={audit_counts['after_market_quote_active']} | "
        f"after_min_quote_volume={audit_counts['after_min_quote_volume']} | "
        f"after_max_candidates={audit_counts['after_max_candidates']}"
    )

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=args.lookback_days)
    since_ms = int(since.timestamp() * 1000)
    now_ms = int(now.timestamp() * 1000)

    earliest_since = now - timedelta(days=max(args.min_age_days * 3, 365))
    earliest_since_ms = int(earliest_since.timestamp() * 1000)

    rows: list[dict[str, Any]] = []
    scored_count = 0

    for idx, cand in enumerate(candidates, 1):
        symbol = cand["symbol"]
        try:
            ohlcv = fetch_ohlcv_range_compatible(exchange, symbol, args.timeframe, since_ms, now_ms)
            if len(ohlcv) < 50:
                excluded_rows.append({"symbol": symbol, "quote_volume": cand["quote_volume"], "excluded_reason": "insufficient_ohlcv"})
                continue

            df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
            metrics = compute_metrics(df, args.timeframe, args.lookback_days)
            rev_score, rev_events, rev_hit_rate = compute_reversion_friendliness(df, horizon=args.reversion_horizon)

            # Estimate age from earliest available candle in coarse timeframe.
            age_probe = exchange.fetch_ohlcv(symbol, timeframe="1d", since=earliest_since_ms, limit=1)
            if not age_probe:
                excluded_rows.append({"symbol": symbol, "quote_volume": cand["quote_volume"], "excluded_reason": "no_1d_age_probe"})
                continue
            first_ts = int(age_probe[0][0])
            age_days = (now_ms - first_ts) / (1000 * 60 * 60 * 24)
            if age_days < args.min_age_days:
                excluded_rows.append(
                    {
                        "symbol": symbol,
                        "quote_volume": cand["quote_volume"],
                        "excluded_reason": f"age_below_min({age_days:.1f}<{args.min_age_days})",
                    }
                )
                continue

            rows.append(
                {
                    "profile": args.profile,
                    "symbol": symbol,
                    "quote_volume": cand["quote_volume"],
                    "atr_pct": metrics["atr_pct"],
                    "atr_target_score": atr_target_score(metrics["atr_pct"], args.atr_target, args.atr_sigma),
                    "wickiness": metrics["wickiness"],
                    "data_completeness": metrics["data_completeness"],
                    "reversion_score": rev_score,
                    "reversion_events": rev_events,
                    "reversion_hit_rate": rev_hit_rate,
                    "age_days": age_days,
                    "excluded_reason": "",
                }
            )
            scored_count += 1

            if idx % 10 == 0:
                print(f"Processed {idx}/{len(candidates)} candidates...")

        except Exception as e:
            print(f"WARN {symbol}: {e}")
            excluded_rows.append({"symbol": symbol, "quote_volume": cand["quote_volume"], "excluded_reason": f"fetch_error:{e}"})

    if not rows:
        raise SystemExit("No pairs survived filters. Relax thresholds.")

    vol_norm = minmax([r["quote_volume"] for r in rows])
    atr_norm = minmax([r["atr_pct"] for r in rows])
    wick_norm = minmax([r["wickiness"] for r in rows])

    w_sum = args.w_volume + args.w_atr_target + args.w_cleanliness + args.w_reversion + args.w_completeness
    if w_sum <= 0:
        raise SystemExit("Weight sum must be > 0.")
    w_volume = args.w_volume / w_sum
    w_atr_target = args.w_atr_target / w_sum
    w_cleanliness = args.w_cleanliness / w_sum
    w_reversion = args.w_reversion / w_sum
    w_completeness = args.w_completeness / w_sum

    # Profile defaults tuned per timeframe unless caller overrides explicitly.
    if args.profile == "mean_reversion_2h":
        if args.atr_target == 0.010:
            args.atr_target = 0.011
        if args.atr_sigma == 0.006:
            args.atr_sigma = 0.007
        if args.reversion_horizon == 6:
            args.reversion_horizon = 5
    elif args.profile == "mean_reversion_3h":
        if args.atr_target == 0.010:
            args.atr_target = 0.013
        if args.atr_sigma == 0.006:
            args.atr_sigma = 0.008
        if args.reversion_horizon == 6:
            args.reversion_horizon = 4
    elif args.profile == "mean_reversion_4h":
        if args.atr_target == 0.010:
            args.atr_target = 0.015
        if args.atr_sigma == 0.006:
            args.atr_sigma = 0.009
        if args.reversion_horizon == 6:
            args.reversion_horizon = 3

    for i, r in enumerate(rows):
        r["normalized_volume"] = vol_norm[i]
        r["normalized_atr_pct"] = atr_norm[i]
        r["normalized_wickiness"] = wick_norm[i]
        r["score_cleanliness"] = 1.0 - r["normalized_wickiness"]
        r["score_completeness"] = r["data_completeness"]
        if args.profile in ("mean_reversion_1h", "mean_reversion_2h", "mean_reversion_3h", "mean_reversion_4h"):
            r["score_volume"] = r["normalized_volume"]
            r["score_atr"] = r["atr_target_score"]
            r["score_reversion"] = r["reversion_score"]
            r["score"] = (
                (w_volume * r["score_volume"])
                + (w_atr_target * r["score_atr"])
                + (w_cleanliness * r["score_cleanliness"])
                + (w_reversion * r["score_reversion"])
                + (w_completeness * r["score_completeness"])
            )
        else:
            # Keep backward-compatible universal score as default behavior.
            r["score_volume"] = r["normalized_volume"]
            r["score_atr"] = r["normalized_atr_pct"]
            r["score_reversion"] = 0.0
            r["score"] = (
                r["normalized_volume"]
                * r["normalized_atr_pct"]
                * r["data_completeness"]
                * (1.0 - r["normalized_wickiness"])
            )

    rows.sort(key=lambda x: x["score"], reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    selected = rows[: args.top_n]

    if args.profile in ("mean_reversion_1h", "mean_reversion_2h", "mean_reversion_3h", "mean_reversion_4h"):
        score_formula = (
            "score = w_volume*volume_norm + w_atr_target*atr_target_score + "
            "w_cleanliness*(1-wickiness_norm) + w_reversion*reversion_score + "
            "w_completeness*data_completeness"
        )
    else:
        score_formula = "score = volume_norm * atr_norm * data_completeness * (1 - wickiness_norm)"

    payload = {
        "generated_at_utc": now.isoformat(),
        "generated_by": "select_pairs.py",
        "exchange": args.exchange,
        "market": args.market,
        "profile": args.profile,
        "timeframe": args.timeframe,
        "days_lookback": args.lookback_days,
        "min_age_days": args.min_age_days,
        "min_quote_volume": args.min_quote_volume,
        "exclude_stables": bool(args.exclude_stables),
        "exclude_leveraged": bool(args.exclude_leveraged),
        "score_formula": score_formula,
        "weights": {
            "w_volume": w_volume,
            "w_atr_target": w_atr_target,
            "w_cleanliness": w_cleanliness,
            "w_reversion": w_reversion,
            "w_completeness": w_completeness,
        },
        "atr_target": args.atr_target,
        "atr_sigma": args.atr_sigma,
        "reversion_horizon": args.reversion_horizon,
        "top_n": args.top_n,
        "audit_counts": {
            **audit_counts,
            "scored_with_metrics": scored_count,
            "excluded_rows_total": len(excluded_rows),
            "selected_top_n": min(args.top_n, len(rows)),
        },
        "pair_whitelist": [r["symbol"] for r in selected],
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "profile",
                "symbol",
                "rank",
                "score",
                "score_volume",
                "score_atr",
                "score_cleanliness",
                "score_reversion",
                "score_completeness",
                "quote_volume",
                "atr_pct",
                "atr_target_score",
                "wickiness",
                "data_completeness",
                "reversion_score",
                "reversion_events",
                "reversion_hit_rate",
                "age_days",
                "normalized_volume",
                "normalized_atr_pct",
                "normalized_wickiness",
                "excluded_reason",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        for row in excluded_rows:
            writer.writerow(
                {
                    "profile": args.profile,
                    "symbol": row.get("symbol", ""),
                    "rank": "",
                    "score": "",
                    "score_volume": "",
                    "score_atr": "",
                    "score_cleanliness": "",
                    "score_reversion": "",
                    "score_completeness": "",
                    "quote_volume": row.get("quote_volume", ""),
                    "atr_pct": "",
                    "atr_target_score": "",
                    "wickiness": "",
                    "data_completeness": "",
                    "reversion_score": "",
                    "reversion_events": "",
                    "reversion_hit_rate": "",
                    "age_days": "",
                    "normalized_volume": "",
                    "normalized_atr_pct": "",
                    "normalized_wickiness": "",
                    "excluded_reason": row.get("excluded_reason", "excluded"),
                }
            )

    print(
        "Selector final: "
        f"scored={scored_count} | selected={len(selected)} "
        f"(top_n={args.top_n} over scored={len(rows)})"
    )
    print(f"Selected pairs: {len(selected)}")
    print(f"Whitelist written: {out_path}")
    print(f"Ranking CSV written: {csv_path}")

    for i, r in enumerate(selected[:15], 1):
        print(
            f"{i:02d}. {r['symbol']:<20} score={r['score']:.4f} "
            f"vol={r['quote_volume']:,.0f} atr%={r['atr_pct']:.5f} "
            f"wick={r['wickiness']:.4f} comp={r['data_completeness']:.3f} age={r['age_days']:.1f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
