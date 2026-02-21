#!/usr/bin/env python3
"""Download OHLCV data for pairs from a whitelist file with warmup extension."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path("/Users/carlaherrera/Desktop/codex/freqtrade")
DEFAULT_CONFIG = REPO_ROOT / "config.json"
DATA_ROOT = REPO_ROOT / "user_data" / "data"


def timeframe_to_minutes(tf: str) -> int:
    unit = tf[-1].lower()
    n = int(tf[:-1])
    mult = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    if unit not in mult:
        raise ValueError(f"Unsupported timeframe: {tf}")
    return n * mult[unit]


def extend_timerange(timerange: str, min_tf: str, warmup_candles: int) -> str:
    start_s, end_s = timerange.split("-")
    start = datetime.strptime(start_s, "%Y%m%d")
    extra = timedelta(minutes=timeframe_to_minutes(min_tf) * warmup_candles)
    return f"{(start-extra).strftime('%Y%m%d')}-{end_s}"


def load_whitelist(path: Path) -> tuple[str, str, list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    pairs = payload.get("pair_whitelist", [])
    if not pairs:
        raise ValueError(f"No pair_whitelist in {path}")
    exchange = payload.get("exchange", "binance")
    market = payload.get("market", "spot")
    return exchange, market, pairs


def run(cmd: list[str]) -> None:
    print("\n$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def pair_to_stem(pair: str) -> str:
    # Futures pair format may include margin suffix, e.g. BTC/USDT:USDT.
    normalized = pair.split(":", 1)[0]
    return normalized.replace("/", "_")


def verify_files(exchange: str, pairs: list[str], timeframes: list[str], market: str) -> tuple[list[str], list[str]]:
    exchange_dir = DATA_ROOT / exchange
    found: list[str] = []
    missing: list[str] = []
    for pair in pairs:
        stem = pair_to_stem(pair)
        for tf in timeframes:
            if market == "futures":
                # Futures ohlcv is stored under <exchange>/futures/ with explicit candle type suffix.
                fut_stem = f"{stem}_USDT" if ":" in pair else stem
                fpath = exchange_dir / "futures" / f"{fut_stem}-{tf}-futures.feather"
            else:
                fpath = exchange_dir / f"{stem}-{tf}.feather"
            if fpath.exists():
                found.append(str(fpath))
            else:
                missing.append(str(fpath))
    return found, missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Download data from conservative liquid whitelist")
    parser.add_argument("--whitelist-file", required=True)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--exchange", default="")
    parser.add_argument("--market", choices=["spot", "futures"], default="")
    parser.add_argument("--timerange", required=True, help="YYYYMMDD-YYYYMMDD")
    parser.add_argument("--timeframes", default="1m,3m,5m,1h,1d")
    parser.add_argument("--warmup-candles", type=int, default=600)
    parser.add_argument("--prepend", action="store_true", default=True)
    args = parser.parse_args()

    whitelist_file = Path(args.whitelist_file)
    cfg_exchange, cfg_market, pairs = load_whitelist(whitelist_file)

    exchange = args.exchange or cfg_exchange
    market = args.market or cfg_market

    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    if not timeframes:
        raise ValueError("No timeframes provided")

    min_tf = min(timeframes, key=timeframe_to_minutes)
    extended = extend_timerange(args.timerange, min_tf, args.warmup_candles)

    print(f"Whitelist: {whitelist_file}")
    print(f"Exchange: {exchange} | Market: {market}")
    print(f"Pairs: {len(pairs)}")
    print(f"Timeframes: {timeframes}")
    print(f"Timerange: {args.timerange} -> extended: {extended}")

    cmd = [
        "freqtrade",
        "download-data",
        "--config",
        args.config,
        "--exchange",
        exchange,
        "--trading-mode",
        market,
        "--timeframes",
        *timeframes,
        "--timerange",
        extended,
        "--pairs",
        *pairs,
    ]
    if args.prepend:
        cmd.append("--prepend")

    run(cmd)

    found, missing = verify_files(exchange, pairs, timeframes, market)
    print(f"\nDownloaded/available files: {len(found)}")
    print(f"Missing files: {len(missing)}")
    if missing:
        print("Missing sample:")
        for row in missing[:20]:
            print(f"- {row}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
