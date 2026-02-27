#!/usr/bin/env python3
"""Runner for sanity and multi-pair backtests (CLI only)."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path("/Users/carlaherrera/Desktop/codex/freqtrade")
CONFIG_SPOT = REPO_ROOT / "user_data" / "configs" / "config.bt_spot.json"
CONFIG_FUT = REPO_ROOT / "user_data" / "configs" / "config.bt_futures.json"
SCRIPTS = REPO_ROOT / "user_data" / "scripts"
WHITELISTS = REPO_ROOT / "user_data" / "whitelists"


def run(cmd: list[str]) -> None:
    print("\n$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def pick_config(market: str) -> Path:
    return CONFIG_FUT if market == "futures" else CONFIG_SPOT


def ensure_data(
    config: Path,
    timerange: str,
    market: str,
    timeframes: list[str],
    informative_timeframes: list[str],
) -> None:
    cmd = [
        "python",
        str(SCRIPTS / "ensure_data.py"),
        "--config",
        str(config),
        "--timerange",
        timerange,
        "--market",
        market,
        "--timeframes",
        ",".join(timeframes),
    ]
    if informative_timeframes:
        cmd += ["--informative-timeframes", ",".join(informative_timeframes)]
    run(cmd)


def run_backtest(config: Path, strategy: str, timerange: str, timeframe: str | None = None) -> None:
    cmd = [
        "freqtrade",
        "backtesting",
        "-c",
        str(config),
        "-s",
        strategy,
        "--timerange",
        timerange,
    ]
    if timeframe:
        cmd += ["--timeframe", timeframe]
    run(cmd)


def build_temp_config(base_config: Path, whitelist_json: Path) -> Path:
    cfg = json.loads(base_config.read_text(encoding="utf-8"))
    wl = json.loads(whitelist_json.read_text(encoding="utf-8"))
    pairs = wl.get("pair_whitelist", [])
    if not pairs:
        raise ValueError(f"Whitelist has no pairs: {whitelist_json}")

    cfg.setdefault("exchange", {})
    cfg["exchange"]["pair_whitelist"] = pairs
    cfg["pairlists"] = [{"method": "StaticPairList"}]

    out = REPO_ROOT / "user_data" / "configs" / f"config.bt.temp.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"Temp config: {out}")
    return out


def cmd_sanity(args: argparse.Namespace) -> int:
    config = pick_config(args.market)
    ensure_data(
        config=config,
        timerange=args.timerange,
        market=args.market,
        timeframes=[args.timeframe],
        informative_timeframes=args.informative_timeframes,
    )
    run_backtest(config=config, strategy=args.strategy, timerange=args.timerange, timeframe=args.timeframe)
    return 0


def cmd_multi(args: argparse.Namespace) -> int:
    base_config = pick_config(args.market)
    whitelist_out = Path(args.out or (WHITELISTS / "whitelist.selected.json"))

    run(
        [
            "python",
            str(SCRIPTS / "select_pairs.py"),
            "--market",
            args.market,
            "--timeframe",
            args.timeframe,
            "--lookback-days",
            str(args.lookback_days),
            "--top-n",
            str(args.top_n),
            "--min-age-days",
            str(args.min_age_days),
            "--out",
            str(whitelist_out),
        ]
    )

    temp_config = build_temp_config(base_config, whitelist_out)

    ensure_data(
        config=temp_config,
        timerange=args.timerange,
        market=args.market,
        timeframes=[args.timeframe],
        informative_timeframes=args.informative_timeframes,
    )

    run_backtest(
        config=temp_config,
        strategy=args.strategy,
        timerange=args.timerange,
        timeframe=args.timeframe,
    )
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Backtest runner (sanity + multi-pair)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("sanity", help="Run sanity backtest on SAFE 5-pair config")
    ps.add_argument("--market", choices=["spot", "futures"], default="spot")
    ps.add_argument("--strategy", required=True)
    ps.add_argument("--timerange", required=True)
    ps.add_argument("--timeframe", default="5m")
    ps.add_argument("--informative-timeframes", default="1d", type=lambda s: [x for x in s.split(",") if x])
    ps.set_defaults(func=cmd_sanity)

    pm = sub.add_parser("multi", help="Select pairs and run multi-pair backtest")
    pm.add_argument("--market", choices=["spot", "futures"], default="spot")
    pm.add_argument("--strategy", required=True)
    pm.add_argument("--timerange", required=True)
    pm.add_argument("--timeframe", default="5m")
    pm.add_argument("--lookback-days", type=int, default=30)
    pm.add_argument("--top-n", type=int, default=50)
    pm.add_argument("--min-age-days", type=int, default=180)
    pm.add_argument("--out", default="")
    pm.add_argument("--informative-timeframes", default="1d", type=lambda s: [x for x in s.split(",") if x])
    pm.set_defaults(func=cmd_multi)

    return p


def main() -> int:
    args = parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
