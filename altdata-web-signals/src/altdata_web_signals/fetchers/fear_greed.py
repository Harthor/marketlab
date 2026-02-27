"""Fear & Greed Index fetcher (Alternative.me API)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from ..http import ApiClient
from ..storage import write_signal_frame

FNG_API_URL = "https://api.alternative.me/fng/"


def parse_fng_payload(
    payload: dict[str, list[dict[str, str]]],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    signal_prefix: str = "signal_fng",
) -> pl.DataFrame:
    """Parse Fear & Greed Index JSON payload into a polars DataFrame.

    Returns a frame with columns:
    - ts_utc (Datetime UTC)
    - signal_fng_value (Int32, 0-100)
    - signal_fng_classification (Utf8)
    """
    items = payload.get("data", [])
    if not items:
        raise ValueError("FNG payload has no 'data' entries")

    rows: list[dict[str, datetime | int | str]] = []
    for item in items:
        ts = datetime.fromtimestamp(int(item["timestamp"]), tz=UTC)
        ts = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        rows.append({
            "ts_utc": ts,
            f"{signal_prefix}_value": int(item["value"]),
            f"{signal_prefix}_classification": item["value_classification"],
        })

    df = pl.DataFrame(rows).sort("ts_utc")

    if start is not None:
        df = df.filter(pl.col("ts_utc") >= start)
    if end is not None:
        df = df.filter(pl.col("ts_utc") <= end)

    return df


def fetch_fng_signals(
    *,
    start: str | None = None,
    end: str | None = None,
    signals_root: str | Path = "data/signals",
    freq: str = "1d",
    cache_dir: str | Path = ".cache/altdata-web-signals",
    limit: int = 0,
) -> list[Path]:
    """Fetch Fear & Greed Index and write signal parquets.

    Writes two signal files:
    - fng/value/{freq}.parquet  (int 0-100)
    - fng/classification/{freq}.parquet  (string category)
    """
    client = ApiClient(cache_dir=cache_dir)
    data = client.get_json(FNG_API_URL, params={"limit": str(limit), "format": "json"})

    start_dt = (
        datetime.fromisoformat(start).replace(tzinfo=UTC) if start else None
    )
    end_dt = (
        datetime.fromisoformat(end).replace(tzinfo=UTC)
        + timedelta(days=1) - timedelta(microseconds=1)
        if end else None
    )

    df = parse_fng_payload(data, start=start_dt, end=end_dt)

    outputs: list[Path] = []

    # Write value signal (numeric, suitable for correlation)
    value_frame = df.select(["ts_utc", "signal_fng_value"])
    outputs.append(
        write_signal_frame(
            frame=value_frame,
            signals_root=signals_root,
            source="fng",
            topic="value",
            freq=freq,
        )
    )

    # Write classification signal (categorical, for reference)
    class_frame = df.select(["ts_utc", "signal_fng_classification"])
    outputs.append(
        write_signal_frame(
            frame=class_frame,
            signals_root=signals_root,
            source="fng",
            topic="classification",
            freq=freq,
        )
    )

    return outputs
