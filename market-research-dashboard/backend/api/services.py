"""Filesystem reader for canonical MarketLab run manifests.

This module reads ONLY schema_version 2.0 manifests as defined in
marketlab_core.manifests. Producers validate at write time, so the reader
does not guess field spellings; a manifest that does not conform surfaces
as an 'invalid' run pointing at tools/migrate_manifests.py.
"""

from __future__ import annotations

import base64
import binascii
import csv
import json
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.exceptions import BadRequest

CANONICAL_SCHEMA_VERSION = "2.0"

RUN_TYPES = {"correlation", "forecast"}

CORRELATION_ROOT_NAME = "correlation-engine"
CORRELATION_SUBPATH = "reports"
FORECAST_ROOT_NAME = "forecasting-backtest"
FORECAST_SUBPATH = "runs"

CORRELATION_MANIFEST = "summary.json"
FORECAST_MANIFEST = "run_summary.json"

RUN_STATUS_COMPLETE = "complete"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_PARTIAL = "partial"
RUN_STATUS_SKIPPED = "skipped"
RUN_STATUS_STALE = "stale"
RUN_STATUS_INVALID = "invalid"

KNOWN_STATUSES = {
    RUN_STATUS_COMPLETE,
    RUN_STATUS_RUNNING,
    RUN_STATUS_FAILED,
    RUN_STATUS_PARTIAL,
    RUN_STATUS_SKIPPED,
}


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
    status_ui: str
    is_stale: bool
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
    decoded_run_id = unquote(run_id)

    if '::' not in decoded_run_id:
        raise BadRequest('run_id has invalid format')

    run_type, encoded = decoded_run_id.split('::', 1)
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


def _read_json_if_possible(path: Path) -> Optional[Any]:
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# ─── Staleness: compare manifest hash against the dataset's sidecar ────────


def _is_dataset_stale(dataset_hash: str, dataset_path: Optional[str], run_dir: Path) -> bool:
    if not dataset_hash or not dataset_path:
        return False

    resolved = Path(dataset_path).expanduser()
    if not resolved.is_absolute():
        resolved = (run_dir / resolved).resolve()

    meta_payload = _read_json_if_possible(resolved.with_suffix(".meta.json"))
    if not isinstance(meta_payload, dict):
        return False

    current_hash = meta_payload.get("out_sha256") or meta_payload.get("sha256")
    if not isinstance(current_hash, str) or not current_hash.strip():
        return False

    return dataset_hash != current_hash.strip()


# ─── Canonical manifest → RunSummary ───────────────────────────────────────


def _build_invalid_run_summary(run_type: str, manifest: Path, errors: List[str]) -> RunSummary:
    run_dir = manifest.parent
    try:
        run_id = _run_id_from_path(run_type, run_dir.relative_to(_workspace_root()))
    except ValueError:
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
        status_ui=RUN_STATUS_INVALID,
        is_stale=False,
        error='; '.join(errors),
        errors=list(errors),
        label=f"{run_type} run",
        model_name=None,
        top_features=None,
        summary={},
        tables=[],
        plots=[],
    )


def _artifact_path(run_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path.replace('\\', '/')).expanduser()
    if path.is_absolute():
        return path
    return (run_dir / path).resolve()


def _collect_artifacts(summary: Dict[str, Any], run_dir: Path, kind: str) -> List[RunArtifact]:
    artifacts: List[RunArtifact] = []
    raw = summary.get("artifacts")
    if not isinstance(raw, list):
        return artifacts

    for item in raw:
        if not isinstance(item, dict) or item.get("type") != kind:
            continue
        raw_path = item.get("path")
        name = item.get("name")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        artifacts.append(
            RunArtifact(
                name=str(name).strip() if isinstance(name, str) and name.strip() else raw_path,
                path=_artifact_path(run_dir, raw_path.strip()),
                kind=kind,
            )
        )
    return artifacts


def _top_features_count(summary: Dict[str, Any]) -> Optional[int]:
    value = summary.get("top_features")
    if not isinstance(value, dict):
        return None
    lengths = [len(item) for item in value.values() if isinstance(item, list)]
    return max(lengths) if lengths else 0


def _build_label(kind: str, model_name: Optional[str], top_features: Optional[int], run_name: str) -> str:
    if model_name:
        return model_name
    if top_features is not None:
        return f"top_features={top_features}"
    return run_name or f"{kind} run"


def _build_run_summary(run_type: str, manifest_path: Path) -> RunSummary:
    run_dir = manifest_path.parent
    summary = _read_json_if_possible(manifest_path)
    if not isinstance(summary, dict):
        return _build_invalid_run_summary(run_type, manifest_path, ['manifest is not a JSON object'])

    schema_version = summary.get("schema_version")
    if schema_version != CANONICAL_SCHEMA_VERSION:
        return _build_invalid_run_summary(
            run_type,
            manifest_path,
            [
                f"unsupported schema_version {schema_version!r} "
                f"(expected {CANONICAL_SCHEMA_VERSION!r}); run tools/migrate_manifests.py"
            ],
        )

    declared_status = summary.get("status")
    if declared_status not in KNOWN_STATUSES:
        return _build_invalid_run_summary(
            run_type, manifest_path, [f"unknown status {declared_status!r}"]
        )

    run_id = _run_id_from_path(run_type, run_dir.relative_to(_workspace_root()))
    dataset_hash = str(summary.get("dataset_hash") or run_dir.name)
    model_name = summary.get("model_name") if isinstance(summary.get("model_name"), str) else None
    top_features = _top_features_count(summary) if run_type == "correlation" else None
    created_at_utc = _parse_datetime(summary.get("created_at_utc")) or _manifest_timestamp(manifest_path)

    error_payload = summary.get("error")
    if isinstance(error_payload, dict):
        error_message = str(error_payload.get("message") or "") or None
    elif isinstance(error_payload, str):
        error_message = error_payload.strip() or None
    else:
        error_message = None

    tables = _collect_artifacts(summary, run_dir, kind='table')
    plots = _collect_artifacts(summary, run_dir, kind='plot')

    status = str(declared_status)
    if status == RUN_STATUS_COMPLETE and any(
        not artifact.path.is_file() for artifact in [*tables, *plots]
    ):
        status = RUN_STATUS_PARTIAL
    if error_message and status not in (RUN_STATUS_FAILED, RUN_STATUS_RUNNING):
        status = RUN_STATUS_FAILED

    is_stale = _is_dataset_stale(dataset_hash, summary.get("dataset_path"), run_dir)
    status_ui = RUN_STATUS_STALE if is_stale else status

    return RunSummary(
        run_id=run_id,
        kind=run_type,
        name=run_dir.name,
        path=run_dir,
        created_at_utc=created_at_utc,
        dataset_hash=dataset_hash,
        schema_version=str(schema_version),
        status=status,
        status_ui=status_ui,
        is_stale=is_stale,
        error=error_message,
        errors=[str(item) for item in summary.get("errors", []) if isinstance(item, str)],
        label=_build_label(run_type, model_name, top_features, run_dir.name),
        model_name=model_name,
        top_features=top_features,
        summary=summary,
        tables=tables,
        plots=plots,
    )


# ─── Listing / lookup ──────────────────────────────────────────────────────


def _discover_run_manifests(base_dir: Path, run_type: str) -> List[Path]:
    if not base_dir.exists():
        return []
    return sorted(base_dir.glob(f"*/{_manifest_for_kind(run_type)}"))


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
            run = _build_run_summary(current_type, manifest)

            if run.status == RUN_STATUS_INVALID and run.error:
                bad_manifests.append({'path': str(manifest), 'error': run.error})

            if dataset is not None and run.dataset_hash.lower() != dataset.lower():
                continue
            if not run.path.is_dir() or not run.path.is_relative_to(workspace_root):
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

    result = [
        DatasetSummary(
            name=bucket['name'],
            run_count=bucket['run_count'],
            source_types=sorted(bucket['source_types']),
            last_seen=bucket['last_seen'],
            table_count=bucket['table_count'],
            plot_count=bucket['plot_count'],
        )
        for bucket in grouped.values()
    ]
    result.sort(key=lambda item: item.name.lower())
    return result


def get_run_summary(run_id: str) -> RunSummary:
    run_type, rel = _decode_run_id(run_id)
    workspace = _workspace_root()
    candidate_path = (workspace / rel).resolve()

    base_map = {run_kind: base for run_kind, base in _base_paths()}
    base_path = base_map[run_type].resolve()

    if not candidate_path.is_relative_to(base_path):
        raise BadRequest('run_id does not point to a valid run path')

    if not candidate_path.is_dir():
        raise BadRequest('run_id does not map to an existing run')

    manifest = candidate_path / _manifest_for_kind(run_type)
    if not manifest.exists():
        raise LookupError('run manifest not found')

    return _build_run_summary(run_type, manifest)


# ─── Health ────────────────────────────────────────────────────────────────


def health_from_run(run: RunSummary) -> Dict[str, Any]:
    """Compute health from an already-parsed RunSummary (no re-reading)."""

    warnings: List[str] = []
    missing_artifacts: List[Dict[str, str]] = []

    if run.errors:
        warnings.extend(run.errors)

    raw_warnings = run.summary.get("warnings")
    if isinstance(raw_warnings, list):
        warnings.extend(str(item) for item in raw_warnings if isinstance(item, str))

    for artifact in [*run.tables, *run.plots]:
        if not artifact.path.is_file():
            reason = (
                "artifact path exists but is not a file"
                if artifact.path.exists()
                else "artifact file not found"
            )
            missing_artifacts.append(
                {
                    "kind": artifact.kind,
                    "name": artifact.name,
                    "path": str(artifact.path),
                    "reason": reason,
                },
            )

    status = run.status
    if status == RUN_STATUS_COMPLETE and missing_artifacts:
        status = RUN_STATUS_PARTIAL

    if run.is_stale and status not in (RUN_STATUS_FAILED, RUN_STATUS_RUNNING):
        warnings.append("dataset hash in manifest does not match dataset metadata sidecar")

    return {
        "run_id": run.run_id,
        "status": status,
        "status_ui": run.status_ui,
        "is_stale": run.is_stale,
        "schema_version": run.schema_version,
        "missing_artifacts": missing_artifacts,
        "warnings": warnings,
        "error": {"message": run.error} if run.error else None,
    }


def get_run_health(run_id: str) -> Dict[str, Any]:
    return health_from_run(get_run_summary(run_id))


# ─── Artifact serving ──────────────────────────────────────────────────────


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
        if artifact.name.lower() == target or artifact.path.name.lower() == target:
            if not artifact.path.is_file():
                break
            return artifact

    available = ', '.join(artifact.name for artifact in artifacts)
    raise FileNotFoundError(
        f'Artifact {name} is not declared for this run. Available artifacts: {available}'
    )


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
    except ImportError as exc:
        raise BadRequest('Parquet support missing: install pandas and pyarrow to read parquet tables') from exc

    try:
        if path.suffix.lower() == '.parquet':
            frame = pd.read_parquet(path)
        else:
            frame = pd.read_feather(path)
    except Exception as exc:
        raise BadRequest('Failed to read parquet table') from exc

    if max_rows is not None:
        frame = frame.head(max_rows)

    return [dict(row) for row in frame.to_dict(orient='records')]
