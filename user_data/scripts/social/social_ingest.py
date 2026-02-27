from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .social_specs import coerce_event
from .social_synthetic_generator import generate_synthetic_events
from .x_provider_import_jsonl import import_jsonl

LOGGER = logging.getLogger("social_ingest")


def ingest(
    out_raw_jsonl: str,
    sources_requested: list[str] | None = None,
    external_jsonl_paths: list[str] | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    sources = sources_requested or ["mock"]
    external_paths = external_jsonl_paths or []

    rows: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []

    for source in sources:
        if source == "mock":
            produced = [coerce_event(r) for r in generate_synthetic_events(now_utc=now_utc)]
            rows.extend(produced)
            coverage.append({"source": "mock", "status": "ok", "events_count": len(produced), "reason": None})
            continue

        if source == "external_jsonl":
            imported_rows, import_summary = import_jsonl(external_paths)
            rows.extend(imported_rows)
            coverage.append(
                {
                    "source": "external_jsonl",
                    "status": "ok",
                    "events_count": import_summary["rows_out"],
                    "reason": None,
                    "files_read": import_summary["files_read"],
                }
            )
            continue

        if source in {"reddit_stub", "rss_stub"}:
            coverage.append(
                {
                    "source": source,
                    "status": "degraded",
                    "events_count": 0,
                    "reason": "stub_source_not_implemented",
                }
            )
            continue

        coverage.append({"source": source, "status": "degraded", "events_count": 0, "reason": "unsupported_source"})

    out_path = Path(out_raw_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")

    degraded = [c["reason"] for c in coverage if c["status"] == "degraded" and c.get("reason")]
    summary = {
        "status": "degraded" if degraded else "ok",
        "sources_requested": sources,
        "events_total": len(rows),
        "degraded_reasons": degraded,
        "coverage": coverage,
        "output_jsonl": str(out_path),
    }
    LOGGER.info("stage=ingest rows_in=%d rows_out=%d output=%s", len(rows), len(rows), out_path)
    return summary

