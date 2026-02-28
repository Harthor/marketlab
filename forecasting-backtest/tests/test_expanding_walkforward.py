"""Tests for expanding walk-forward splits, new models, and new metrics."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.linear_model import LassoCV, RidgeCV
from sklearn.pipeline import Pipeline

from forecasting_backtest.metrics import regime_hit_rate, rolling_ic
from forecasting_backtest.models import is_baseline, make_model, predict_baseline
from forecasting_backtest.pipeline import execute_train
from forecasting_backtest.validation import iter_expanding_splits

# ---------------------------------------------------------------------------
# iter_expanding_splits
# ---------------------------------------------------------------------------


def _make_expanding_df(n: int = 50) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="ME", tz="UTC")
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "ts": dates,
            "returns_1w": rng.normal(0.005, 0.02, size=n),
            "feat": rng.normal(size=n),
        }
    )


def test_expanding_splits_basic() -> None:
    df = _make_expanding_df(50)
    splits = list(iter_expanding_splits(df, ts_col="ts", min_train_rows=10, test_rows=1, step_rows=1))

    # 50 rows, min_train=10 → first fold train=0..9, test=10
    # last fold train=0..48, test=49 → 40 folds
    assert len(splits) == 40
    assert splits[0].fold == 0
    assert splits[-1].fold == 39

    # Train always starts at index 0
    for split in splits:
        assert split.train_idx[0] == 0


def test_expanding_splits_no_temporal_leak() -> None:
    df = _make_expanding_df(50)
    splits = list(iter_expanding_splits(df, ts_col="ts", min_train_rows=10))

    for split in splits:
        assert split.train_idx.max() < split.test_idx.min()
        assert pd.Timestamp(split.train_end) < pd.Timestamp(split.test_start)


def test_expanding_splits_train_grows() -> None:
    df = _make_expanding_df(50)
    splits = list(iter_expanding_splits(df, ts_col="ts", min_train_rows=10))

    for i in range(1, len(splits)):
        assert len(splits[i].train_idx) > len(splits[i - 1].train_idx)


def test_expanding_splits_min_train_respected() -> None:
    df = _make_expanding_df(50)
    splits = list(iter_expanding_splits(df, ts_col="ts", min_train_rows=20))

    assert len(splits[0].train_idx) >= 20


# ---------------------------------------------------------------------------
# New model types
# ---------------------------------------------------------------------------


def test_ridgecv_model_creation() -> None:
    model = make_model("ridgecv", {})
    assert isinstance(model, Pipeline)
    assert isinstance(model[-1], RidgeCV)


def test_lassocv_model_creation() -> None:
    model = make_model("lassocv", {})
    assert isinstance(model, Pipeline)
    assert isinstance(model[-1], LassoCV)


def test_naive_mean_baseline() -> None:
    assert is_baseline("naive_mean")
    y_train = np.array([0.01, 0.02, 0.03, 0.04, 0.05])
    preds = predict_baseline("naive_mean", y_train, size=3)
    expected_mean = float(np.mean(y_train))
    np.testing.assert_allclose(preds, expected_mean)
    assert len(preds) == 3


# ---------------------------------------------------------------------------
# New metrics
# ---------------------------------------------------------------------------


def test_rolling_ic_length() -> None:
    rng = np.random.default_rng(42)
    y_true = rng.normal(size=50)
    y_pred = y_true * 0.5 + rng.normal(size=50) * 0.5
    ic = rolling_ic(y_true, y_pred, window=10)

    assert len(ic) == 50
    # First 9 should be None
    for i in range(9):
        assert ic[i] is None
    # From index 9 onward should be floats
    for i in range(9, 50):
        assert isinstance(ic[i], float)
        assert -1.0 <= ic[i] <= 1.0


def test_regime_hit_rate_keys() -> None:
    rng = np.random.default_rng(42)
    y_true = rng.normal(size=100)
    y_pred = y_true * 0.3 + rng.normal(size=100) * 0.7
    stats = regime_hit_rate(y_true, y_pred)

    assert "bull_hit_rate" in stats
    assert "bear_hit_rate" in stats
    assert "bull_n" in stats
    assert "bear_n" in stats
    assert stats["bull_n"] + stats["bear_n"] == 100


# ---------------------------------------------------------------------------
# Pipeline smoke test with expanding mode
# ---------------------------------------------------------------------------


def _make_synthetic_expanding_dataset(path: Path, size: int = 80) -> Path:
    rng = np.random.default_rng(42)
    dates = np.array([np.datetime64("2018-01-01") + np.timedelta64(i * 30, "D") for i in range(size)])
    feat_a = rng.normal(size=size)
    feat_b = pd.Series(feat_a).rolling(5).mean().fillna(0.0).to_numpy()
    returns = 0.004 * pd.Series(feat_a).shift(1).fillna(0.0).to_numpy() + 0.01 * rng.normal(size=size)
    close = 100 * (1 + np.cumsum(returns))

    frame = pl.DataFrame(
        {
            "ts": dates,
            "close": close.astype(float),
            "returns_1w": returns.astype(float),
            "feat_a": feat_a.astype(float),
            "feat_b": feat_b.astype(float),
        }
    )
    frame.write_parquet(path)
    return path


def test_pipeline_smoke_expanding(tmp_path: Path) -> None:
    dataset_path = _make_synthetic_expanding_dataset(tmp_path / "expanding.parquet")
    summary = execute_train(
        dataset=str(dataset_path),
        target="returns_1w",
        model="ridgecv",
        run_id="expanding-smoke",
        output_root=str(tmp_path / "runs"),
        config={
            "dataset": {"path": None},
            "target": "returns_1w",
            "features": ["feat_a", "feat_b"],
            "model": {"name": "ridgecv", "params": {}},
            "walk_forward": {
                "mode": "expanding",
                "min_train_rows": 20,
                "test_rows": 1,
                "step_rows": 1,
            },
            "backtest": {
                "threshold": 0.0,
                "transaction_cost": 0.001,
                "slippage": 0.0005,
                "initial_capital": 1.0,
                "annualize_sharpe_days": 12,
            },
            "random_state": 42,
            "output_root": str(tmp_path / "runs"),
        },
    )

    run_dir = tmp_path / "runs" / summary["run_id"]
    assert run_dir.exists()
    assert (run_dir / "run_summary.json").exists()

    data = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert data["status"] == "complete"
    assert data["folds"] > 0
    assert "regime" in data["metrics"]
    assert "trading" in data["metrics"]
    # Verify expanding mode produced many folds (80 rows - 20 min = ~60 folds)
    assert data["folds"] >= 50
