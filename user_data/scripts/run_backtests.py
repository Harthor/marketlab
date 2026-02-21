#!/usr/bin/env python3
"""Interactive/CLI backtest runner for strategy pack."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from freqtrade.data.btanalysis.bt_fileutils import get_latest_backtest_filename, load_backtest_stats


REPO_ROOT = Path("/Users/carlaherrera/Desktop/codex/freqtrade")
CONFIG_PATH = REPO_ROOT / "config.json"
USER_DATA = REPO_ROOT / "user_data"
RESULTS_ROOT = USER_DATA / "backtest_results"
WHITELIST_PATH = USER_DATA / "whitelists" / "rotation_top10.json"
ROTATION_SELECTOR = USER_DATA / "scripts" / "rotation_select.py"


@dataclass(frozen=True)
class StrategySpec:
    name: str
    informative_tfs: tuple[str, ...] = ()
    requires_external: bool = False
    supports_rotation_whitelist: bool = False


STRATEGIES = [
    StrategySpec("Strat01RegimeMACross", informative_tfs=("1d",)),
    StrategySpec("Strat02DonchianTurtle"),
    StrategySpec("Strat03RSIBBMeanReversion"),
    StrategySpec("Strat04FundingCarryFutures", requires_external=True),
    StrategySpec("Strat05MomentumRotation", informative_tfs=("1d",), supports_rotation_whitelist=True),
]


def run(cmd: list[str]) -> None:
    print("\n$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def timeframe_to_minutes(tf: str) -> int:
    unit = tf[-1].lower()
    n = int(tf[:-1])
    mult = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    if unit not in mult:
        raise ValueError(f"Unsupported timeframe: {tf}")
    return n * mult[unit]


def extend_start(timerange: str, timeframe: str, candles: int = 400) -> str:
    start_s, end_s = timerange.split("-")
    start = datetime.strptime(start_s, "%Y%m%d")
    shift = timedelta(minutes=timeframe_to_minutes(timeframe) * candles)
    extended = start - shift
    return f"{extended.strftime('%Y%m%d')}-{end_s}"


def parse_selection(raw: str, total: int) -> list[int]:
    raw = raw.strip().lower()
    if raw == "all":
        return list(range(1, total + 1))

    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        i = int(part)
        if i < 1 or i > total:
            raise ValueError(f"Invalid selection index: {i}")
        out.append(i)

    if not out:
        raise ValueError("No strategies selected")
    return sorted(set(out))


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def load_base_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_whitelist_file(path: Path) -> tuple[str, str, list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    pairs = payload.get("pair_whitelist", [])
    if not pairs:
        raise ValueError(f"Whitelist file has no pair_whitelist: {path}")
    exchange = payload.get("exchange", "binance")
    market = payload.get("market", "spot")
    return exchange, market, pairs


def apply_rotation_whitelist(config: dict, exchange: str) -> tuple[dict, list[str]]:
    if not WHITELIST_PATH.exists():
        raise FileNotFoundError(
            f"Missing whitelist file {WHITELIST_PATH}. Run rotation selector first."
        )

    payload = json.loads(WHITELIST_PATH.read_text(encoding="utf-8"))
    whitelist = payload.get("pair_whitelist", [])
    if not whitelist:
        raise ValueError(f"Whitelist file {WHITELIST_PATH} has no pairs")

    config.setdefault("exchange", {})
    config["exchange"]["name"] = exchange
    config["exchange"]["pair_whitelist"] = whitelist
    config["pairlists"] = [{"method": "StaticPairList"}]
    return config, whitelist


def download_data(
    config_path: Path,
    exchange: str,
    market: str,
    pairs: list[str],
    timerange: str,
    timeframes: Iterable[str],
) -> None:
    tfs = sorted(set(timeframes), key=timeframe_to_minutes)
    ext_range = extend_start(timerange, tfs[0], candles=400)

    cmd = [
        "freqtrade",
        "download-data",
        "--config",
        str(config_path),
        "--exchange",
        exchange,
        "--trading-mode",
        market,
        "--timeframes",
        *tfs,
        "--timerange",
        ext_range,
        "--prepend",
    ]

    if pairs:
        cmd += ["--pairs", *pairs]

    run(cmd)


def summarize_result(result_dir: Path, strategy_name: str) -> dict:
    latest = get_latest_backtest_filename(result_dir)
    stats = load_backtest_stats(result_dir / latest)
    data = stats["strategy"][strategy_name]
    return {
        "profit_pct": round(data.get("profit_total", 0.0) * 100, 3),
        "drawdown_pct": round(data.get("max_drawdown_account", 0.0) * 100, 3),
        "winrate_pct": round(data.get("winrate", 0.0) * 100, 3),
        "trades": int(data.get("total_trades", 0)),
        "trades_per_day": round(float(data.get("trades_per_day", 0.0)), 3),
        "expectancy": round(float(data.get("expectancy", 0.0)), 6),
        "profit_factor": data.get("profit_factor", None),
    }


def choose_strategies(selector: str) -> list[StrategySpec]:
    keymap = {s.name.lower(): s for s in STRATEGIES}
    if selector.lower() == "all":
        return STRATEGIES

    if all(part.strip().isdigit() for part in selector.split(",") if part.strip()):
        idx = parse_selection(selector, len(STRATEGIES))
        return [STRATEGIES[i - 1] for i in idx]

    selected: list[StrategySpec] = []
    for raw in selector.split(","):
        k = raw.strip().lower()
        if not k:
            continue
        if k not in keymap:
            raise ValueError(f"Unknown strategy: {raw}")
        selected.append(keymap[k])

    if not selected:
        raise ValueError("No strategies selected")
    return selected


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run strategy backtests with auto-download")
    p.add_argument("--strategies", default="", help="all | '1,2' | 'NameA,NameB'")
    p.add_argument("--timeframe", default="")
    p.add_argument("--timerange", default="", help="YYYYMMDD-YYYYMMDD")
    p.add_argument("--exchange", default="")
    p.add_argument("--market", choices=["spot", "futures"], default="")
    p.add_argument("--pairs", default="", help="Comma-separated pair list")
    p.add_argument("--whitelist-file", default="", help="Path to whitelist json with pair_whitelist")
    p.add_argument("--non-interactive", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()

    print("Detected strategies:")
    for idx, spec in enumerate(STRATEGIES, 1):
        note = " (live/external only)" if spec.requires_external else ""
        print(f"  {idx}. {spec.name}{note}")

    if args.non_interactive:
        selected_raw = args.strategies or "all"
        timeframe = args.timeframe or "4h"
        timerange = args.timerange or "20250101-20260101"
        exchange = args.exchange or "binance"
        market = args.market or "spot"
        pairs_raw = args.pairs
    else:
        selected_raw = args.strategies or ask("Select strategy numbers (comma), names, or 'all'", "all")
        timeframe = args.timeframe or ask("Timeframe", "4h")
        timerange = args.timerange or ask("Timerange (YYYYMMDD-YYYYMMDD)", "20250101-20260101")
        exchange = args.exchange or ask("Exchange", "binance")
        market = args.market or ask("Market (spot/futures)", "spot")
        pairs_raw = args.pairs or ask("Pairs comma separated (empty = config/selector)", "")

    selected = choose_strategies(selected_raw)
    pairs = [p.strip() for p in pairs_raw.split(",") if p.strip()]

    whitelist_pairs: list[str] = []
    whitelist_file = Path(args.whitelist_file) if args.whitelist_file else None
    if whitelist_file:
        wl_exchange, wl_market, whitelist_pairs = load_whitelist_file(whitelist_file)
        if not args.exchange:
            exchange = wl_exchange
        if not args.market:
            market = wl_market
        print(f"Using whitelist-file: {whitelist_file} ({len(whitelist_pairs)} pairs)")

    now_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_rows: list[tuple[str, dict | str]] = []

    for spec in selected:
        print(f"\n=== {spec.name} ===")

        if spec.requires_external:
            msg = "SKIPPED: requires external funding-rate source (live-only workflow)."
            print(msg)
            summary_rows.append((spec.name, msg))
            continue

        strategy_dir = RESULTS_ROOT / now_tag / spec.name
        strategy_dir.mkdir(parents=True, exist_ok=True)

        cfg = load_base_config()
        cfg["strategy"] = spec.name
        cfg["timeframe"] = timeframe
        cfg.setdefault("exchange", {})
        cfg["exchange"]["name"] = exchange
        cfg["trading_mode"] = market
        if market == "futures":
            cfg["margin_mode"] = cfg.get("margin_mode", "isolated")

        effective_pairs = list(pairs)

        if whitelist_pairs:
            effective_pairs = list(whitelist_pairs)
            cfg["exchange"]["pair_whitelist"] = effective_pairs
            cfg["pairlists"] = [{"method": "StaticPairList"}]
        elif not effective_pairs:
            effective_pairs = list(cfg.get("exchange", {}).get("pair_whitelist", []))

        required_tfs = {timeframe, *spec.informative_tfs}

        config_copy = strategy_dir / "config.runtime.json"
        config_copy.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

        download_data(config_copy, exchange, market, effective_pairs, timerange, required_tfs)

        if spec.supports_rotation_whitelist and not whitelist_pairs:
            selector_cmd = [
                "python",
                str(ROTATION_SELECTOR),
                "--exchange",
                exchange,
                "--timeframe",
                "1d",
                "--lookback",
                "28",
                "--top",
                "10",
            ]
            run(selector_cmd)
            cfg, rotated_pairs = apply_rotation_whitelist(cfg, exchange)
            effective_pairs = rotated_pairs
            print(f"Rotation whitelist pairs: {len(rotated_pairs)}")
            config_copy.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

        bt_cmd = [
            "freqtrade",
            "backtesting",
            "--config",
            str(config_copy),
            "--strategy",
            spec.name,
            "--timeframe",
            timeframe,
            "--timerange",
            timerange,
            "--backtest-directory",
            str(strategy_dir),
        ]
        if effective_pairs:
            bt_cmd += ["--pairs", *effective_pairs]

        run(bt_cmd)

        stats = summarize_result(strategy_dir, spec.name)
        summary_rows.append((spec.name, stats))

    print("\n=== Summary ===")
    for name, result in summary_rows:
        if isinstance(result, str):
            print(f"- {name}: {result}")
            continue

        pf = result["profit_factor"]
        pf_text = f"{pf:.3f}" if isinstance(pf, (float, int)) else "n/a"
        print(
            f"- {name}: profit={result['profit_pct']:.3f}% | "
            f"drawdown={result['drawdown_pct']:.3f}% | "
            f"winrate={result['winrate_pct']:.2f}% | "
            f"trades={result['trades']} | "
            f"trades/day={result['trades_per_day']} | "
            f"expectancy={result['expectancy']} | "
            f"profit_factor={pf_text}"
        )

    print(f"\nResults written under: {RESULTS_ROOT / now_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
