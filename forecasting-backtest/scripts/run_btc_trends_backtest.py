"""Run walk-forward backtest with BTC Google Trends signals.

Executes 4 experiments (naive_mean, ridgecv_basic, lassocv_basic, ridgecv_lagged)
and produces a comparison table + equity overlay plot.
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import polars as pl

# Ensure the package is importable
FORECAST_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FORECAST_ROOT / "src"))

from forecasting_backtest.pipeline import execute_train  # noqa: E402
from forecasting_backtest.plots import plot_equity_comparison  # noqa: E402

# --- paths -------------------------------------------------------------------
DATASET_PATH = FORECAST_ROOT / "data" / "btc_trends_monthly.parquet"
RUNS_ROOT = FORECAST_ROOT / "runs"

# --- feature sets ------------------------------------------------------------
BASE_FEATURES = [
    "signal_trends_bitcoin_pct_change",
    "signal_trends_buy_bitcoin_pct_change",
    "signal_trends_bitcoin_crash_pct_change",
    "signal_trends_crypto_pct_change",
]

ALL_FEATURES = BASE_FEATURES + [
    "signal_trends_bitcoin_pct_change_lag1",
    "signal_trends_bitcoin_pct_change_lag2",
    "signal_trends_buy_bitcoin_pct_change_lag1",
    "signal_trends_buy_bitcoin_pct_change_lag2",
    "signal_trends_bitcoin_crash_pct_change_lag1",
    "signal_trends_bitcoin_crash_pct_change_lag2",
    "signal_trends_crypto_pct_change_lag1",
    "signal_trends_crypto_pct_change_lag2",
    "signal_trends_fear_ratio",
]

# --- common config -----------------------------------------------------------
BASE_CONFIG = {
    "dataset": {"path": None, "timestamp_col": "ts_utc"},
    "target": "returns_1w",
    "features": None,
    "model": {"name": "ridgecv", "params": {}},
    "walk_forward": {
        "mode": "expanding",
        "min_train_rows": 26,
        "test_rows": 1,
        "step_rows": 1,
    },
    "imputation": {
        "strategy": "zero+coverage",
        "coverage_floor": 0.0,
        "max_fill_gap": 1,
    },
    "backtest": {
        "threshold": 0.0,
        "transaction_cost": 0.001,
        "slippage": 0.0005,
        "initial_capital": 1.0,
        "annualize_sharpe_days": 12,
    },
    "random_state": 42,
}

# --- experiment definitions --------------------------------------------------
EXPERIMENTS = [
    {
        "name": "naive_mean",
        "run_id": "btc-trends-naive-mean",
        "model": "naive_mean",
        "features": BASE_FEATURES,
    },
    {
        "name": "ridgecv_basic",
        "run_id": "btc-trends-ridgecv-basic",
        "model": "ridgecv",
        "features": BASE_FEATURES,
    },
    {
        "name": "lassocv_basic",
        "run_id": "btc-trends-lassocv-basic",
        "model": "lassocv",
        "features": BASE_FEATURES,
    },
    {
        "name": "ridgecv_lagged",
        "run_id": "btc-trends-ridgecv-lagged",
        "model": "ridgecv",
        "features": ALL_FEATURES,
    },
]


def _extract_stats(summary: dict) -> dict:
    metrics = summary.get("metrics", {})
    trading = metrics.get("trading", metrics.get("backtest", {}))
    regression = metrics.get("regression", {})
    regime = metrics.get("regime", {})
    return {
        "cagr": trading.get("cagr", float("nan")),
        "sharpe": trading.get("sharpe", float("nan")),
        "max_drawdown": trading.get("max_drawdown", float("nan")),
        "hit_rate": trading.get("hit_rate", float("nan")),
        "trades": trading.get("trades", 0),
        "corr": regression.get("corr", float("nan")),
        "total_return": trading.get("total_return", float("nan")),
        "bull_hit": regime.get("bull_hit_rate", float("nan")),
        "bear_hit": regime.get("bear_hit_rate", float("nan")),
    }


def main() -> None:
    if not DATASET_PATH.exists():
        print(f"ERROR: dataset not found: {DATASET_PATH}", file=sys.stderr)
        print("Run scripts/prepare_btc_trends.py first.", file=sys.stderr)
        sys.exit(1)

    results: list[dict] = []
    equity_series: dict[str, tuple] = {}

    for exp in EXPERIMENTS:
        print(f"\n{'='*60}")
        print(f"Running: {exp['name']} (model={exp['model']})")
        print(f"{'='*60}")

        config = deepcopy(BASE_CONFIG)
        config["model"]["name"] = exp["model"]
        config["features"] = exp["features"]

        try:
            summary = execute_train(
                dataset=str(DATASET_PATH),
                target="returns_1w",
                model=exp["model"],
                config=config,
                run_id=exp["run_id"],
                output_root=str(RUNS_ROOT),
                timestamp_col="ts_utc",
            )
        except Exception as exc:
            print(f"  FAILED: {exc}")
            results.append({"name": exp["name"], "status": "failed", "error": str(exc)})
            continue

        stats = _extract_stats(summary)
        stats["name"] = exp["name"]
        stats["run_id"] = summary["run_id"]
        stats["folds"] = summary.get("folds", 0)
        stats["status"] = summary.get("status", "unknown")
        results.append(stats)

        # Collect equity for comparison plot
        run_dir = RUNS_ROOT / summary["run_id"]
        equity_path = run_dir / "tables" / "equity.parquet"
        if equity_path.exists():
            eq_df = pl.read_parquet(equity_path)
            equity_series[exp["name"]] = (
                eq_df["ts_utc"].to_numpy(),
                eq_df["equity"].to_numpy(),
            )

        print(f"  Status: {summary.get('status')}")
        print(f"  Folds:  {summary.get('folds')}")
        print(f"  CAGR:   {stats['cagr']:.4f}")
        print(f"  Sharpe: {stats['sharpe']:.4f}")
        print(f"  MaxDD:  {stats['max_drawdown']:.4f}")
        print(f"  HitRate:{stats['hit_rate']:.4f}")

    # --- comparison table ----
    print(f"\n\n{'='*80}")
    print("COMPARISON TABLE — BTC Walk-Forward Backtest (Google Trends)")
    print(f"{'='*80}")
    header = (
        f"{'Model':<20} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} "
        f"{'HitRate':>8} {'Trades':>7} {'Corr':>8} {'BullHit':>8} {'BearHit':>8}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        if r.get("status") == "failed":
            print(f"{r['name']:<20} FAILED: {r.get('error', 'unknown')}")
            continue
        print(
            f"{r['name']:<20} "
            f"{r['cagr']:>8.4f} "
            f"{r['sharpe']:>8.4f} "
            f"{r['max_drawdown']:>8.4f} "
            f"{r['hit_rate']:>8.4f} "
            f"{r['trades']:>7d} "
            f"{r['corr']:>8.4f} "
            f"{r.get('bull_hit', float('nan')):>8.4f} "
            f"{r.get('bear_hit', float('nan')):>8.4f}"
        )

    # --- equity overlay plot ---
    if len(equity_series) >= 2:
        overlay_path = RUNS_ROOT / "btc_trends_equity_comparison.png"
        plot_equity_comparison(equity_series, overlay_path)
        print(f"\nEquity comparison plot: {overlay_path}")

    # --- save comparison JSON ---
    comparison_path = RUNS_ROOT / "btc_trends_comparison.json"
    comparison_path.write_text(
        json.dumps(results, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Comparison JSON: {comparison_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
