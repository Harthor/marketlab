"""Wikipedia Pageviews API fetcher."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import polars as pl
import urllib.parse

from ..config import slugify_topic
from ..core import normalize_timezone
from ..http import ApiClient
from ..storage import write_signal_frame

WIKI_ENDPOINT = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/all-access/all-agents/daily/{article}/{start}/{end}"


def _to_wiki_timestamp(value: date | str) -> str:
    if isinstance(value, str):
        dt = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    else:
        dt = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    return dt.strftime("%Y%m%d00")


def _article_path(topic: str) -> str:
    return urllib.parse.quote(topic.strip().replace(" ", "_"))


def parse_wikipedia_payload(
    payload: dict[str, Any],
    topic: str,
    start: date,
    end: date,
    *,
    freq: str = "1d",
    signal_prefix: str = "signal_wiki",
) -> pl.DataFrame:
    if "items" not in payload:
        raise ValueError("Respuesta de Wikipedia sin items")

    values: list[tuple[datetime, int]] = []
    for item in payload["items"]:
        ts_raw = str(item.get("timestamp", "")).strip()
        if len(ts_raw) >= 8:
            dt = datetime.strptime(ts_raw[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
        else:
            continue
        values.append((dt, int(item.get("views", 0))))

    if values:
        raw = pl.DataFrame({"ts_utc": [v[0] for v in values], "value": [v[1] for v in values]})
        raw = raw.with_columns(pl.col("ts_utc").dt.truncate(freq).alias("ts_utc"))
        raw = raw.group_by("ts_utc").agg(pl.col("value").sum().alias("value"))
    else:
        raw = pl.DataFrame({"ts_utc": pl.Series([], dtype=pl.Datetime("us", "UTC")), "value": pl.Series([], dtype=pl.Int64)})

    column = f"{signal_prefix}_{slugify_topic(topic)}"

    # completar malla completa de fechas del rango para dejar NA->0
    days = int((end - start).days)
    grid = [datetime.combine(start + timedelta(days=offset), datetime.min.time(), tzinfo=timezone.utc) for offset in range(days + 1)]
    all_days = pl.DataFrame({"ts_utc": grid})

    out = all_days.join(raw, on="ts_utc", how="left")
    out = out.with_columns(pl.col("value").fill_null(0).cast(pl.Int64).alias(column)).select(["ts_utc", column])
    return normalize_timezone(out, ts_col="ts_utc")


def fetch_wiki_series(
    topics: list[str],
    start: str,
    end: str,
    *,
    project: str = "en.wikipedia",
    signals_root: str | Path = "data/signals",
    freq: str = "1d",
    cache_dir: str | Path = ".cache/altdata-web-signals",
) -> list[Path]:
    client = ApiClient(cache_dir=cache_dir)
    start_date = datetime.fromisoformat(start).date()
    end_date = datetime.fromisoformat(end).date()
    outputs: list[Path] = []

    for topic in topics:
        start_key = _to_wiki_timestamp(start_date)
        end_key = _to_wiki_timestamp(end_date)
        url = WIKI_ENDPOINT.format(
            project=project,
            article=_article_path(topic),
            start=start_key,
            end=end_key,
        )
        payload = client.get_json(url)
        frame = parse_wikipedia_payload(
            payload=payload,
            topic=topic,
            start=start_date,
            end=end_date,
            freq=freq,
            signal_prefix="signal_wiki",
        )
        outputs.append(write_signal_frame(frame=frame, signals_root=signals_root, source="wiki", topic=topic, freq=freq))

    return outputs
