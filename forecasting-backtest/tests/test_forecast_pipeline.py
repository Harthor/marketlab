from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pytest

from forecasting_backtest.backtest import run_simple_backtest
from forecasting_backtest.pipeline import execute_backtest_only, execute_train
from forecasting_backtest.validation import iter_time_splits


def _make_synthetic_dataset(path: Path, size: int = 900) -> Path:
    rng = np.random.default_rng(42)
    dates = np.array([np.datetime64("2019-01-01") + np.timedelta64(i, "D") for i in range(size)])
    feature_a = rng.normal(size=size)
    feature_b = pd.Series(feature_a).rolling(7).mean().fillna(0.0).to_numpy()
    lag_signal = pd.Series(feature_a).shift(1).fillna(0.0).to_numpy()
    returns = 0.004 * lag_signal + 0.01 * rng.normal(size=size)
    close = 100 * (1 + np.cumsum(returns))

    frame = pl.DataFrame(
        {
            "ts": dates,
            "close": close.astype(float),
            "returns_1d": returns.astype(float),
            "feat_a": feature_a.astype(float),
            "feat_b": feature_b.astype(float),
        }
    )
    frame.write_parquet(path)
    return path


def test_walk_forward_splits_do_not_leak_temporally() -> None:
    dates = pd.Series(pd.date_range("2020-01-01", periods=200, freq="D", tz="UTC"))
    df = pd.DataFrame({"ts": dates, "returns_1d": np.linspace(0.001, 0.002, 200), "feat": np.arange(200, dtype=float)})
    splits = list(
        iter_time_splits(
            df,
            ts_col="ts",
            train_window_days=90,
            test_window_days=30,
            step_days=30,
            min_train_rows=20,
            min_test_rows=10,
        )
    )

    assert splits
    for split in splits:
        assert split.train_idx.max() < split.test_idx.min()
        assert split.train_idx.size > 0 and split.test_idx.size > 0
        train_end = dates.iloc[split.train_idx].max()
        test_start = dates.iloc[split.test_idx].min()
        assert pd.Timestamp(train_end) < pd.Timestamp(test_start)
    for left, right in zip(splits[:-1], splits[1:], strict=False):
        assert right.train_idx.min() > left.train_idx.min()
        assert right.test_idx.min() > left.test_idx.max()


def test_backtest_costs_and_no_lookahead() -> None:
    returns = np.array([0.01, 0.01, -0.02, 0.02, -0.01])
    preds = np.array([0.2, 0.3, -0.4, 0.1, 0.0])
    timestamps = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC")

    out = run_simple_backtest(
        timestamps=timestamps,
        y_true=returns,
        y_pred=preds,
        threshold=0.15,
        transaction_cost=0.001,
        slippage=0.0005,
        initial_capital=1.0,
    )

    expected_position = np.array([0, 1, 1, -1, 0], dtype=float)
    expected_net = np.array(
        [0.0, 0.0085, -0.02, -0.023, -0.0015],
        dtype=float,
    )
    np.testing.assert_allclose(np.asarray(out["positions"], dtype=float), expected_position)
    np.testing.assert_allclose(
        (np.asarray(out["equity_curve"])[1:] / np.asarray(out["equity_curve"])[:-1]) - 1.0,
        expected_net,
        atol=1e-12,
    )


def test_execute_train_failed_run_is_stable(tmp_path: Path) -> None:
    missing_dataset = tmp_path / "missing.parquet"
    run_id = "failed-train-demo"
    with pytest.raises((FileNotFoundError, ValueError)):
        execute_train(
            dataset=str(missing_dataset),
            target="returns_1d",
            model="ridge",
            run_id=run_id,
            output_root=str(tmp_path / "runs"),
            config={
                "dataset": {"path": None},
                "target": "returns_1d",
                "features": ["close", "feat_a", "feat_b"],
                "model": {"name": "ridge", "params": {}},
                "walk_forward": {
                    "train_window_days": 90,
                    "test_window_days": 30,
                    "step_days": 30,
                    "min_train_rows": 20,
                    "min_test_rows": 10,
                },
                "backtest": {
                    "threshold": 0.0,
                    "transaction_cost": 0.0004,
                    "slippage": 0.0002,
                    "initial_capital": 1.0,
                },
                "random_state": 42,
                "output_root": str(tmp_path / "runs"),
            },
        )

    run_dir = tmp_path / "runs" / run_id
    assert run_dir.exists()
    summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "failed"
    assert summary["kind"] == "forecast"
    assert "error" in summary
    assert "type" in summary["error"]
    assert "message" in summary["error"]
    assert "traceback_path" in summary["error"] and summary["error"]["traceback_path"] is not None
    assert (run_dir / summary["error"]["traceback_path"]).exists()


@pytest.mark.parametrize("model_name", ["ridge", "naive_last"])
def test_pipeline_smoke(tmp_path: Path, model_name: str) -> None:
    dataset_path = _make_synthetic_dataset(tmp_path / f"{model_name}.parquet")
    summary = execute_train(
        dataset=str(dataset_path),
        target="returns_1d",
        model=model_name,
        run_id=f"{model_name}-test",
        output_root=str(tmp_path / "runs"),
        config={
            "dataset": {"path": None},
            "target": "returns_1d",
            "features": ["close", "feat_a", "feat_b"],
            "model": {"name": model_name, "params": {"alpha": 0.9}},
            "walk_forward": {
                "train_window_days": 120,
                "test_window_days": 30,
                "step_days": 30,
                "min_train_rows": 80,
                "min_test_rows": 20,
            },
            "backtest": {
                "threshold": 0.0001,
                "transaction_cost": 0.0004,
                "slippage": 0.0002,
                "initial_capital": 1.0,
            },
            "random_state": 42,
            "output_root": str(tmp_path / "runs"),
        },
    )

    run_dir = tmp_path / "runs" / summary["run_id"]
    assert run_dir.exists()
    assert (run_dir / "run_summary.json").exists()
    assert (run_dir / "tables" / "predictions.parquet").exists()
    assert (run_dir / "tables" / "equity.parquet").exists()
    assert (run_dir / "tables" / "backtest_equity.parquet").exists()
    assert (run_dir / "equity_curve.png").exists()

    data = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert data["status"] == "complete"
    assert data["schema_version"] == "2.0"
    assert "running" not in data["status"]
    assert data["kind"] == "forecast"
    assert data["split"] == {
        "train_window_days": 120,
        "test_window_days": 30,
        "step_days": 30,
        "min_train_rows": 80,
        "min_test_rows": 20,
    }
    assert data["kind"] == "forecast"
    assert "imputation" in data
    assert data["model_name"] == model_name
    assert "created_at_utc" in data
    assert "dataset_path" in data
    assert "dataset_hash" in data
    assert data["seed"] == 42
    assert "trading" in data["metrics"]
    assert isinstance(data["metrics"]["trading"], dict)
    trading_stats = data["metrics"].get("trading", data["metrics"].get("backtest", {}))
    assert "cagr" in trading_stats
    assert data["schema_version"] == "2.0"
    assert data["status"] == "complete"
    assert isinstance(data.get("artifacts"), list)
    for artifact in data["artifacts"]:
        assert isinstance(artifact, dict)
        assert isinstance(artifact.get("type"), str) and artifact["type"] in {"table", "plot", "model"}
        assert isinstance(artifact.get("name"), str) and artifact["name"].strip()
        assert isinstance(artifact.get("path"), str) and artifact["path"].strip()
        assert (run_dir / artifact["path"]).exists()
    assert any(item.get("type") == "table" and item.get("name") == "predictions" for item in data["artifacts"])
    assert any(item.get("type") == "table" and item.get("name") == "equity" for item in data["artifacts"])
    assert any(item.get("type") == "table" and item.get("name") == "backtest_equity" for item in data["artifacts"])
    assert data["metrics"]["regression"]["mae"] >= 0
    assert trading_stats["trades"] >= 0

    pred_df = pl.read_parquet(run_dir / "tables" / "predictions.parquet")
    assert {"ts_utc", "y_true", "y_pred", "position", "pnl"}.issubset(set(pred_df.columns))
    assert "table" in [artifact["type"] for artifact in data["artifacts"]]
    assert bool((pred_df.filter(pl.col("fold") == -1)["position"].to_numpy() == 0.0).all())
    assert bool(np.isnan(np.asarray(pred_df.filter(pl.col("fold") == -1)["y_pred"])).all())

    y_pred = np.asarray(pred_df["y_pred"], dtype=float)
    y_pred_clean = np.nan_to_num(y_pred[:-1], nan=0.0)
    expected_positions = np.r_[
        0.0, np.where(y_pred_clean > 0.0001, 1.0, np.where(y_pred_clean < -0.0001, -1.0, 0.0)),
    ]
    np.testing.assert_array_equal(np.asarray(pred_df["position"], dtype=float), expected_positions)

    equity_df = pl.read_parquet(run_dir / "tables" / "backtest_equity.parquet")
    assert set(equity_df.columns) == {"ts_utc", "equity", "drawdown"}

    rerun = execute_backtest_only(summary["run_id"], runs_root=str(tmp_path / "runs"))
    assert rerun["run_id"] == summary["run_id"]
