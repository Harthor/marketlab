"""Manifest models and helpers for reproducible cross-repo outputs."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Literal, TypeAlias

from pydantic import BaseModel, Field, ValidationError, field_validator

ArtifactType: TypeAlias = Literal["table", "plot", "model"]
ManifestKind: TypeAlias = Literal["correlation", "forecast"]
ManifestStatus: TypeAlias = Literal["running", "complete", "failed", "partial"]

REQUIRED_MANIFEST_KEYS: Final[set[str]] = {
    "schema_version",
    "kind",
    "status",
    "run_id",
    "created_at_utc",
    "started_at_utc",
    "dataset_path",
    "dataset_hash",
    "config_hash",
    "seed",
    "artifacts",
}


def _iso_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError("created_at_utc/started_at_utc/completed_at_utc must be ISO datetime")


class ManifestError(BaseModel):
    type: str
    message: str
    traceback_path: str | None = None


class ManifestArtifact(BaseModel):
    type: ArtifactType
    name: str
    path: str
    artifact_id: str | None = None

    @field_validator("name", "path")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("artifact_id")
    @classmethod
    def _non_empty_artifact_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class ManifestBase(BaseModel):
    schema_version: str
    kind: ManifestKind
    status: ManifestStatus
    run_id: str
    created_at_utc: datetime
    started_at_utc: datetime
    completed_at_utc: datetime | None = None
    dataset_path: str
    dataset_hash: str
    config_hash: str
    seed: int
    artifacts: list[ManifestArtifact] = Field(default_factory=list)
    error: ManifestError | None = None

    @field_validator("schema_version", "run_id", "dataset_hash", "config_hash")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("created_at_utc", "started_at_utc", "completed_at_utc", mode="before")
    @classmethod
    def _coerce_datetimes(cls, value: Any) -> datetime | None:
        if value is None:
            return None
        return _iso_datetime(value)

    @field_validator("dataset_path")
    @classmethod
    def _dataset_path_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("dataset_path must not be blank")
        return value


class CorrelationManifest(ManifestBase):
    kind: Literal["correlation"] = "correlation"
    top_features: dict[str, dict[str, float]] = Field(default_factory=dict)


class ForecastManifest(ManifestBase):
    kind: Literal["forecast"] = "forecast"
    model_name: str
    metrics: dict[str, float]

    @field_validator("model_name")
    @classmethod
    def _not_blank_model_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model_name must not be blank")
        return value


def _build_manifest(payload: Mapping[str, Any]) -> ManifestBase:
    if payload.get("kind") == "correlation":
        return CorrelationManifest.model_validate(payload)
    if payload.get("kind") == "forecast":
        return ForecastManifest.model_validate(payload)
    raise ValueError("kind must be 'correlation' or 'forecast'")


def _validation_errors(exc: ValidationError) -> list[str]:
    out: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", ()))
        out.append(f"{location or '<root>'}: {error.get('msg', 'validation error')}")
    return out


def validate_manifest(manifest_dict: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Validate a manifest dictionary and return ok/error tuple."""

    missing = REQUIRED_MANIFEST_KEYS - set(manifest_dict)
    if missing:
        return False, [f"missing required keys: {', '.join(sorted(missing))}"]

    try:
        _build_manifest(manifest_dict)
    except ValidationError as exc:  # pragma: no cover - exercised via tests through messages
        return False, _validation_errors(exc)
    except ValueError as exc:
        return False, [str(exc)]
    return True, []


def validate_artifacts_exist(
    manifest_dict: Mapping[str, Any],
    workspace_root: str | Path,
) -> tuple[bool, list[str]]:
    """Validate artifacts defined in manifest and whether files exist."""

    if not isinstance(manifest_dict, Mapping):
        return False, ["manifest must be a mapping"]

    ok, errors = validate_manifest(manifest_dict)
    if not ok:
        return False, errors

    manifest = _build_manifest(manifest_dict)
    root = Path(workspace_root)
    missing: list[str] = []

    for artifact in manifest.artifacts:
        candidate = Path(artifact.path)
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.exists():
            missing.append(str(candidate))

    return len(missing) == 0, missing


def write_json_atomic(path: str | Path, obj: Any) -> None:
    """Write JSON to path through a temporary file and atomically replace destination."""

    target = Path(path)
    tmp = Path(f"{target}.tmp")
    target.parent.mkdir(parents=True, exist_ok=True)

    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, target)


def write_manifest_atomic(
    path: str | Path,
    manifest_obj: BaseModel | dict[str, Any],
) -> None:
    """Persist manifest using the atomic JSON helper."""

    if isinstance(manifest_obj, BaseModel):
        payload = manifest_obj.model_dump(mode="json")
    else:
        payload = manifest_obj
    write_json_atomic(path, payload)
