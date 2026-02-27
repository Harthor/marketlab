#!/usr/bin/env python3
"""Offline smoke-demo runner for the forecasting backtest stack."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import polars as pl

from forecasting_backtest.config import load_config
from forecasting_backtest.pipeline import execute_train


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / ".demo_data"
RUNS_ROOT = ROOT_DIR / "runs"
DATASET_PATH = DATA_DIR / "synthetic_research_ready.parquet"


def _build_synthetic_dataset(path: Path, size: int = 1_200, seed: int = 42) -> Path:
    rng = np.random.default_rng(seed)
    start = datetime(2019, 1, 1, tzinfo=timezone.utc)
    dates = [start + timedelta(days=i) for i in range(size)]

    # Weak predictive structure for a realistic smoke test.
    feat_a = rng.normal(0.0, 1.0, size)
    feat_b = np.convolve(feat_a, np.ones(5) / 5, mode="same")
    lag_signal = np.r_[0.0, feat_a[:-1]]
    returns = 0.0025 * lag_signal + 0.01 * rng.normal(0.0, 1.0, size)
    close = 100.0 * (1 + np.cumsum(returns))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    frame = pl.DataFrame(
        {
            "ts": dates,
            "close": close.astype(float),
            "returns_1d": returns.astype(float),
            "feat_a": feat_a.astype(float),
            "feat_b": feat_b.astype(float),
        }
    )
    frame.write_parquet(path)
    return path


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    dataset_path = _build_synthetic_dataset(DATASET_PATH)

    cfg = load_config(str(ROOT_DIR / "configs" / "default.yaml"))
    summary = execute_train(
        dataset=str(dataset_path),
        target="returns_1d",
        model="ridge",
        config=cfg,
        run_id=None,
        output_root=str(RUNS_ROOT),
        command="forecast train (run_demo.py)",
    )

    payload = {
        "run_id": summary["run_id"],
        "run_root": str(RUNS_ROOT / summary["run_id"]),
        "run_summary": str((RUNS_ROOT / summary["run_id"]) / "run_summary.json"),
        "metrics": {
            "regression": summary["metrics"]["regression"],
            "trading": summary["metrics"].get("trading", summary["metrics"].get("backtest", {})),
        },
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
