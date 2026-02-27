#!/usr/bin/env python3
"""Rank pairs by momentum (ROC) and write a rotation whitelist JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def pair_from_filename(path: Path, timeframe: str) -> str:
    base = path.name.replace(f"-{timeframe}.feather", "")
    return base.replace("_", "/")


def compute_roc(path: Path, lookback: int) -> float | None:
    try:
        df = pd.read_feather(path)
    except Exception:
        return None

    if "close" not in df.columns or len(df) <= lookback:
        return None

    end = float(df["close"].iloc[-1])
    start = float(df["close"].iloc[-(lookback + 1)])
    if start <= 0:
        return None

    return (end / start) - 1.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate top-N momentum whitelist from local data")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--lookback", type=int, default=28)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--quote", default="USDT")
    parser.add_argument(
        "--data-root",
        default="/Users/carlaherrera/Desktop/codex/freqtrade/user_data/data",
        help="Base data directory (contains exchange subfolders)",
    )
    parser.add_argument(
        "--output",
        default="/Users/carlaherrera/Desktop/codex/freqtrade/user_data/whitelists/rotation_top10.json",
    )
    args = parser.parse_args()

    exchange_dir = Path(args.data_root) / args.exchange
    pattern = f"*-{args.timeframe}.feather"
    files = sorted(exchange_dir.glob(pattern))

    if not files:
        raise SystemExit(f"No data files found in {exchange_dir} for timeframe {args.timeframe}")

    ranked: list[tuple[str, float]] = []
    for fpath in files:
        pair = pair_from_filename(fpath, args.timeframe)
        if not pair.endswith(f"/{args.quote}"):
            continue

        roc = compute_roc(fpath, args.lookback)
        if roc is None:
            continue

        ranked.append((pair, roc))

    ranked.sort(key=lambda x: x[1], reverse=True)
    selected = [pair for pair, _ in ranked[: args.top]]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_by": "rotation_select.py",
        "exchange": args.exchange,
        "timeframe": args.timeframe,
        "lookback": args.lookback,
        "top": args.top,
        "pair_whitelist": selected,
        "ranking": [{"pair": p, "roc": r} for p, r in ranked[: args.top]],
    }

    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote whitelist: {output_path}")
    for idx, item in enumerate(payload["ranking"], 1):
        print(f"{idx:02d}. {item['pair']} roc={item['roc']:.4f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
