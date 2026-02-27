"""High-level ingestion orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Final
from uuid import uuid4

import pandas as pd

from .config import Paths
from .connectors import get_connector
from .connectors.base import ConnectorError
from .logging_utils import get_logger
from .normalization import normalize_ohlcv
from .storage import write_ingest_manifest, write_processed_parquet, write_raw_dump

logger = get_logger(__name__)

_MANIFEST_FILENAME: Final = "ingest_summary.json"


def _parse_symbols(raw: str) -> list[str]:
    return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]


def _read_price_meta_hash(processed_path: Path) -> str | None:
    try:
        with (processed_path.with_suffix(".meta.json")).open("r", encoding="utf-8") as stream:
            meta = json.load(stream)
        value = meta.get("sha256")
        return str(value) if value is not None else None
    except Exception:
        return None


def _resolve_manifest_status(artifacts: list[dict[str, object]], has_errors: bool) -> str:
    if not artifacts:
        return "skipped"
    if has_errors:
        return "partial"

    statuses = {artifact.get("status") for artifact in artifacts}
    if statuses == {"complete"}:
        return "complete"
    if statuses == {"skipped"}:
        return "skipped"
    return "partial"


def run_download(
    paths: Paths,
    symbols: str,
    start: str,
    end: str,
    timeframe: str,
    source: str,
    exchange: str | None = None,
    venue: str | None = None,
) -> list[dict[str, object]]:
    paths.create()
    run_id = uuid4().hex
    parsed = _parse_symbols(symbols)
    connector = get_connector(source, exchange=exchange)
    results: list[dict[str, object]] = []

    manifest_path = paths.processed_dir / _MANIFEST_FILENAME
    manifest = {
        "kind": "ingest",
        "status": "complete",
        "run_id": run_id,
        "provider": source,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "completed_at_utc": None,
        "rows": 0,
        "artifacts": [],
        "warnings": [],
        "errors": [],
    }

    for symbol in parsed:
        symbol_venue = (venue or getattr(connector, "venue", "unknown"))
        artifact: dict[str, object] = {
            "symbol": symbol,
            "timeframe": timeframe,
            "provider": source,
            "status": "skipped",
            "rows": 0,
            "dataset_path": None,
            "dataset_hash": None,
            "artifacts": {"parquet_path": None, "meta_path": None},
            "warnings": [],
            "errors": [],
        }

        report_row: dict[str, object] = {
            "symbol": symbol,
            "rows": 0,
            "raw_path": None,
            "processed_path": None,
            "from": None,
            "to": None,
            "manifest_path": str(manifest_path),
        }

        try:
            raw = connector.fetch_ohlcv(symbol=symbol, timeframe=timeframe, start=start, end=end)
        except ConnectorError as exc:
            error = f"connector_error: {exc}"
            logger.error("download_failed", symbol=symbol, source=source, reason=str(exc))
            artifact["status"] = "partial"
            artifact["errors"].append(error)
            manifest["errors"].append(f"{symbol}: {error}")
            manifest["artifacts"].append(artifact)
            results.append(report_row)
            continue

        ingestion_ts = datetime.now(timezone.utc)
        raw_path = write_raw_dump(
            raw=raw,
            paths=paths,
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            run_id=run_id,
        )
        report_row["raw_path"] = str(raw_path)

        try:
            normalized = normalize_ohlcv(
                raw=raw,
                symbol=symbol,
                venue=symbol_venue,
                timeframe=timeframe,
                source=source,
                ingestion_ts=ingestion_ts,
            )
            processed_path = write_processed_parquet(
                frame=normalized,
                paths=paths,
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                run_id=run_id,
            )
        except (ValueError, RuntimeError) as exc:
            warning = f"validation_error: {exc}"
            artifact["status"] = "skipped"
            artifact["warnings"].append(warning)
            manifest["warnings"].append(f"{symbol}: {warning}")
            manifest["artifacts"].append(artifact)
            results.append(report_row)
            continue
        except Exception as exc:  # pragma: no cover - defensive
            error = f"processing_error: {exc}"
            artifact["status"] = "partial"
            artifact["errors"].append(error)
            manifest["errors"].append(f"{symbol}: {error}")
            manifest["artifacts"].append(artifact)
            results.append(report_row)
            continue

        logger.info(
            "download_complete",
            symbol=symbol,
            rows=len(normalized),
            raw_path=str(raw_path),
            processed_path=str(processed_path),
        )

        date_min = None
        date_max = None
        if not normalized.empty:
            date_min = pd.to_datetime(normalized["ts_utc"].min()).isoformat()
            date_max = pd.to_datetime(normalized["ts_utc"].max()).isoformat()

        manifest["rows"] += int(len(normalized))
        artifact["status"] = "complete"
        artifact["rows"] = int(len(normalized))
        artifact["dataset_path"] = str(processed_path)
        artifact["artifacts"]["parquet_path"] = str(processed_path)
        artifact["artifacts"]["meta_path"] = str(processed_path.with_suffix(".meta.json"))
        artifact["dataset_hash"] = _read_price_meta_hash(processed_path)
        manifest["artifacts"].append(artifact)

        report_row["rows"] = int(len(normalized))
        report_row["processed_path"] = str(processed_path)
        report_row["from"] = date_min
        report_row["to"] = date_max
        results.append(report_row)

    manifest["status"] = _resolve_manifest_status(manifest["artifacts"], bool(manifest["errors"]))
    manifest["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_ingest_manifest(manifest_path, manifest)

    return results
