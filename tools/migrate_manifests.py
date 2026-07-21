#!/usr/bin/env python3
"""One-time migration of legacy run manifests to the canonical 2.0 schema.

Usage:
    .venv-mlab/bin/python tools/migrate_manifests.py [--workspace PATH] [--dry-run]

Scans the known run roots, rewrites any manifest that is not canonical
schema 2.0, and keeps the original next to it as <name>.pre-migration.bak.
The alias tables in here are intentionally the last place they exist:
they used to live in the dashboard's read path; now producers validate at
write time and readers only accept the canonical schema.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "marketlab-core" / "src"))

from marketlab_core.manifests import (  # noqa: E402
    SCHEMA_VERSION,
    sanitize_non_finite,
    validate_manifest,
    write_json_atomic,
)

SCAN_ROOTS = [
    ("correlation", "correlation-engine/reports", "summary.json"),
    ("correlation", "correlation-engine/reports_check", "summary.json"),
    ("correlation", "correlation-engine/reports_csv_check", "summary.json"),
    ("forecast", "forecasting-backtest/runs", "run_summary.json"),
]

CREATED_AT_ALIASES = ("created_at_utc", "created_at", "createdAt", "created", "run_started_at", "start_time")
DATASET_HASH_ALIASES = ("dataset_hash", "dataset_sha256", "datasetHash")
DATASET_PATH_ALIASES = ("dataset_path", "dataset_file", "dataset_file_path")

STATUS_MAP = {
    "running": "running", "in_progress": "running", "queued": "running", "pending": "running",
    "failed": "failed", "error": "failed", "errored": "failed", "crashed": "failed",
    "cancelled": "failed", "canceled": "failed",
    "complete": "complete", "completed": "complete", "done": "complete",
    "success": "complete", "successful": "complete", "finished": "complete",
    "partial": "partial", "incomplete": "partial",
    "skipped": "skipped",
}

ARTIFACT_TYPES = {"table", "plot", "model", "readme", "manifest"}
TABLE_EXTS = {".csv", ".json", ".parquet", ".feather"}
PLOT_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


def _first_str(payload: dict, keys: tuple) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _guess_type(path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix in TABLE_EXTS:
        return "table"
    if suffix in PLOT_EXTS:
        return "plot"
    return None


def _normalize_artifacts(payload: dict) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()

    def add(type_: str | None, name: str | None, path: Any) -> None:
        if not isinstance(path, str) or not path.strip():
            return
        path = path.strip()
        resolved_type = type_ if type_ in ARTIFACT_TYPES else _guess_type(path)
        if resolved_type is None or path in seen:
            return
        seen.add(path)
        out.append({"type": resolved_type, "name": (name or Path(path).name), "path": path})

    raw = payload.get("artifacts")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                add(item.get("type"), item.get("name") or item.get("artifact_name"),
                    item.get("path") or item.get("file") or item.get("filename"))

    for legacy_key, type_ in (("tables", "table"), ("plots", "plot")):
        value = payload.get(legacy_key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    add(type_, None, item)
                elif isinstance(item, dict):
                    add(type_, item.get("name"), item.get("path") or item.get("file"))

    files = payload.get("files")
    if isinstance(files, dict):
        for name, value in files.items():
            if isinstance(value, str):
                add(None, str(name), value)

    return out


def migrate_payload(payload: dict, kind: str, run_dir: Path) -> dict:
    created = _first_str(payload, CREATED_AT_ALIASES) or datetime.fromtimestamp(
        run_dir.stat().st_mtime, tz=timezone.utc
    ).isoformat()

    raw_status = str(payload.get("status") or payload.get("state") or "complete").lower()
    status = STATUS_MAP.get(raw_status, "partial")

    error = payload.get("error")
    if isinstance(error, str):
        error = {"type": "Error", "message": error}
    elif not (isinstance(error, dict) and error.get("message")):
        error = None
    if error is not None:
        error = {"type": str(error.get("type") or "Error"), "message": str(error["message"])}

    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}

    migrated = dict(payload)
    migrated.update(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "status": status,
            "run_id": str(payload.get("run_id") or run_dir.name),
            "created_at_utc": created,
            "started_at_utc": _first_str(payload, ("started_at_utc",)) or created,
            "dataset_path": _first_str(payload, DATASET_PATH_ALIASES) or "unknown",
            "dataset_hash": _first_str(payload, DATASET_HASH_ALIASES) or run_dir.name,
            "config_hash": _first_str(payload, ("config_hash",)) or "unknown",
            "seed": payload.get("seed") if isinstance(payload.get("seed"), int) else int(config.get("seed", 0) or 0),
            "artifacts": _normalize_artifacts(payload),
            "warnings": [str(w) for w in payload.get("warnings", []) if isinstance(w, str)],
            "error": error,
        }
    )
    if kind == "correlation" and not isinstance(migrated.get("top_features"), dict):
        migrated["top_features"] = {}
    if kind == "forecast":
        if not isinstance(migrated.get("model_name"), str) or not migrated["model_name"].strip():
            migrated["model_name"] = str(config.get("model", "unknown")) or "unknown"
        if not isinstance(migrated.get("metrics"), dict):
            migrated["metrics"] = {}
    return sanitize_non_finite(migrated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".", help="monorepo root")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    migrated = skipped = failed = 0

    for kind, rel_root, manifest_name in SCAN_ROOTS:
        root = workspace / rel_root
        if not root.is_dir():
            continue
        for manifest_path in sorted(root.glob(f"*/{manifest_name}")):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"FAILED  {manifest_path}: unreadable ({exc})")
                failed += 1
                continue

            ok, _ = validate_manifest(payload) if isinstance(payload, dict) else (False, [])
            if ok and payload.get("schema_version") == SCHEMA_VERSION and not json.dumps(payload).count("NaN"):
                skipped += 1
                continue

            candidate = migrate_payload(payload if isinstance(payload, dict) else {}, kind, manifest_path.parent)
            ok, errors = validate_manifest(candidate)
            if not ok:
                print(f"FAILED  {manifest_path}: {'; '.join(errors[:3])}")
                failed += 1
                continue

            if args.dry_run:
                print(f"WOULD MIGRATE  {manifest_path}")
            else:
                backup = manifest_path.with_suffix(manifest_path.suffix + ".pre-migration.bak")
                if not backup.exists():
                    backup.write_text(manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
                write_json_atomic(manifest_path, candidate)
                print(f"MIGRATED  {manifest_path}")
            migrated += 1

    print(f"\n{migrated} migrated, {skipped} already canonical, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
