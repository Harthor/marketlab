"""Audit logger — append-only JSON log for candidate generation runs."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_audit_dir() -> Path:
    workspace = getattr(settings, "MARKETLAB_WORKSPACE", Path("."))
    audit_dir = Path(workspace) / "paper-trading" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    return audit_dir


def log_generation_run(
    regime: str,
    regime_confidence: float,
    evaluated_count: int,
    candidates_raw: int,
    candidates_after_conflict: int,
    candidates_after_overlay: int,
    emitted_count: int,
    details: list[dict[str, Any]] | None = None,
) -> None:
    """Append a run summary to the audit log."""
    ts = datetime.now(tz=timezone.utc)
    record = {
        "timestamp": ts.isoformat(),
        "regime": regime,
        "regime_confidence": round(regime_confidence, 4),
        "evaluated_count": evaluated_count,
        "candidates_raw": candidates_raw,
        "candidates_after_conflict": candidates_after_conflict,
        "candidates_after_overlay": candidates_after_overlay,
        "emitted_count": emitted_count,
    }
    if details:
        record["details"] = details

    try:
        audit_dir = _get_audit_dir()
        log_file = audit_dir / f"generation_{ts:%Y%m%d}.jsonl"
        with log_file.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        logger.warning("Could not write audit log", exc_info=True)
