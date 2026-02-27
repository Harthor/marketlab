from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from marketlab_core.manifests import (
    validate_artifacts_exist,
    validate_manifest,
    write_json_atomic,
    write_manifest_atomic,
)


def _base_manifest(created_at: str, started_at: str, artifacts: list[dict[str, str]]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "status": "complete",
        "run_id": "run-001",
        "created_at_utc": created_at,
        "started_at_utc": started_at,
        "completed_at_utc": None,
        "dataset_path": "outputs/data/inputs.parquet",
        "dataset_hash": "sha256:datasetsha",
        "config_hash": "sha256:configsha",
        "seed": 42,
        "artifacts": artifacts,
    }


def test_validate_manifest_correlation_ok() -> None:
    created_at = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc).isoformat()
    manifest = _base_manifest(created_at, created_at, [])
    manifest["kind"] = "correlation"
    manifest["top_features"] = {"BTCUSDT": {"ETHUSDT": 0.91}}

    ok, errors = validate_manifest(manifest)
    assert ok, errors


def test_validate_manifest_forecast_ok() -> None:
    created_at = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc).isoformat()
    manifest = _base_manifest(created_at, created_at, [])
    manifest["kind"] = "forecast"
    manifest["model_name"] = "xgboost-v1"
    manifest["metrics"] = {"rmse": 0.82, "mae": 0.61}

    ok, errors = validate_manifest(manifest)
    assert ok, errors


def test_validate_manifest_rejects_unknown_kind() -> None:
    created_at = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc).isoformat()
    manifest = _base_manifest(created_at, created_at, [])
    manifest["kind"] = "other"
    manifest["top_features"] = {}

    ok, errors = validate_manifest(manifest)
    assert not ok
    assert any("kind" in err for err in errors)


def test_validate_manifest_missing_required_key() -> None:
    created_at = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc).isoformat()
    manifest = {
        "schema_version": "1.0",
        "kind": "forecast",
    }
    manifest["model_name"] = "xgboost-v1"
    manifest["metrics"] = {"rmse": 0.82}

    ok, errors = validate_manifest(manifest)
    assert not ok
    assert any("missing required keys" in err for err in errors)


def test_validate_artifacts_exist_checks_workspace_paths(tmp_path: Path) -> None:
    created_at = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc).isoformat()
    present = tmp_path / "present.parquet"
    present.write_text("ok", encoding="utf-8")

    manifest = _base_manifest(
        created_at,
        created_at,
        [
            {"type": "table", "name": "forecast_predictions", "path": "present.parquet"},
            {"type": "plot", "name": "forecast_vs_actual", "path": "missing.png"},
        ],
    )
    manifest["kind"] = "forecast"
    manifest["model_name"] = "xgboost-v1"
    manifest["metrics"] = {"rmse": 0.82}

    ok, missing = validate_artifacts_exist(manifest, tmp_path)
    assert not ok
    assert str(tmp_path / "missing.png") in missing


def test_write_json_atomic_and_manifest_atomic(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload = {"a": 1, "b": [1, 2, 3]}

    write_json_atomic(payload_path, payload)
    loaded_payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert loaded_payload == payload

    created_at = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc).isoformat()
    manifest = _base_manifest(created_at, created_at, [])
    manifest["kind"] = "forecast"
    manifest["model_name"] = "xgboost-v1"
    manifest["metrics"] = {"rmse": 0.82}

    manifest_path = tmp_path / "manifest.json"
    write_manifest_atomic(manifest_path, manifest)
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert stored["run_id"] == "run-001"
    assert stored["status"] == "complete"
    assert stored["run_id"] == manifest["run_id"]
