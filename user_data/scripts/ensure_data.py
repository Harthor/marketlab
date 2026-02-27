#!/usr/bin/env python3
"""Ensure ohlcv data exists for pairs/timeframes/timerange (with warmup margin)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path("/Users/carlaherrera/Desktop/codex/freqtrade")
DATA_ROOT = REPO_ROOT / "user_data" / "data"
FREQTRADE_BIN = REPO_ROOT / ".env" / "bin" / "freqtrade"


def tf_to_minutes(tf: str) -> int:
    unit = tf[-1].lower()
    val = int(tf[:-1])
    mul = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    if unit not in mul:
        raise ValueError(f"Unsupported timeframe: {tf}")
    return val * mul[unit]


def extend_timerange(timerange: str, min_tf: str, warmup_candles: int) -> str:
    start_s, end_s = timerange.split("-")
    start = datetime.strptime(start_s, "%Y%m%d")
    delta = timedelta(minutes=tf_to_minutes(min_tf) * warmup_candles)
    return f"{(start-delta).strftime('%Y%m%d')}-{end_s}"


def pair_to_stem(pair: str, market: str) -> str:
    if market == "futures":
        base = pair.split(":", 1)[0].replace("/", "_")
        return f"{base}_USDT"
    return pair.replace("/", "_")


def read_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_timerange(timerange: str) -> tuple[datetime, datetime]:
    start_s, end_s = timerange.split("-")
    return datetime.strptime(start_s, "%Y%m%d"), datetime.strptime(end_s, "%Y%m%d")


def data_file_path(exchange: str, market: str, pair: str, tf: str) -> Path:
    base = DATA_ROOT / exchange
    stem = pair_to_stem(pair, market)
    if market == "futures":
        return base / "futures" / f"{stem}-{tf}-futures.feather"
    return base / f"{stem}-{tf}.feather"


def timeframe_delta(tf: str) -> timedelta:
    return timedelta(minutes=tf_to_minutes(tf))


def load_date_bounds(path: Path) -> tuple[datetime | None, datetime | None]:
    if not path.exists():
        return None, None
    try:
        df = pd.read_feather(path, columns=["date"])
        if df.empty:
            return None, None
        dates = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
        return dates.min().to_pydatetime(), dates.max().to_pydatetime()
    except Exception:
        return None, None


def evaluate_pair_data_coverage(
    exchange: str,
    market: str,
    pair: str,
    timeframes: list[str],
    start_dt: datetime,
    end_dt: datetime,
    require_full_range: bool,
) -> dict[str, Any]:
    reasons: list[str] = []
    details: dict[str, Any] = {}

    for tf in timeframes:
        fp = data_file_path(exchange, market, pair, tf)
        if not fp.exists():
            reasons.append(f"missing_file:{tf}")
            details[tf] = {"file": str(fp), "status": "missing_file"}
            continue

        min_dt, max_dt = load_date_bounds(fp)
        if min_dt is None or max_dt is None:
            reasons.append(f"unreadable_or_empty:{tf}")
            details[tf] = {"file": str(fp), "status": "unreadable_or_empty"}
            continue

        if require_full_range:
            tf_delta = timeframe_delta(tf)
            if min_dt > start_dt:
                reasons.append(f"late_start:{tf}:{min_dt.strftime('%Y-%m-%d %H:%M')}")
            if max_dt < (end_dt - tf_delta):
                reasons.append(f"early_end:{tf}:{max_dt.strftime('%Y-%m-%d %H:%M')}")

        details[tf] = {
            "file": str(fp),
            "status": "ok" if tf not in "".join(reasons) else "insufficient_range",
            "min_date": min_dt.isoformat(),
            "max_date": max_dt.isoformat(),
        }

    return {"pair": pair, "ok": len(reasons) == 0, "reasons": reasons, "details": details}


def list_missing(exchange: str, market: str, pairs: list[str], timeframes: list[str]) -> list[Path]:
    missing: list[Path] = []
    for pair in pairs:
        for tf in timeframes:
            fp = data_file_path(exchange, market, pair, tf)
            if not fp.exists():
                missing.append(fp)
    return missing


def run(cmd: list[str]) -> None:
    print("\n$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def freqtrade_cmd() -> str:
    if FREQTRADE_BIN.exists():
        return str(FREQTRADE_BIN)
    found = shutil.which("freqtrade")
    if found:
        return found
    raise FileNotFoundError("freqtrade executable not found. Activate venv or ensure .env/bin/freqtrade exists.")


def main() -> int:
    p = argparse.ArgumentParser(description="Ensure required OHLCV data is present")
    p.add_argument("--config", required=True)
    p.add_argument("--timerange", required=True)
    p.add_argument("--market", choices=["spot", "futures"], default="")
    p.add_argument("--pairs", default="", help="Comma separated pairs (override config)")
    p.add_argument("--timeframes", default="", help="Comma separated timeframes")
    p.add_argument("--informative-timeframes", default="", help="Extra informative timeframes")
    p.add_argument("--warmup-candles", type=int, default=400)
    p.add_argument("--exchange", default="")
    p.add_argument("--effective-whitelist-out", default="", help="Optional output whitelist with only pairs having required data")
    p.add_argument("--effective-report-out", default="", help="Optional JSON report with pair data coverage and exclusion reasons")
    p.add_argument("--require-full-range", action="store_true", default=False, help="Require data coverage across full extended timerange")
    p.add_argument(
        "--no-download",
        action="store_true",
        default=False,
        help="Skip freqtrade download-data step and only evaluate local coverage.",
    )
    args = p.parse_args()

    cfg = read_config(Path(args.config))
    exchange = args.exchange or cfg.get("exchange", {}).get("name", "binance")
    market = args.market or cfg.get("trading_mode", "spot")

    pairs = [x.strip() for x in args.pairs.split(",") if x.strip()]
    if not pairs:
        pairs = cfg.get("exchange", {}).get("pair_whitelist", [])

    if not pairs:
        raise SystemExit("No pairs configured. Pass --pairs or set exchange.pair_whitelist.")

    timeframes = [x.strip() for x in args.timeframes.split(",") if x.strip()]
    if not timeframes:
        timeframes = [cfg.get("timeframe", "5m")]

    informative = [x.strip() for x in args.informative_timeframes.split(",") if x.strip()]
    all_tfs = sorted(set(timeframes + informative), key=tf_to_minutes)

    extended = extend_timerange(args.timerange, min(all_tfs, key=tf_to_minutes), args.warmup_candles)

    print(f"Config: {args.config}")
    print(f"Exchange: {exchange} | Market: {market}")
    print(f"Pairs: {len(pairs)} | Timeframes: {all_tfs}")
    print(f"Timerange: {args.timerange} -> extended: {extended}")

    missing_before = list_missing(exchange, market, pairs, all_tfs)
    print(f"Missing files before download: {len(missing_before)}")

    if args.no_download:
        print("Skipping download-data step (--no-download enabled).")
    else:
        cmd = [
            freqtrade_cmd(),
            "download-data",
            "--config",
            args.config,
            "--exchange",
            exchange,
            "--trading-mode",
            market,
            "--timeframes",
            *all_tfs,
            "--timerange",
            extended,
            "--prepend",
            "--pairs",
            *pairs,
        ]
        run(cmd)

    missing_after = list_missing(exchange, market, pairs, all_tfs)
    print(f"Missing files after download: {len(missing_after)}")
    if missing_after:
        for fp in missing_after[:20]:
            print(f"- {fp}")

    if args.effective_whitelist_out or args.effective_report_out:
        start_dt, end_dt = parse_timerange(extended)
        coverage_rows = [
            evaluate_pair_data_coverage(
                exchange=exchange,
                market=market,
                pair=pair,
                timeframes=all_tfs,
                start_dt=start_dt,
                end_dt=end_dt,
                require_full_range=args.require_full_range,
            )
            for pair in pairs
        ]
        effective_pairs = [row["pair"] for row in coverage_rows if row["ok"]]
        excluded = [row for row in coverage_rows if not row["ok"]]
        print(f"Effective whitelist size: {len(effective_pairs)} / {len(pairs)}")

        if args.effective_whitelist_out:
            wl_path = Path(args.effective_whitelist_out)
            if not wl_path.is_absolute():
                wl_path = (REPO_ROOT / wl_path).resolve()
            wl_path.parent.mkdir(parents=True, exist_ok=True)
            wl_payload = {
                "generated_at_utc": datetime.utcnow().isoformat() + "Z",
                "generated_by": "ensure_data.py",
                "exchange": exchange,
                "market": market,
                "timerange_requested": args.timerange,
                "timerange_checked": extended,
                "timeframes": all_tfs,
                "require_full_range": bool(args.require_full_range),
                "pair_whitelist": effective_pairs,
                "excluded_count": len(excluded),
            }
            wl_path.write_text(json.dumps(wl_payload, indent=2) + "\n", encoding="utf-8")
            print(f"Effective whitelist written: {wl_path}")

        if args.effective_report_out:
            report_path = Path(args.effective_report_out)
            if not report_path.is_absolute():
                report_path = (REPO_ROOT / report_path).resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_payload = {
                "generated_at_utc": datetime.utcnow().isoformat() + "Z",
                "exchange": exchange,
                "market": market,
                "timerange_requested": args.timerange,
                "timerange_checked": extended,
                "timeframes": all_tfs,
                "require_full_range": bool(args.require_full_range),
                "pairs_total": len(pairs),
                "pairs_effective": len(effective_pairs),
                "pairs_excluded": excluded,
            }
            report_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")
            print(f"Effective data report written: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
