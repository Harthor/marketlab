from __future__ import annotations

import base64
import binascii
import csv
import math
import json
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.exceptions import BadRequest

from .utils import json_sanitize

RUN_TYPES = {"correlation", "forecast"}

CORRELATION_ROOT_NAME = "correlation-engine"
CORRELATION_SUBPATH = "reports"
FORECAST_ROOT_NAME = "forecasting-backtest"
FORECAST_SUBPATH = "runs"

CORRELATION_MANIFEST = "summary.json"
FORECAST_MANIFEST = "run_summary.json"

TABLE_EXTS = {".csv", ".json", ".parquet", ".feather"}
PLOT_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}

TABLE_KEYS = (
    "tables",
    "table_artifacts",
    "artifact_tables",
    "table_files",
    "table_paths",
    "artifacts.tables",
    "artifacts.table_artifacts",
)

PLOT_KEYS = (
    "plots",
    "plot_artifacts",
    "artifact_plots",
    "plot_files",
    "plot_paths",
    "artifacts.plots",
    "artifacts.plot_artifacts",
)

CREATED_AT_KEYS = (
    "created_at_utc",
    "created_at",
    "createdAt",
    "created_at_iso",
    "created_at_iso8601",
    "created",
    "run_started_at",
    "start_time",
)

DATASET_HASH_KEYS = (
    "dataset_hash",
    "dataset_hash_id",
    "datasetHash",
    "dataset",
    "dataset_name",
    "datasetName",
)

MODEL_NAME_KEYS = (
    "model_name",
    "modelName",
    "model",
    "model_id",
)

TOP_FEATURES_KEYS = (
    "top_features",
    "top_features_count",
    "top_feature_count",
    "top_feature_counted",
)

RUN_STATUS_COMPLETE = "complete"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_PARTIAL = "partial"

KNOWN_STATUS_KEYS = (
    "status",
    "state",
    "run_status",
    "run_state",
    "status_code",
)

REQUIRED_STATUS_BY_KIND = {
    "correlation": ("schema_version", "dataset_hash", "top_features"),
    "forecast": ("schema_version", "dataset_hash", "model_name"),
}

RUN_ERROR_KEYS = (
    "error",
    "error_message",
    "message",
    "exception",
)


def _extract_top_features_count(summary: Dict[str, Any]) -> Optional[int]:
    value = summary.get("top_features")
    if isinstance(value, int) and not isinstance(value, bool):
        return value

    if isinstance(value, str):
        value = value.strip()
        return int(value) if value.isdigit() else None

    if isinstance(value, list):
        return len(value)

    if isinstance(value, dict):
        max_len = 0
        found = False
        for item in value.values():
            if isinstance(item, list):
                found = True
                if len(item) > max_len:
                    max_len = len(item)
        return max_len if found else 0

    return None


def _has_required_manifest_value(summary: Dict[str, Any], field: str) -> bool:
    if field == "dataset_hash":
        return _extract_string(summary, DATASET_HASH_KEYS) is not None
    if field == "top_features":
        value = summary.get("top_features")
        return value is not None
    if field == "model_name":
        return _extract_string(summary, MODEL_NAME_KEYS) is not None
    return _extract_string(summary, (field,)) is not None


@dataclass(frozen=True)
class RunArtifact:
    name: str
    path: Path
    kind: str


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    kind: str
    name: str
    path: Path
    created_at_utc: Optional[datetime]
    dataset_hash: str
    schema_version: Optional[str]
    status: str
    error: Optional[str]
    errors: Optional[List[str]]
    label: str
    model_name: Optional[str]
    top_features: Optional[int]
    summary: Dict[str, Any]
    tables: List[RunArtifact]
    plots: List[RunArtifact]


@dataclass(frozen=True)
class DatasetSummary:
    name: str
    run_count: int
    source_types: List[str]
    last_seen: Optional[datetime]
    table_count: int
    plot_count: int


def _workspace_root() -> Path:
    return getattr(settings, 'MARKETLAB_WORKSPACE', Path(__file__).resolve().parents[2]).resolve()


def _base_paths() -> List[Tuple[str, Path]]:
    workspace = _workspace_root()
    return [
        ('correlation', workspace / CORRELATION_ROOT_NAME / CORRELATION_SUBPATH),
        ('forecast', workspace / FORECAST_ROOT_NAME / FORECAST_SUBPATH),
    ]


def _run_id_from_path(run_type: str, path: Path) -> str:
    encoded = base64.urlsafe_b64encode(path.as_posix().encode()).decode().rstrip('=')
    return f"{run_type}::{encoded}"


def _decode_run_id(run_id: str) -> Tuple[str, str]:
    if '::' not in run_id:
        raise BadRequest('run_id has invalid format')

    run_type, encoded = run_id.split('::', 1)
    if run_type not in RUN_TYPES:
        raise BadRequest('run_id has invalid run type')

    try:
        padding = '=' * (-len(encoded) % 4)
        rel = base64.urlsafe_b64decode(f"{encoded}{padding}").decode()
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise BadRequest('run_id is not decodable') from exc

    return run_type, rel


def _manifest_for_kind(run_type: str) -> str:
    return CORRELATION_MANIFEST if run_type == 'correlation' else FORECAST_MANIFEST


def _manifest_timestamp(path: Path) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _read_json_if_possible(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def _lookup_nested(payload: Dict[str, Any], dotted_key: str) -> Any:
    current: Any = payload
    for segment in dotted_key.split('.'):
        if not isinstance(current, dict):
            return None
        if segment not in current:
            return None
        current = current[segment]
    return current


def _extract_string(payload: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = _lookup_nested(payload, key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
    return None


def _extract_int(payload: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[int]:
    for key in keys:
        value = _lookup_nested(payload, key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.isdigit():
                return int(normalized)
    return None


def _contains_non_finite(obj: Any) -> bool:
    if isinstance(obj, float):
        return not math.isfinite(obj)

    try:
        import numpy as np  # type: ignore

        if isinstance(obj, np.floating):
            return not np.isfinite(obj)
    except Exception:
        pass

    if isinstance(obj, dict):
        return any(_contains_non_finite(value) for value in obj.values())

    if isinstance(obj, (list, tuple, set)):
        return any(_contains_non_finite(item) for item in obj)

    return False


def _extract_status(summary: Dict[str, Any]) -> Optional[str]:
    raw = _extract_string(summary, KNOWN_STATUS_KEYS)
    if raw is None:
        return None

    normalized = raw.strip().lower()
    if normalized in {"running", "in_progress", "inprogress", "queued", "pending"}:
        return RUN_STATUS_RUNNING
    if normalized in {"failed", "error", "errored", "crashed", "cancelled", "canceled"}:
        return RUN_STATUS_FAILED
    if normalized in {"complete", "completed", "done", "success", "successful", "finished"}:
        return RUN_STATUS_COMPLETE
    if normalized in {"partial", "incomplete"}:
        return RUN_STATUS_PARTIAL
    return None


def _extract_schema_version(summary: Dict[str, Any]) -> Optional[str]:
    return _extract_string(summary, ("schema_version", "schema.version", "schemaVersion"))


def _extract_error(summary: Dict[str, Any]) -> Optional[str]:
    error_value = _extract_string(summary, RUN_ERROR_KEYS)
    if error_value:
        return error_value

    raw_error = _lookup_nested(summary, "error.message")
    if isinstance(raw_error, str) and raw_error.strip():
        return raw_error.strip()

    return None


def _build_label(kind: str, model_name: Optional[str], top_features: Optional[int], summary: Dict[str, Any]) -> str:
    if model_name:
        return model_name
    if top_features is not None:
        return f"top_features={top_features}"
    summary_metric = _extract_string(
        summary,
        (
            "label",
            "run_label",
            "metric",
            "top_metric",
            "top_metric_name",
            "top_metric_value",
            "performance_metric",
            "display_metric",
        ),
    )
    if summary_metric:
        return summary_metric

    for key in (
        "sharpe",
        "return",
        "roi",
        "profit",
        "fitness",
        "score",
        "rmse",
        "mae",
    ):
        raw = summary.get(key) if isinstance(summary, dict) else None
        if isinstance(raw, (int, float)):
            return f"{key}={raw}"

    summary_label = _extract_string(
        summary,
        (
            "name",
            "run_name",
            "display_name",
            "strategy",
            "experiment_name",
            "experimentName",
            "title",
        ),
    )
    if summary_label:
        return summary_label

    return f"{kind} run"


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc)

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_datetime(payload: Dict[str, Any]) -> Optional[datetime]:
    for key in CREATED_AT_KEYS:
        value = _lookup_nested(payload, key)
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _discover_run_manifests(base_dir: Path, run_type: str) -> List[Path]:
    if not base_dir.exists():
        return []
    manifest_name = _manifest_for_kind(run_type)
    return sorted(base_dir.glob(f"*/{manifest_name}"))


def _gather_artifact_values(value: Any, fallback_name: Optional[str] = None) -> List[Tuple[Optional[str], Any]]:
    if value is None:
        return []

    if isinstance(value, (str, Path)):
        return [(fallback_name, value)]

    if isinstance(value, (list, tuple, set)):
        entries: List[Tuple[Optional[str], Any]] = []
        for item in value:
            entries.extend(_gather_artifact_values(item, fallback_name=fallback_name))
        return entries

    if isinstance(value, dict):
        if any(key in value for key in ('path', 'file', 'filename')) and (
            any(key in value for key in ('path', 'file', 'filename', 'name', 'artifact_name'))
        ):
            path_value = value.get('path') or value.get('file') or value.get('filename')
            if path_value is None:
                return []
            return [(value.get('name') or value.get('artifact_name') or fallback_name, path_value)]

        entries: List[Tuple[Optional[str], Any]] = []
        for key, item in value.items():
            if not isinstance(item, (str, Path, list, tuple, set, dict)):
                continue
            entries.extend(_gather_artifact_values(item, fallback_name=str(key)))
        return entries

    return []




def _collect_artifacts_from_manifest_items(payload: Dict[str, Any], kind: str) -> List[Tuple[Optional[str], Any]]:
    raw_artifacts = payload.get("artifacts")
    if not isinstance(raw_artifacts, list):
        return []

    entries: List[Tuple[Optional[str], Any]] = []
    target_kind = kind.lower()
    for item in raw_artifacts:
        if not isinstance(item, dict):
            continue

        raw_type = item.get("type")
        if not isinstance(raw_type, str) or raw_type.strip().lower() != target_kind:
            continue

        raw_path = item.get("path") or item.get("file") or item.get("filename")
        if raw_path is None:
            continue

        name = item.get("name") or item.get("artifact_name") or item.get("artifactName")
        if isinstance(name, str) and not name.strip():
            name = None

        entries.append((name, raw_path))

    return entries


def _collect_artifacts_from_manifest_sections(payload: Dict[str, Any], kind: str) -> List[Tuple[Optional[str], Any]]:
    section = payload.get(f"{kind}s") if isinstance(payload, dict) else None
    if section is None:
        return []
    return _gather_artifact_values(section)


def _collect_artifacts_from_files(payload: Dict[str, Any], kind: str) -> List[Tuple[Optional[str], Any]]:
    raw_files = payload.get("files")
    if not isinstance(raw_files, dict):
        return []

    entries: List[Tuple[Optional[str], Any]] = []
    for name, value in raw_files.items():
        if not isinstance(name, str):
            continue

        if not isinstance(value, (str, Path)):
            continue

        path_text = str(value)
        if kind == 'table' and Path(path_text).suffix.lower() in TABLE_EXTS:
            entries.append((name, value))
            continue

        if kind == 'plot' and Path(path_text).suffix.lower() in PLOT_EXTS:
            entries.append((name, value))
    return entries


def _normalize_artifact_path(run_dir: Path, raw_path: Any) -> Path:
    path_text = str(raw_path).replace('\\', '/').strip()
    if not path_text:
        raise ValueError('artifact path is empty')

    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path
    return (run_dir / path).resolve()


def _collect_artifacts(payload: Dict[str, Any], run_dir: Path, kind: str) -> List[RunArtifact]:
    candidates: List[Tuple[Optional[str], Any]] = []
    source_keys = TABLE_KEYS if kind == 'table' else PLOT_KEYS
    for key in source_keys:
        value = _lookup_nested(payload, key)
        if value is not None:
            candidates.extend(_gather_artifact_values(value))
    candidates.extend(_collect_artifacts_from_manifest_sections(payload, kind))

    candidates.extend(_collect_artifacts_from_manifest_items(payload, kind))
    candidates.extend(_collect_artifacts_from_files(payload, kind))

    artifacts: List[RunArtifact] = []
    seen: set[str] = set()
    for declared_name, raw_path in candidates:
        try:
            path = _normalize_artifact_path(run_dir, raw_path)
        except ValueError:
            continue

        raw_name = (declared_name or "").strip() or raw_path
        candidate_path = Path(raw_path).as_posix()
        if '/' in candidate_path:
            display_name = candidate_path
        else:
            display_name = Path(candidate_path).name

        try:
            relative_name = path.relative_to(run_dir).as_posix()
            display_name = relative_name or display_name
        except ValueError:
            display_name = display_name or str(path.name)

        normalized_key = display_name.lower()
        if normalized_key in seen:
            continue

        seen.add(normalized_key)
        artifacts.append(
            RunArtifact(
                name=display_name,
                path=path,
                kind=kind,
            )
        )

    return artifacts


RUN_STATUS_INVALID = "invalid"


def _read_manifest(path: Path) -> Tuple[Dict[str, Any], Optional[str]]:
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)

    if not isinstance(payload, dict):
        return {}, 'Manifest is not a JSON object'

    return payload, None


def _build_invalid_run_summary(run_type: str, manifest: Path, errors: List[str]) -> RunSummary:
    run_dir = manifest.parent
    try:
        run_id = _run_id_from_path(run_type, run_dir.relative_to(_workspace_root()))
    except Exception:
        run_id = f"{run_type}::{manifest.name}"

    return RunSummary(
        run_id=run_id,
        kind=run_type,
        name=run_dir.name,
        path=run_dir,
        created_at_utc=_manifest_timestamp(manifest),
        dataset_hash=run_dir.name,
        schema_version=None,
        status=RUN_STATUS_INVALID,
        error='; '.join(errors),
        errors=list(errors),
        label=f"{run_type} run",
        model_name=None,
        top_features=None,
        summary={},
        tables=[],
        plots=[],
    )


def _build_run_summary(run_type: str, manifest_path: Path) -> RunSummary:
    run_dir = manifest_path.parent
    summary: Dict[str, Any]
    parse_error: Optional[str]
    summary, parse_error = _read_manifest(manifest_path)

    errors: List[str] = []
    if parse_error:
        errors.append(parse_error)
        return _build_invalid_run_summary(run_type, manifest_path, errors)

    if _contains_non_finite(summary):
        errors.append('sanitized_nonfinite_values')
        summary = json_sanitize(summary)

    run_id = _run_id_from_path(run_type, run_dir.relative_to(_workspace_root()))
    dataset_hash = _extract_string(summary, DATASET_HASH_KEYS) or run_dir.name
    model_name = _extract_string(summary, MODEL_NAME_KEYS)
    top_features = _extract_top_features_count(summary)
    label = _build_label(kind=run_type, model_name=model_name, top_features=top_features, summary=summary)
    created_at_utc = _extract_datetime(summary) or _manifest_timestamp(manifest_path)
    schema_version = _extract_schema_version(summary)
    error_message = _extract_error(summary)
    tables = _collect_artifacts(summary, run_dir, kind='table')
    plots = _collect_artifacts(summary, run_dir, kind='plot')
    declared_status = _extract_status(summary)

    status = declared_status or RUN_STATUS_COMPLETE
    if any(not artifact.path.is_file() for artifact in [*tables, *plots]):
        status = RUN_STATUS_PARTIAL

    if status in (RUN_STATUS_COMPLETE, RUN_STATUS_PARTIAL):
        for required in REQUIRED_STATUS_BY_KIND.get(run_type, ()):
            if not _has_required_manifest_value(summary, required):
                status = RUN_STATUS_PARTIAL
                break

    if error_message:
        status = RUN_STATUS_FAILED

    return RunSummary(
        run_id=run_id,
        kind=run_type,
        name=run_dir.name,
        path=run_dir,
        created_at_utc=created_at_utc,
        dataset_hash=dataset_hash,
        schema_version=schema_version,
        status=status,
        error=error_message,
        errors=errors,
        label=label,
        model_name=model_name,
        top_features=top_features,
        summary=summary,
        tables=tables,
        plots=plots,
    )


def list_runs(
    run_type: Optional[str] = None,
    dataset: Optional[str] = None,
) -> List[RunSummary]:
    runs, _ = list_runs_with_diagnostics(run_type=run_type, dataset=dataset)
    return runs


def list_runs_with_diagnostics(
    run_type: Optional[str] = None,
    dataset: Optional[str] = None,
) -> Tuple[List[RunSummary], List[Dict[str, str]]]:
    if run_type is not None and run_type not in RUN_TYPES:
        raise BadRequest('run type must be correlation or forecast')

    runs: List[RunSummary] = []
    bad_manifests: List[Dict[str, str]] = []
    workspace_root = _workspace_root()

    for current_type, base_path in _base_paths():
        if run_type is not None and current_type != run_type:
            continue

        for manifest in _discover_run_manifests(base_path, current_type):
            manifest_path = str(manifest)
            run: RunSummary
            try:
                run = _build_run_summary(current_type, manifest)
            except Exception as exc:
                error = f'Failed reading run manifest: {exc}'
                run = _build_invalid_run_summary(
                    current_type,
                    manifest,
                    [error],
                )
                bad_manifests.append(
                    {
                        'path': manifest_path,
                        'error': error,
                    }
                )

            if run.status == 'invalid' and run.error:
                existing_paths = {entry.get('path') for entry in bad_manifests}
                if manifest_path not in existing_paths:
                    bad_manifests.append(
                        {
                            'path': manifest_path,
                            'error': run.error,
                        }
                    )

            if dataset is not None and run.dataset_hash.lower() != dataset.lower():
                continue

            if not run.path.is_dir():
                continue

            try:
                _ = run.path.relative_to(workspace_root)
            except ValueError:
                continue

            runs.append(run)

    runs.sort(key=lambda item: item.created_at_utc or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)
    return runs, bad_manifests

def list_datasets() -> List[DatasetSummary]:
    grouped: Dict[str, Dict[str, Any]] = {}

    for run in list_runs():
        bucket = grouped.setdefault(
            run.dataset_hash,
            {
                'name': run.dataset_hash,
                'run_count': 0,
                'source_types': set(),
                'last_seen': None,
                'table_count': 0,
                'plot_count': 0,
            }
        )

        bucket['run_count'] += 1
        bucket['source_types'].add(run.kind)
        bucket['table_count'] += len(run.tables)
        bucket['plot_count'] += len(run.plots)
        if run.created_at_utc is not None and (
            bucket['last_seen'] is None or run.created_at_utc > bucket['last_seen']
        ):
            bucket['last_seen'] = run.created_at_utc

    result: List[DatasetSummary] = []
    for bucket in grouped.values():
        result.append(
            DatasetSummary(
                name=bucket['name'],
                run_count=bucket['run_count'],
                source_types=sorted(bucket['source_types']),
                last_seen=bucket['last_seen'],
                table_count=bucket['table_count'],
                plot_count=bucket['plot_count'],
            )
        )

    result.sort(key=lambda item: item.name.lower())
    return result


def get_run_summary(run_id: str) -> RunSummary:
    run_type, rel = _decode_run_id(run_id)
    workspace = _workspace_root()
    candidate_path = (workspace / rel).resolve()

    base_map = {run_kind: base for run_kind, base in _base_paths()}
    base_path = base_map[run_type].resolve()

    if not str(candidate_path).startswith(str(base_path)):
        raise BadRequest('run_id does not point to a valid run path')

    if not candidate_path.exists() or not candidate_path.is_dir():
        raise BadRequest('run_id does not map to an existing run')

    manifest = candidate_path / _manifest_for_kind(run_type)
    if not manifest.exists():
        raise LookupError('run manifest not found')

    return _build_run_summary(run_type, manifest)


def get_run_health(run_id: str) -> Dict[str, Any]:
    run = get_run_summary(run_id)
    schema_version = run.schema_version
    warnings: List[str] = []
    missing_artifacts: List[Dict[str, str]] = []

    if run.errors:
        warnings.extend(run.errors)

    if schema_version is None:
        warnings.append('Manifest field "schema_version" is missing')

    for required in REQUIRED_STATUS_BY_KIND.get(run.kind, ()):
        if required == "schema_version":
            continue
        if not _has_required_manifest_value(run.summary, required):
            warnings.append(f'Manifest field "{required}" is missing')

    for artifact in [*run.tables, *run.plots]:
        if not artifact.path.is_file():
            missing_artifacts.append(
                {
                    "kind": artifact.kind,
                    "name": artifact.name,
                    "path": str(artifact.path),
                },
            )

    status = run.status
    if status == RUN_STATUS_COMPLETE and missing_artifacts:
        status = RUN_STATUS_PARTIAL
    if run.error and status not in (RUN_STATUS_FAILED, RUN_STATUS_RUNNING):
        status = RUN_STATUS_FAILED

    return {
        "run_id": run.run_id,
        "status": status,
        "schema_version": schema_version,
        "missing_artifacts": missing_artifacts,
        "warnings": warnings,
        "error": (
            {
                "message": run.error,
            }
            if run.error
            else None
        ),
    }


def _resolve_artifact_path(run: RunSummary, kind: str, name: Optional[str]) -> RunArtifact:
    artifacts = run.tables if kind == 'table' else run.plots
    if not artifacts:
        raise FileNotFoundError(f'No {kind} artifacts declared for this run')

    if not name:
        artifact = artifacts[0]
        if not artifact.path.is_file():
            raise FileNotFoundError(f'Artifact {artifact.name} declared for run {run.run_id} is missing')
        return artifact

    target = name.strip().lower()
    for artifact in artifacts:
        artifact_name = artifact.name.lower()
        if artifact_name == target:
            if artifact.path.is_file():
                return artifact
            break

    stem_target = Path(target).stem
    for artifact in artifacts:
        if (
            Path(artifact.name).name.lower() == target
            or artifact.path.name.lower() == target
            or artifact.path.stem.lower() == stem_target
        ):
            if not artifact.path.is_file():
                break
            return artifact

    if artifacts:
        available = ', '.join(artifact.name for artifact in artifacts)
        raise FileNotFoundError(
            f'Artifact {name} is not declared for this run. Available artifacts: {available}'
        )

    raise FileNotFoundError(f'No {kind} artifacts declared for this run')


def get_run_table(run_id: str, name: Optional[str], page: int, page_size: int) -> Dict[str, Any]:
    run = get_run_summary(run_id)
    artifact = _resolve_artifact_path(run, 'table', name)

    suffix = artifact.path.suffix.lower()
    is_binary_table = suffix in {'.parquet', '.feather'}
    table_data = _read_table_file(artifact.path, max_rows=200 if is_binary_table else None)
    total_rows = len(table_data)

    if page <= 0:
        page = 1
    if page_size <= 0:
        page_size = 100
    page_size = min(page_size, 200 if is_binary_table else 1000)

    start = (page - 1) * page_size
    end = start + page_size
    columns = list(table_data[0].keys()) if table_data else []

    return {
        'run_id': run.run_id,
        'table': artifact.name,
        'columns': columns,
        'rows': table_data[start:end],
        'row_count': total_rows,
        'page': page,
        'page_size': page_size,
    }


def get_run_plot_file(run_id: str, name: Optional[str]) -> Tuple[Path, str]:
    run = get_run_summary(run_id)
    artifact = _resolve_artifact_path(run, 'plot', name)
    content_type = mimetypes.guess_type(str(artifact.path))[0] or 'application/octet-stream'
    return artifact.path, content_type


def _read_table_file(path: Path, max_rows: Optional[int] = None) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == '.csv':
        return _read_csv(path)
    if suffix == '.json':
        return _read_json_table(path)
    if suffix in {'.parquet', '.feather'}:
        return _read_parquet_table(path, max_rows=max_rows)
    raise BadRequest('Unsupported table format')


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, 'r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({key: (value if value != '' else None) for key, value in row.items()})
    return rows


def _read_json_table(path: Path) -> List[Dict[str, Any]]:
    payload = _read_json_if_possible(path)
    if payload is None:
        raise BadRequest('Invalid JSON table file')

    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    if isinstance(payload, dict):
        for key in ('rows', 'data', 'items', 'result'):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]

    raise BadRequest('Unsupported JSON table shape')


def _read_parquet_table(path: Path, max_rows: Optional[int] = None) -> List[Dict[str, Any]]:
    try:
        import pandas as pd
    except Exception as exc:
        raise BadRequest('Parquet support missing: install pandas and pyarrow to read parquet tables') from exc

    try:
        if path.suffix.lower() == '.parquet':
            frame = pd.read_parquet(path)
        else:
            frame = pd.read_feather(path)
    except Exception as exc:
        message = str(exc).lower()
        if 'pyarrow' in message or 'pandas' in message:
            raise BadRequest('Parquet support missing: install pandas and pyarrow to read parquet tables') from exc
        raise BadRequest('Failed to read parquet table') from exc

    if max_rows is not None:
        frame = frame.head(max_rows)

    rows = frame.to_dict(orient='records')
    return [dict(row) for row in rows]
