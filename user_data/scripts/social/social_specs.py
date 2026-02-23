from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


_KNOWN_FIELDS = {
    "event_id",
    "source",
    "ts_utc",
    "text",
    "author",
    "channel_or_subreddit",
    "url",
    "engagement_score",
    "metadata",
}


@dataclass
class SocialEvent:
    event_id: str = ""
    source: str = "unknown"
    ts_utc: str = ""
    text: str = ""
    author: str = ""
    channel_or_subreddit: str = ""
    url: str = ""
    engagement_score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def coerce_event(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row or {})
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    unknown = {k: v for k, v in data.items() if k not in _KNOWN_FIELDS}
    if unknown:
        metadata = dict(metadata)
        metadata.update(unknown)

    event = SocialEvent(
        event_id=str(data.get("event_id", "") or ""),
        source=str(data.get("source", "unknown") or "unknown"),
        ts_utc=str(data.get("ts_utc", "") or ""),
        text=str(data.get("text", "") or ""),
        author=str(data.get("author", "") or ""),
        channel_or_subreddit=str(data.get("channel_or_subreddit", "") or ""),
        url=str(data.get("url", "") or ""),
        engagement_score=_to_float_or_none(data.get("engagement_score")),
        metadata=metadata,
    )
    return asdict(event)


def _to_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None

