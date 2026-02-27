from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pytest

from correngine.config import RunConfig
from correngine.manifest import SCHEMA_VERSION, build_corr_manifest, sanitize_for_json, write_corr_manifest_atomic
from correngine.runner import run_correlation


def _has_no_non_finite_numbers(payload: object) -> bool:
    if isinstance(payload, dict):
        return all(_has_no_non_finite_numbers(value) for value in payload.values())
    if isinstance(payload, list):
        return all(_has_no_non_finite_numbers(value) for value in payload)
    if isinstance(payload, float):
        if not np.isfinite(payload):
            return False
    if isinstance(payload, (list, tuple, dict)):
        return True
    return True


def test_sanitize_for_json_replaces_non_finite_values() -> None:
    payload = {
        "a": float("nan"),
        "b": float("inf"),
        "c": float("-inf"),
        "nested": {
            "d": float("nan"),
            "e": 123,
            "f": [float("inf"), 1.5, float("nan")],
        },
    }
    cleaned = sanitize_for_json(payload)
    assert cleaned["a"] is None
    assert cleaned["b"] is None
    assert cleaned["c"] is None
    assert cleaned["nested"]["d"] is None
    assert cleaned["nested"]["f"][0] is None
    assert cleaned["nested"]["f"][2] is None


def test_manifest_is_json_strict_and_has_required_fields() -> None:
    cfg = RunConfig(
        dataset="/tmp/fake.parquet",
        target="returns_1d",
        timestamp="ts_utc",
        output_root="/tmp/reports",
    )
    manifest = build_corr_manifest(
        result={
            "top_features": {
                "pearson": [{"feature": "f1", "score": 0.8}],
                "spearman": [],
                "mi": [],
                "best_lag": [],
                "pearson_abs": [],
                "spearman_abs": [],
                "mutual_information": [],
                "distance_correlation": [],
            },
            "feature_summary_preview": [],
        },
        config=cfg,
        dataset_meta={
            "run_id": "manifest-test",
            "dataset_path": "/tmp/fake.parquet",
            "dataset_hash": "abcdef123456",
            "dataset_rows": 123,
            "created_at_utc": "2026-02-27T00:00:00+00:00",
        },
        artifacts=[
            {"type": "table", "name": "feature_summary_csv", "path": "tables/feature_summary.csv"}
        ],
        status="complete",
        top_features={
            "pearson": [{"feature": "f1", "score": 0.8}],
            "spearman": [],
            "mi": [],
            "best_lag": [],
            "pearson_abs": [],
            "spearman_abs": [],
            "mutual_information": [],
            "distance_correlation": [],
        },
        tables=["tables/feature_summary.csv"],
        plots=["plots/rolling_corr.png"],
        warnings=[],
        completed_at_utc="2026-02-27T00:00:05+00:00",
    )

    payload = json.dumps(manifest, allow_nan=False)
    assert len(payload) > 0
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["kind"] == "correlation"
    assert manifest["status"] == "complete"
    assert manifest["run_id"] == "manifest-test"
    assert Path(manifest["dataset_path"]).resolve() == Path("/tmp/fake.parquet").resolve()
    assert manifest["dataset_hash"] == "abcdef123456"
    assert manifest["completed_at_utc"] == "2026-02-27T00:00:05+00:00"
    assert manifest["artifacts"]


def test_manifest_sanitizes_nonfinite_to_null(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    payload = {
        "run_id": "nan-test",
        "schema_version": SCHEMA_VERSION,
        "kind": "correlation",
        "status": "complete",
        "created_at_utc": "2026-01-01T00:00:00+00:00",
        "created_utc": "2026-01-01T00:00:00+00:00",
        "dataset_path": "/tmp/test.parquet",
        "dataset_hash": "abc",
        "dataset_rows": 1,
        "config": {},
        "config_hash": "config-hash",
        "seed": 1,
        "artifacts": [{"type": "table", "name": "feature_summary", "path": "tables/feature_summary.parquet"}],
        "top_features": {
            "pearson": [{"feature": "f", "score": float("nan"), "p_value": float("inf"), "n_effective": float("-inf")}],
            "spearman": [],
            "mi": [],
            "best_lag": [],
        },
        "feature_summary_preview": [
            {"feature": "f", "metric": "pearson", "score": float("nan"), "p_value": float("inf"), "n_effective": float("-inf")},
        ],
    }
    write_corr_manifest_atomic(run_dir, payload)
    loaded = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert loaded["top_features"]["pearson"][0]["score"] is None
    assert loaded["top_features"]["pearson"][0]["p_value"] is None
    assert loaded["top_features"]["pearson"][0]["n_effective"] is None
    assert loaded["feature_summary_preview"][0]["score"] is None


def test_run_correlation_small_dataset_marked_as_skipped(tmp_path: Path) -> None:
    df = pl.DataFrame(
        {
            "ts_utc": pl.Series("ts_utc", pd.date_range("2020-01-01", periods=2, freq="1d", tz="UTC")),
            "returns_1d": [0.01, -0.02],
            "feature_a": [1.0, 0.5],
        }
    )
    dataset_path = tmp_path / "small.parquet"
    df.write_parquet(dataset_path)

    cfg = RunConfig(
        dataset=str(dataset_path),
        target="returns_1d",
        timestamp="ts_utc",
        output_root=str(tmp_path / "reports"),
        max_lag=5,
        windows=(3,),
        seed=7,
        bootstrap=0,
        top=10,
        min_effective_obs=10,
    )

    result = run_correlation(cfg)
    assert result.summary["status"] == "skipped"
    assert result.summary["dataset_rows"] == 2
    assert "insufficient_data" in (result.summary.get("errors") or [])

    summary_path = result.run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "skipped"
    assert summary["dataset_rows"] == 2
    assert summary["artifacts"] == []
    assert _has_no_non_finite_numbers(summary)


def test_run_correlation_no_artifacts_becomes_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    periods = 200
    index = pd.date_range("2020-01-01", periods=periods, freq="1d", tz="UTC")
    feature = np.sin(np.linspace(0.0, 4.0 * np.pi, periods))
    target = feature + np.random.RandomState(0).normal(0.0, 0.1, periods)

    df = pl.DataFrame(
        {
            "ts_utc": pd.Series(index),
            "returns_1d": target,
            "feature_signal": feature,
            "noise": np.random.RandomState(1).normal(0.0, 1.0, periods),
        }
    )
    dataset_path = tmp_path / "no_artifacts.parquet"
    df.write_parquet(dataset_path)

    monkeypatch.setattr("correngine.runner._write_tables", lambda *args, **kwargs: None)
    monkeypatch.setattr("correngine.runner.plot_rolling_correlations", lambda *args, **kwargs: None)
    monkeypatch.setattr("correngine.runner.plot_lag_profiles", lambda *args, **kwargs: None)

    cfg = RunConfig(
        dataset=str(dataset_path),
        target="returns_1d",
        timestamp="ts_utc",
        output_root=str(tmp_path / "reports"),
        max_lag=5,
        windows=(5, 10),
        seed=7,
        bootstrap=0,
        top=10,
        min_effective_obs=30,
    )

    result = run_correlation(cfg)
    assert result.summary["status"] == "skipped"
    assert result.summary.get("reason") == "no usable outputs"
    assert result.summary["tables"] == []
    assert result.summary["plots"] == []
    assert "no_artifacts_produced" in result.summary["warnings"]


def test_run_correlation_complete_includes_top_correlations_and_top_features(tmp_path: Path) -> None:
    periods = 400
    index = pd.date_range("2020-01-01", periods=periods, freq="1d", tz="UTC")
    x = np.linspace(0.0, 20.0, periods)
    noise = np.random.RandomState(42).normal(0.0, 0.1, periods)
    feature_signal = np.sin(x) + noise
    feature_noise = np.random.RandomState(7).normal(0.0, 1.0, periods)
    target = pd.Series(feature_signal).shift(3).bfill().to_numpy()

    df = pl.DataFrame(
        {
            "ts_utc": pd.Series(index),
            "returns_1d": target,
            "signal_1": feature_signal,
            "noise": feature_noise,
        }
    )
    dataset_path = tmp_path / "complete.parquet"
    df.write_parquet(dataset_path)

    cfg = RunConfig(
        dataset=str(dataset_path),
        target="returns_1d",
        timestamp="ts_utc",
        output_root=str(tmp_path / "reports"),
        max_lag=5,
        windows=(5, 10),
        seed=7,
        bootstrap=0,
        top=20,
        min_effective_obs=30,
    )

    result = run_correlation(cfg)
    assert result.summary["status"] == "complete"
    assert "top_features" in result.summary
    assert isinstance(result.summary["top_features"], dict)
    assert result.summary["top_features"]["pearson"] is not None
    tables = result.summary.get("tables")
    assert isinstance(tables, list)
    assert "tables/top_correlations.csv" in tables
    assert (result.run_dir / "tables" / "top_correlations.csv").exists()
