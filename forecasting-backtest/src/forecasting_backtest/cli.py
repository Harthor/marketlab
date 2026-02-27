from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

from .config import load_config, merge_cli_overrides
from .pipeline import execute_backtest_only, execute_train

try:
    from marketlab_core.contracts import TIMESTAMP_COL
except Exception:
    TIMESTAMP_COL = "ts_utc"
    warnings.warn(
        "marketlab-core.contracts unavailable; using fallback timestamp default ts_utc",
        stacklevel=2,
    )


def _format_metric_table(items: list[dict]) -> str:
    if not items:
        return "No runs found.\n"

    ordered = sorted(
        items,
        key=lambda item: item.get("metrics", {}).get(
            "trading", item.get("metrics", {}).get("backtest", {}),
        ).get("sharpe", float("-inf")),
        reverse=True,
    )
    lines = ["RANK | RUN_ID | MODEL | SHARPE | CAGR | MAX_DD | HIT_RATE"]
    lines.append("---- | ----- | ----- | ------ | ---- | ------ | --------")
    for rank, row in enumerate(ordered, 1):
        bt = row.get("metrics", {}).get("trading", row.get("metrics", {}).get("backtest", {}))
        lines.append(
            f"{rank:>4} | {row.get('run_id', '')} | {row.get('model', {}).get('type', '')} "
            f"| {bt.get('sharpe', float('nan')):.4f} | {bt.get('cagr', float('nan')):.4f} "
            f"| {bt.get('max_drawdown', float('nan')):.4f} "
            f"| {row.get('metrics', {}).get('information', {}).get('hit_rate', float('nan')):.4f}"
        )
    return "\n".join(lines) + "\n"


def _load_runs(runs_root: Path) -> list[dict]:
    if not runs_root.exists():
        return []
    runs = []
    for directory in sorted(runs_root.iterdir()):
        if not directory.is_dir():
            continue
        summary = directory / "run_summary.json"
        if not summary.exists():
            continue
        try:
            runs.append(json.loads(summary.read_text(encoding="utf-8")))
        except Exception:
            continue
    return runs


def _format_run_summary(summary: dict) -> str:
    return json.dumps(
        {
            "run_id": summary["run_id"],
            "model": summary["model"],
            "regression": summary["metrics"]["regression"],
            "classification": summary["metrics"]["classification"],
            "information": summary["metrics"]["information"],
            "backtest": summary["metrics"].get("trading", summary["metrics"].get("backtest", {})),
            "files": summary["files"],
        },
        indent=2,
    )


def cmd_train(args: argparse.Namespace) -> None:
    base_cfg = load_config(args.config)
    cfg = merge_cli_overrides(
        base_cfg,
        dataset=args.dataset,
        target=args.target,
        timestamp=args.timestamp,
        model=args.model,
        output_root=args.output_root,
        run_id=args.run_id,
        features=[f.strip() for f in args.features.split(",") if f.strip()] if args.features else None,
    )
    summary = execute_train(
        dataset=args.dataset,
        target=args.target,
        timestamp_col=args.timestamp,
        model=args.model,
        config=cfg,
        run_id=args.run_id,
        output_root=args.output_root,
        command="forecast train",
    )
    print(json.dumps(
        {
            "run_id": summary["run_id"],
            "dataset_hash": summary["dataset"]["hash"],
            "metric_regression_mae": summary["metrics"]["regression"]["mae"],
            "metric_sharpe": summary["metrics"].get("trading", summary["metrics"].get("backtest", {})).get("sharpe"),
            "metric_cagr": summary["metrics"].get("trading", summary["metrics"].get("backtest", {})).get("cagr"),
        },
        indent=2,
    ))


def cmd_backtest(args: argparse.Namespace) -> None:
    summary = execute_backtest_only(args.run_id, runs_root=args.runs_root)
    print(json.dumps(
        {
            "run_id": summary["run_id"],
            "backtest": summary["metrics"]["backtest"],
        },
        indent=2,
    ))


def cmd_leaderboard(args: argparse.Namespace) -> None:
    runs_root = Path(args.runs_root)
    runs = _load_runs(runs_root)
    runs = sorted(
        runs,
        key=lambda item: item.get("metrics", {}).get(
            "trading", item.get("metrics", {}).get("backtest", {}),
        ).get("sharpe", float("-inf")),
        reverse=True,
    )
    limit = int(args.limit)
    if limit > 0:
        runs = runs[:limit]
    print(_format_metric_table(runs))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forecast")
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="run a train + walk-forward benchmark")
    train.add_argument("--dataset", required=True, help="path to research-ready dataset")
    train.add_argument("--target", required=True, help="target column (e.g., returns_1d)")
    train.add_argument(
        "--model",
        required=True,
        help="naive, naive0, naive_last, ridge, lasso, xgboost, lightgbm, histgb",
    )
    train.add_argument("--config", default=None, help="optional yaml config file")
    train.add_argument("--features", default=None, help="comma-separated feature list")
    train.add_argument(
        "--timestamp",
        default=TIMESTAMP_COL,
        help=f"timestamp column name (default: {TIMESTAMP_COL})",
    )
    train.add_argument("--run-id", default=None, help="optional run id override")
    train.add_argument("--output-root", default="runs", help="directory where runs are written")
    train.set_defaults(func=cmd_train)

    backtest = sub.add_parser("backtest", help="recompute backtest from an existing run")
    backtest.add_argument("--run-id", required=True)
    backtest.add_argument("--runs-root", default="runs")
    backtest.set_defaults(func=cmd_backtest)

    leaderboard = sub.add_parser("leaderboard", help="show ranked runs from runs directory")
    leaderboard.add_argument("--runs-root", default="runs")
    leaderboard.add_argument("--limit", default=20)
    leaderboard.set_defaults(func=cmd_leaderboard)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
