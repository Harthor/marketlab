#!/usr/bin/env python3
"""Build conservative high-liquidity pair whitelists for spot/futures."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

SPOT_URL = "https://api.binance.com/api/v3/ticker/24hr"
FUTURES_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"

LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
EXCLUDED_BASES = {
    "USDT",
    "USDC",
    "BUSD",
    "FDUSD",
    "TUSD",
    "USDP",
    "DAI",
    "EUR",
    "TRY",
    "BRL",
    "GBP",
    "RUB",
    "UAH",
    "IDRT",
    "BIDR",
    "AUD",
    "NGN",
    "ZAR",
}


REPO_ROOT = Path("/Users/carlaherrera/Desktop/codex/freqtrade")
DEFAULT_OUT_DIR = REPO_ROOT / "user_data" / "whitelists"


def fetch_json(url: str) -> list[dict]:
    with urlopen(url, timeout=20) as resp:
        return json.load(resp)


def symbol_to_pair(symbol: str) -> tuple[str, str] | None:
    if not symbol.endswith("USDT"):
        return None
    base = symbol[:-4]
    if not base:
        return None
    return base, f"{base}/USDT"


def is_excluded_base(base: str) -> bool:
    if base in EXCLUDED_BASES:
        return True
    return base.endswith(LEVERAGED_SUFFIXES)


def select_pairs(
    rows: list[dict],
    top: int,
    min_count: int,
    min_quote_volume: float,
    max_abs_change_pct: float,
    weight_volume: float,
    weight_count: float,
) -> tuple[list[str], list[dict], dict]:
    candidates: list[dict] = []

    for row in rows:
        symbol = row.get("symbol", "")
        pair_info = symbol_to_pair(symbol)
        if not pair_info:
            continue

        base, pair = pair_info
        if is_excluded_base(base):
            continue

        quote_volume = float(row.get("quoteVolume") or 0.0)
        count = int(row.get("count") or 0)
        change_pct = float(row.get("priceChangePercent") or 0.0)

        if quote_volume < min_quote_volume:
            continue
        if count < min_count:
            continue
        if abs(change_pct) > max_abs_change_pct:
            continue

        score = (weight_volume * math.log10(quote_volume + 1.0)) + (
            weight_count * math.log10(float(count) + 1.0)
        )

        candidates.append(
            {
                "symbol": symbol,
                "pair": pair,
                "base": base,
                "quote_volume": quote_volume,
                "trade_count": count,
                "price_change_percent": change_pct,
                "score": score,
            }
        )

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_rows = candidates[:top]
    top_pairs = [r["pair"] for r in top_rows]

    stats = {
        "total_rows": len(rows),
        "eligible_rows": len(candidates),
        "selected_rows": len(top_rows),
    }
    return top_pairs, top_rows, stats


def write_whitelist(
    out_path: Path,
    exchange: str,
    market: str,
    top_pairs: list[str],
    ranking: list[dict],
    filters: dict,
    stats: dict,
) -> None:
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_by": "build_liquid_pairs.py",
        "exchange": exchange,
        "market": market,
        "pair_whitelist": top_pairs,
        "filters": filters,
        "stats": stats,
        "ranking": ranking,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build conservative liquid pair whitelists")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--min-count", type=int, default=100000)
    parser.add_argument("--min-quote-volume", type=float, default=10_000_000.0)
    parser.add_argument("--max-abs-change-pct", type=float, default=20.0)
    parser.add_argument("--weight-volume", type=float, default=0.65)
    parser.add_argument("--weight-count", type=float, default=0.35)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    filters = {
        "top": args.top,
        "min_count": args.min_count,
        "min_quote_volume": args.min_quote_volume,
        "max_abs_change_pct": args.max_abs_change_pct,
        "weight_volume": args.weight_volume,
        "weight_count": args.weight_count,
        "excluded_bases": sorted(EXCLUDED_BASES),
        "excluded_suffixes": list(LEVERAGED_SUFFIXES),
    }

    spot_rows = fetch_json(SPOT_URL)
    spot_pairs, spot_rank, spot_stats = select_pairs(
        spot_rows,
        top=args.top,
        min_count=args.min_count,
        min_quote_volume=args.min_quote_volume,
        max_abs_change_pct=args.max_abs_change_pct,
        weight_volume=args.weight_volume,
        weight_count=args.weight_count,
    )
    spot_file = out_dir / "liquid_spot_top20.json"
    write_whitelist(
        spot_file,
        exchange=args.exchange,
        market="spot",
        top_pairs=spot_pairs,
        ranking=spot_rank,
        filters=filters,
        stats=spot_stats,
    )

    futures_rows = fetch_json(FUTURES_URL)
    futures_pairs, futures_rank, futures_stats = select_pairs(
        futures_rows,
        top=args.top,
        min_count=args.min_count,
        min_quote_volume=args.min_quote_volume,
        max_abs_change_pct=args.max_abs_change_pct,
        weight_volume=args.weight_volume,
        weight_count=args.weight_count,
    )
    futures_file = out_dir / "liquid_futures_top20.json"
    write_whitelist(
        futures_file,
        exchange=args.exchange,
        market="futures",
        top_pairs=futures_pairs,
        ranking=futures_rank,
        filters=filters,
        stats=futures_stats,
    )

    print(f"Wrote: {spot_file} ({len(spot_pairs)} pairs)")
    print(f"Wrote: {futures_file} ({len(futures_pairs)} pairs)")

    print("\nTop 10 spot:")
    for i, item in enumerate(spot_rank[:10], 1):
        print(
            f"{i:02d}. {item['pair']:<12} score={item['score']:.3f} "
            f"qv={item['quote_volume']:,.0f} cnt={item['trade_count']:,} "
            f"chg={item['price_change_percent']:+.2f}%"
        )

    print("\nTop 10 futures:")
    for i, item in enumerate(futures_rank[:10], 1):
        print(
            f"{i:02d}. {item['pair']:<12} score={item['score']:.3f} "
            f"qv={item['quote_volume']:,.0f} cnt={item['trade_count']:,} "
            f"chg={item['price_change_percent']:+.2f}%"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
