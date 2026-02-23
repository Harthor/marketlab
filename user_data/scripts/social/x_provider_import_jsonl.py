from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .social_specs import coerce_event


def import_jsonl(paths: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows_in = 0
    parse_errors = 0
    files_read = 0

    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        files_read += 1
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows_in += 1
                try:
                    payload = json.loads(line)
                except Exception:
                    parse_errors += 1
                    continue
                if not isinstance(payload, dict):
                    continue

                mapped = _map_row(payload)
                rows.append(coerce_event(mapped))

    summary = {
        "status": "ok",
        "rows_in": rows_in,
        "rows_out": len(rows),
        "parse_errors": parse_errors,
        "files_read": files_read,
    }
    return rows, summary


def _map_row(payload: dict[str, Any]) -> dict[str, Any]:
    text = _pick_str(payload, ["text", "full_text", "content", "body", "title"])
    ts_raw = _pick_first(payload, ["ts_utc", "timestamp", "created_at", "time", "date", "datetime"])
    ts_utc = _coerce_timestamp(ts_raw)
    event_id = _pick_str(payload, ["event_id", "id", "tweet_id", "post_id"]) or ""
    author = _pick_str(payload, ["author", "username", "user", "screen_name"]) or ""
    source = _pick_str(payload, ["source"]) or "x_provider"
    channel = _pick_str(payload, ["channel_or_subreddit", "channel", "subreddit"]) or ""
    url = _pick_str(payload, ["url", "link", "permalink"]) or ""

    known_keys = {
        "text",
        "full_text",
        "content",
        "body",
        "title",
        "ts_utc",
        "timestamp",
        "created_at",
        "time",
        "date",
        "datetime",
        "event_id",
        "id",
        "tweet_id",
        "post_id",
        "author",
        "username",
        "user",
        "screen_name",
        "source",
        "channel_or_subreddit",
        "channel",
        "subreddit",
        "url",
        "link",
        "permalink",
    }
    metadata = {k: v for k, v in payload.items() if k not in known_keys}

    return {
        "event_id": event_id,
        "source": source,
        "ts_utc": ts_utc,
        "text": text or "",
        "author": author,
        "channel_or_subreddit": channel,
        "url": url,
        "engagement_score": _engagement_score(payload),
        "metadata": metadata,
    }


def _pick_first(payload: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _pick_str(payload: dict[str, Any], keys: list[str]) -> str | None:
    value = _pick_first(payload, keys)
    if value is None:
        return None
    return str(value)


def _coerce_timestamp(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _engagement_score(payload: dict[str, Any]) -> float | None:
    keys = [
        "engagement_score",
        "like_count",
        "likes",
        "reply_count",
        "replies",
        "retweet_count",
        "retweets",
        "quote_count",
        "quotes",
        "view_count",
        "views",
    ]
    total = 0.0
    seen = False
    for key in keys:
        if key not in payload:
            continue
        try:
            total += float(payload[key] or 0.0)
            seen = True
        except Exception:
            continue
    return total if seen else None

