"""RSS signals: conteo diario por keywords."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import re

import feedparser
import polars as pl
import yaml
from dateutil import parser as date_parser

from ..config import slugify_topic
from ..http import ApiClient
from ..storage import write_signal_frame


def read_feeds_file(path: str | Path) -> list[str]:
    content = Path(path).read_text(encoding="utf-8")
    parsed = yaml.safe_load(content) or []

    if isinstance(parsed, dict):
        parsed = parsed.get("feeds", [])

    urls: list[str] = []
    if not isinstance(parsed, list):
        raise ValueError("El YAML de feeds debe ser una lista o un dict con key 'feeds'.")

    for item in parsed:
        if isinstance(item, str):
            urls.append(item.strip())
        elif isinstance(item, dict) and "url" in item:
            urls.append(str(item["url"]).strip())
    if not urls:
        raise ValueError("No se encontraron URLs válidas en feeds_file")
    return urls


def _parse_entry_time(entry: dict[str, Any]) -> datetime | None:
    for key in ("published", "updated", "created", "pubDate"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = date_parser.parse(raw)
        except Exception:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    return None


def _build_matchers(keywords: list[str], use_regex: bool = False) -> list[tuple[str, Any]]:
    matchers: list[tuple[str, Any]] = []
    for kw in keywords:
        norm = kw.strip()
        if not norm:
            continue
        if use_regex:
            matchers.append((norm, re.compile(norm, flags=re.IGNORECASE | re.MULTILINE)))
        else:
            lower = norm.lower()

            def _contains(value: str, needle: str = lower) -> bool:
                return needle in value

            matchers.append((norm, _contains))
    if not matchers:
        raise ValueError("No se pasaron keywords válidas")
    return matchers


def parse_rss_counts(
    feed_payload: str,
    keywords: list[str],
    start: datetime,
    end: datetime,
    *,
    use_regex: bool = False,
    freq: str = "1d",
    signal_prefix: str = "signal_rss",
) -> dict[str, pl.DataFrame]:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    parsed = feedparser.parse(feed_payload)
    if parsed.bozo and parsed.bozo_exception is not None:
        raise ValueError(f"RSS parse error: {parsed.bozo_exception}")

    matchers = _build_matchers(keywords, use_regex=use_regex)
    # preparar rango + buckets día
    total_days = int((end.date() - start.date()).days)
    day_values = [start.date() + timedelta(days=i) for i in range(total_days + 1)]
    counts = {kw: {day: 0 for day in day_values} for kw, _ in matchers}

    for entry in parsed.entries:
        published = _parse_entry_time(entry)
        if published is None:
            continue
        if published < start or published > end:
            continue

        day = published.date()
        title = str(entry.get("title", "") or "")
        summary = str(entry.get("summary", "") or "")
        text = " ".join([title, summary]).lower()

        for kw, matcher in matchers:
            key = kw
            if isinstance(matcher, re.Pattern):
                is_match = bool(matcher.search(text))
            else:
                is_match = matcher(text)
            if is_match and day in counts[key]:
                counts[key][day] += 1

    result: dict[str, pl.DataFrame] = {}
    for kw in [k for k, _ in matchers]:
        slug = slugify_topic(kw)
        col = f"{signal_prefix}_{slug}"
        rows = [
            (datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc), counts[kw][day])
            for day in day_values
        ]
        df = pl.DataFrame({"ts_utc": [r[0] for r in rows], col: [r[1] for r in rows]})
        df = df.with_columns(pl.col("ts_utc").dt.truncate(freq).alias("ts_utc"))
        result[kw] = df

    return result


def fetch_rss_signals(
    feeds_file: str,
    keywords: list[str],
    start: str,
    end: str,
    *,
    use_regex: bool = False,
    signals_root: str | Path = "data/signals",
    freq: str = "1d",
    cache_dir: str | Path = ".cache/altdata-web-signals",
) -> list[Path]:
    urls = read_feeds_file(feeds_file)
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    keyword_slugs = {kw: slugify_topic(kw) for kw in keywords}
    normalized_days = [start_dt.date() + timedelta(days=offset) for offset in range(int((end_dt.date() - start_dt.date()).days) + 1)]
    totals: dict[str, dict[datetime, int]] = {
        kw: {datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc): 0 for day in normalized_days}
        for kw in keywords
    }

    client = ApiClient(cache_dir=cache_dir)
    for feed_url in urls:
        payload = client.get_text(feed_url)
        keyword_frames = parse_rss_counts(
            feed_payload=payload,
            keywords=keywords,
            start=start_dt,
            end=end_dt,
            use_regex=use_regex,
            freq=freq,
        )
        for kw, frame in keyword_frames.items():
            col = f"signal_rss_{keyword_slugs[kw]}"
            for row in frame.iter_rows(named=True):
                totals[kw][row["ts_utc"]] += int(row[col])

    outputs: list[Path] = []
    for kw, rows in totals.items():
        col = f"signal_rss_{keyword_slugs[kw]}"
        ordered_rows = sorted(rows.items(), key=lambda item: item[0])
        frame = pl.DataFrame({"ts_utc": [r[0] for r in ordered_rows], col: [r[1] for r in ordered_rows]}).sort("ts_utc")
        frame = frame.sort("ts_utc")
        outputs.append(write_signal_frame(frame=frame, signals_root=signals_root, source="rss", topic=kw, freq=freq))
    return outputs
