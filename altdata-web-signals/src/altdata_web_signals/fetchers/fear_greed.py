"""Fear & Greed Index fetcher (Alternative.me API)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from ..http import ApiClient
from ..storage import write_signal_frame
from ..transforms import add_asof_utc, add_delta_and_pct, add_zscore_rolling

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


def add_fng_transforms(df: pl.DataFrame, signal_prefix: str = "signal_fng") -> pl.DataFrame:
    """Add stationarity transforms to FNG DataFrame.

    New columns:
    - {prefix}_delta: absolute day-to-day change
    - {prefix}_pct_change: percent change (winsorized to [-1, 1])
    - {prefix}_regime: categorical fear/greed bucket
    - {prefix}_zscore_30d: 30-day rolling z-score
    """
    val = f"{signal_prefix}_value"
    df = add_delta_and_pct(df, val)
    df = add_zscore_rolling(df, val, window=30)

    # Regime classification from raw value
    df = df.with_columns(
        pl.when(pl.col(val) <= 25).then(pl.lit("extreme_fear"))
        .when(pl.col(val) <= 45).then(pl.lit("fear"))
        .when(pl.col(val) <= 55).then(pl.lit("neutral"))
        .when(pl.col(val) <= 75).then(pl.lit("greed"))
        .otherwise(pl.lit("extreme_greed"))
        .alias(f"{signal_prefix}_regime")
    )

    # Binary extreme flags and distance metric (for use as regime filters)
    df = df.with_columns(
        (pl.col(val) <= 25).cast(pl.Int8).alias(f"{signal_prefix}_is_extreme_fear"),
        (pl.col(val) >= 75).cast(pl.Int8).alias(f"{signal_prefix}_is_extreme_greed"),
        (pl.col(val).cast(pl.Float64) - 50.0).abs().alias(f"{signal_prefix}_extremeness"),
    )

    # asof_utc: day T FGI available at T+1 00:00 UTC
    df = add_asof_utc(df)

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
    df = add_fng_transforms(df)

    meta_cols = [c for c in ["ts_utc", "asof_utc"] if c in df.columns]
    outputs: list[Path] = []

    signal_cols = [c for c in df.columns if c.startswith("signal_fng_")]
    for col in signal_cols:
        topic = col.removeprefix("signal_fng_")
        frame = df.select(meta_cols + [col])
        outputs.append(
            write_signal_frame(
                frame=frame,
                signals_root=signals_root,
                source="fng",
                topic=topic,
                freq=freq,
            )
        )

    return outputs
