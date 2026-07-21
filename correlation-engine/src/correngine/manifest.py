from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

from .config import RunConfig

try:
    from marketlab_core.manifests import (
        SCHEMA_VERSION,
        ManifestValidationError,
        validate_and_write_manifest,
    )
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "correngine requires marketlab-core for manifest contracts; "
        "install it with: pip install -e ../marketlab-core"
    ) from exc

__all__ = [
    "SCHEMA_VERSION",
    "ManifestValidationError",
    "build_corr_manifest",
    "write_corr_manifest_atomic",
    "sanitize_for_json",
]


def sanitize_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_for_json(v) for key, v in value.items()}
    if isinstance(value, tuple):
        return [sanitize_for_json(v) for v in value]
    if isinstance(value, list):
        return [sanitize_for_json(v) for v in value]
    if hasattr(value, "to_list"):
        return [sanitize_for_json(v) for v in value.to_list()]  # pragma: no cover - compatibility

    try:
        import numpy as np

        if isinstance(value, (np.integer, np.floating)):
            if not float("inf") > value > float("-inf"):
                return None
            if isinstance(value, np.floating):
                return float(value)
            return int(value)
    except Exception:
        pass

    import math

    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value

    if isinstance(value, (str, int, bool)) or value is None:
        return value

    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_corr_manifest_atomic(run_dir: Path, manifest: dict[str, Any], filename: str = "summary.json") -> Path:
    """Sanitize, validate against the canonical schema, and write atomically.

    Non-finite statistics are represented as None (sanitize_for_json); any
    remaining schema violation raises ManifestValidationError and nothing is
    written. The producer's run fails instead of poisoning the workspace.
    """

    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / filename
    payload = sanitize_for_json(manifest)
    validate_and_write_manifest(path, payload)
    return path


def build_corr_manifest(
    result: dict[str, Any] | None,
    config: RunConfig,
    dataset_meta: dict[str, Any],
    artifacts: list[dict[str, str]] | None,
    *,
    status: str,
    top_features: dict[str, Any] | None = None,
    tables: list[str] | None = None,
    plots: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    error: dict[str, Any] | None = None,
    completed_at_utc: str | None = None,
    feature_summary_preview: list[dict[str, Any]] | None = None,
    extra_fields: dict[str, Any] | None = None,
    config_file: str | None = None,
) -> dict[str, Any]:
    if "run_id" not in dataset_meta or "dataset_path" not in dataset_meta or "dataset_hash" not in dataset_meta:
        raise ValueError("dataset_meta must include run_id, dataset_path, dataset_hash")

    created_at_utc = str(dataset_meta.get("created_at_utc", _now()))
    created_utc = str(dataset_meta.get("created_utc", created_at_utc))
    schema_version = str(dataset_meta.get("schema_version", SCHEMA_VERSION))
    config_hash = dataset_meta.get("config_hash")
    if config_hash is None:
        config_hash = _json_config_hash(config)

    manifest: dict[str, Any] = {
        "run_id": str(dataset_meta["run_id"]),
        "schema_version": schema_version,
        "kind": "correlation",
        "status": status,
        "created_at_utc": created_at_utc,
        "created_utc": created_utc,
        "started_at_utc": str(dataset_meta.get("started_at_utc", created_at_utc)),
        "dataset_path": str(Path(dataset_meta["dataset_path"]).resolve()),
        "dataset_hash": str(dataset_meta["dataset_hash"]),
        "dataset_rows": int(dataset_meta["dataset_rows"]),
        "config_file": config_file,
        "config": config.as_dict(),
        "config_hash": str(config_hash),
        "seed": int(config.seed),
        "top_features": top_features or {},
        "artifacts": artifacts or [],
        "tables": tables or [],
        "plots": plots or [],
        "warnings": warnings or [],
    }
    if errors:
        manifest["errors"] = errors
    if completed_at_utc is not None:
        manifest["completed_at_utc"] = completed_at_utc
    if error is not None:
        manifest["error"] = error
    if feature_summary_preview is not None and feature_summary_preview:
        manifest["feature_summary_preview"] = feature_summary_preview
    if extra_fields:
        manifest.update(extra_fields)
    if "running" in status:
        manifest.pop("errors", None)
    if result is not None and "top_features" in result and top_features is None:
        manifest["top_features"] = result.get("top_features", {})

    return manifest


def _json_config_hash(config: RunConfig) -> str:
    payload = config.as_dict()
    payload_text = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    import hashlib

    return hashlib.sha256(payload_text.encode("utf-8")).hexdigest()


