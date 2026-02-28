"""Conflict resolver — deduplicate and pick the best candidate per token."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def resolve_conflicts(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Given multiple candidates (possibly for the same token from different
    playbooks), keep only the highest-priority candidate per asset_uid.

    Args:
        candidates: List of candidate dicts, each with keys:
            asset_uid, priority_score, playbook_slug, ...

    Returns:
        Deduplicated list of candidates, sorted by priority_score desc.
    """
    best: dict[str, dict[str, Any]] = {}

    for c in candidates:
        uid = c.get("asset_uid", "")
        if not uid:
            continue

        if uid not in best or c["priority_score"] > best[uid]["priority_score"]:
            if uid in best:
                logger.debug(
                    "Conflict: %s — %s (%.3f) beats %s (%.3f)",
                    uid,
                    c["playbook_slug"],
                    c["priority_score"],
                    best[uid]["playbook_slug"],
                    best[uid]["priority_score"],
                )
            best[uid] = c

    return sorted(best.values(), key=lambda c: c["priority_score"], reverse=True)
