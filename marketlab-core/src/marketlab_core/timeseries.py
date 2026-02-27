"""Time-series utilities focused on fast and reproducible preprocessing."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Iterable, Literal, Sequence

import polars as pl

TimestampInput = Iterable[object] | pl.Series


def _coerce_datetime_series(values: pl.Series, timezone: str = "UTC") -> pl.Series:
    """Coerce generic input to a timezone-aware Datetime(us) series."""

    dt: pl.Series
    if str(values.dtype).startswith("Datetime"):
        dt = values
    elif values.dtype in (pl.Int64, pl.Int32, pl.UInt64, pl.UInt32):
        dt = values.cast(pl.Int64, strict=False).cast(pl.Datetime("us"), strict=False)
    elif values.dtype == pl.Utf8:
        dt = values.str.strptime(pl.Datetime, strict=False)
    elif values.dtype == pl.Date:
        dt = values.cast(pl.Datetime("us"), strict=False)
    else:
        dt = values.cast(pl.Utf8, strict=False).str.strptime(pl.Datetime, strict=False)

    dt = dt.cast(pl.Datetime("us"), strict=False)

    tz = dt.dtype.time_zone
    if tz is None:
        dt = dt.dt.replace_time_zone(timezone)
    elif tz != timezone:
        dt = dt.dt.convert_time_zone(timezone)

    return dt


def parse_timestamps(values: TimestampInput, timezone: str = "UTC") -> pl.Series:
    """Parse and timezone-normalize timestamps from arbitrary input."""

    series = values if isinstance(values, pl.Series) else pl.Series("timestamp", list(values))
    return _coerce_datetime_series(series, timezone=timezone)


def normalize_timezone(
    df: pl.DataFrame,
    ts_col: str = "timestamp",
    timezone: str = "UTC",
) -> pl.DataFrame:
    """Normalize timestamp column to a canonical timezone.

    Returns a copy with `ts_col` converted to datetime(us, tz=timezone).
    """

    if ts_col not in df.columns:
        raise KeyError(f"Missing timestamp column '{ts_col}'")
    normalized = _coerce_datetime_series(df[ts_col], timezone=timezone).alias(ts_col)
    return df.with_columns(normalized)


def _parse_duration(value: str | int | float | timedelta | None) -> timedelta | None:
    if value is None:
        return None
    if isinstance(value, timedelta):
        return value
    if isinstance(value, (int, float)):
        return timedelta(seconds=float(value))
    if not isinstance(value, str):
        raise TypeError("tolerance must be a duration string, number, timedelta or None")

    text = value.strip().lower()
    match = re.fullmatch(r"(\d+)\s*(ms|s|m|h|d|w)", text)
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "ms":
        return timedelta(milliseconds=amount)
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    return timedelta(weeks=amount)


def _suffix_non_timestamp_columns(
    df: pl.DataFrame,
    ts_col: str,
    suffix: str | None = None,
) -> pl.DataFrame:
    if suffix is None:
        return df
    rename_map = {col: f"{col}_{suffix}" for col in df.columns if col != ts_col}
    return df.rename(rename_map)


def _is_numeric_dtype(dtype: pl.DataType) -> bool:
    return dtype.is_numeric()


def _apply_fill(
    df: pl.DataFrame,
    method: str,
    ts_col: str = "timestamp",
    exclude_columns: Sequence[str] | None = None,
) -> pl.DataFrame:
    if method == "none":
        return df

    blocked = set(exclude_columns or [])
    data_columns = [col for col in df.columns if col != ts_col and col not in blocked]
    if not data_columns:
        return df

    if method == "ffill":
        exprs = [pl.col(col).forward_fill().alias(col) for col in data_columns]
        return df.with_columns(exprs)
    if method == "bfill":
        exprs = [pl.col(col).backward_fill().alias(col) for col in data_columns]
        return df.with_columns(exprs)
    if method == "interpolate":
        exprs = []
        for col in data_columns:
            if _is_numeric_dtype(df[col].dtype):
                exprs.append(pl.col(col).interpolate().alias(col))
            else:
                exprs.append(pl.col(col).forward_fill().alias(col))
        return df.with_columns(exprs)

    return df


def resample_series(
    df: pl.DataFrame,
    ts_col: str = "timestamp",
    freq: str = "1m",
    value_cols: Sequence[str] | None = None,
    agg: str = "mean",
    timezone: str = "UTC",
) -> pl.DataFrame:
    """Resample a regular DataFrame on a timestamp frequency."""

    if agg == "ohlcv":
        return resample_ohlcv(df, ts_col=ts_col, freq=freq, timezone=timezone)
    if df.height == 0:
        return df

    if _parse_duration(freq) is None:
        raise ValueError(f"unsupported frequency '{freq}'")

    work = normalize_timezone(df, ts_col=ts_col, timezone=timezone).sort(ts_col)
    if value_cols is None:
        value_cols = [c for c in work.columns if c != ts_col]
    if not value_cols:
        raise ValueError("No value columns found for resampling")

    if agg == "mean":
        agg_expr = [pl.col(col).mean().alias(col) for col in value_cols]
    elif agg == "sum":
        agg_expr = [pl.col(col).sum().alias(col) for col in value_cols]
    elif agg == "min":
        agg_expr = [pl.col(col).min().alias(col) for col in value_cols]
    elif agg == "max":
        agg_expr = [pl.col(col).max().alias(col) for col in value_cols]
    elif agg == "first":
        agg_expr = [pl.col(col).first().alias(col) for col in value_cols]
    elif agg == "last":
        agg_expr = [pl.col(col).last().alias(col) for col in value_cols]
    else:
        raise ValueError("agg must be mean|sum|min|max|first|last|ohlcv")

    return (
        work.with_columns(pl.col(ts_col).dt.truncate(freq).alias("__bucket"))
        .group_by("__bucket")
        .agg(agg_expr)
        .rename({"__bucket": ts_col})
        .sort(ts_col)
    )


def resample_ohlcv(
    df: pl.DataFrame,
    ts_col: str = "timestamp",
    freq: str = "1m",
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
    timezone: str = "UTC",
) -> pl.DataFrame:
    """Resample OHLCV data with canonical finance conventions."""

    if df.height == 0:
        return df
    if _parse_duration(freq) is None:
        raise ValueError(f"unsupported frequency '{freq}'")

    work = normalize_timezone(df, ts_col=ts_col, timezone=timezone)
    missing = {open_col, high_col, low_col, close_col, volume_col} - set(work.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")

    return (
        work.with_columns(pl.col(ts_col).dt.truncate(freq).alias("__bucket"))
        .group_by("__bucket")
        .agg(
            [
                pl.col(open_col).first().alias(open_col),
                pl.col(high_col).max().alias(high_col),
                pl.col(low_col).min().alias(low_col),
                pl.col(close_col).last().alias(close_col),
                pl.col(volume_col).sum().alias(volume_col),
            ]
        )
        .rename({"__bucket": ts_col})
        .sort(ts_col)
    )


def compute_returns(
    df: pl.DataFrame,
    value_col: str,
    *,
    ts_col: str = "timestamp",
    method: Literal["simple", "log"] = "simple",
    horizon: int = 1,
    out_col: str | None = None,
) -> pl.DataFrame:
    """Compute lagged returns for a value column."""

    if horizon <= 0:
        raise ValueError("horizon must be >= 1")
    if value_col not in df.columns:
        raise KeyError(f"Missing value column '{value_col}'")

    work = df.sort(ts_col)
    prev = pl.col(value_col).shift(horizon)
    if out_col is None:
        out_col = f"{value_col}_{method}_ret_{horizon}"

    if method == "simple":
        ret = (pl.col(value_col) / prev - 1.0).alias(out_col)
    elif method == "log":
        valid = (pl.col(value_col) > 0) & (prev > 0)
        ret = pl.when(valid).then(pl.col(value_col).log() - prev.log()).otherwise(None).alias(out_col)
    else:
        raise ValueError("method must be simple or log")

    return work.with_columns(ret)


def rolling_zscore(
    df: pl.DataFrame,
    value_col: str,
    *,
    ts_col: str = "timestamp",
    window: int = 20,
    min_periods: int = 1,
    out_col: str | None = None,
) -> pl.DataFrame:
    """Compute rolling z-score on a numeric value column."""

    if value_col not in df.columns:
        raise KeyError(f"Missing value column '{value_col}'")
    if window <= 0:
        raise ValueError("window must be >= 1")
    if min_periods <= 0:
        raise ValueError("min_periods must be >= 1")
    if out_col is None:
        out_col = f"{value_col}_z_{window}"

    work = df.sort(ts_col)
    rolling_mean = pl.col(value_col).rolling_mean(window_size=window, min_periods=min_periods)
    rolling_std = pl.col(value_col).rolling_std(window_size=window, min_periods=min_periods)
    expr = (
        pl.when(rolling_std == 0)
        .then(None)
        .otherwise((pl.col(value_col) - rolling_mean) / rolling_std)
        .alias(out_col)
    )
    return work.with_columns(expr)


def rolling_rank(
    df: pl.DataFrame,
    value_col: str,
    *,
    ts_col: str = "timestamp",
    window: int = 20,
    out_col: str | None = None,
) -> pl.DataFrame:
    """Rolling rank of the latest value inside each window (0..1)."""

    if value_col not in df.columns:
        raise KeyError(f"Missing value column '{value_col}'")
    if window <= 0:
        raise ValueError("window must be >= 1")
    if out_col is None:
        out_col = f"{value_col}_rank_{window}"

    ordered = df.sort(ts_col)
    values = list(ordered[value_col])
    ranks: list[float | None] = []
    for i, current in enumerate(values):
        if current is None or (isinstance(current, float) and not (current == current)):
            ranks.append(None)
            continue

        start = max(0, i - window + 1)
        window_values = [
            v
            for v in values[start : i + 1]
            if v is not None and not (isinstance(v, float) and not (v == v))
        ]
        if not window_values:
            ranks.append(None)
            continue

        le_count = sum(1 for v in window_values if v <= current)
        ranks.append(le_count / len(window_values))

    return ordered.with_columns(pl.Series(name=out_col, values=ranks).alias(out_col))


def _build_grid(
    start,
    end,
    freq: str,
) -> pl.DataFrame:
    if start > end:
        raise ValueError("start timestamp must be lower than end timestamp")

    return pl.DataFrame(
        {
            "timestamp": pl.datetime_range(
                start=start,
                end=end,
                interval=freq,
                eager=True,
                time_unit="us",
                time_zone="UTC",
            )
        }
    )


def align(
    series_list: Sequence[pl.DataFrame],
    *,
    how: Literal["inner", "outer"] = "inner",
    freq: str | None = None,
    tolerance: str | int | float | timedelta | None = None,
    method: Literal["ffill", "bfill", "interpolate", "none"] = "ffill",
    ts_col: str = "timestamp",
) -> pl.DataFrame:
    """Align multiple series by timestamp.

    - how: join mode between aligned series
    - freq: optional regularization frequency (e.g. "1m")
    - tolerance: optional tolerance in join_asof mode
    - method: fill strategy after alignment
    """

    if how not in {"inner", "outer"}:
        raise ValueError("how must be 'inner' or 'outer'")
    if method not in {"ffill", "bfill", "interpolate", "none"}:
        raise ValueError("method must be ffill, bfill, interpolate or none")
    if not series_list:
        return pl.DataFrame({ts_col: pl.Series([], dtype=pl.Datetime("us"))})

    normalized_frames = []
    for index, frame in enumerate(series_list):
        normalized = normalize_timezone(frame, ts_col=ts_col).sort(ts_col)
        normalized = normalized.unique(subset=[ts_col], keep="last").drop_nulls(subset=[ts_col])
        normalized_frames.append(_suffix_non_timestamp_columns(normalized, ts_col=ts_col, suffix=str(index) if index else None))

    if len(normalized_frames) == 1:
        return normalized_frames[0]

    if freq is None:
        aligned = normalized_frames[0]
        for frame in normalized_frames[1:]:
            aligned = aligned.join(frame, on=ts_col, how=how)
        return _apply_fill(aligned, method=method, ts_col=ts_col).sort(ts_col)

    tolerance_duration = _parse_duration(tolerance)
    if tolerance is not None and tolerance_duration is None:
        raise ValueError(f"Unsupported tolerance '{tolerance}'")

    frame_min_ts = [frame[ts_col].min() for frame in normalized_frames if frame.height]
    frame_max_ts = [frame[ts_col].max() for frame in normalized_frames if frame.height]
    if not frame_min_ts or not frame_max_ts:
        return pl.DataFrame({ts_col: pl.Series([], dtype=pl.Datetime("us"))})

    if _parse_duration(freq) is None:
        raise ValueError(f"Unsupported frequency '{freq}'")

    start = min(frame_min_ts)
    end = max(frame_max_ts)
    grid = _build_grid(start, end, freq)

    aligned_frames: list[pl.DataFrame] = []
    present_columns: list[str] = []
    for i, frame in enumerate(normalized_frames):
        if method == "interpolate":
            aligned = grid.join(frame, on=ts_col, how="left")
        else:
            strategy = "backward" if method == "ffill" else "forward"
            aligned = grid.join_asof(
                frame,
                on=ts_col,
                strategy=strategy,
                tolerance=tolerance_duration,
            )

        frame_columns = [col for col in aligned.columns if col != ts_col]
        if frame_columns:
            marker = f"__present_{i}"
            present_columns.append(marker)
            marker_expr = pl.any_horizontal([pl.col(col).is_not_null() for col in frame_columns]).alias(marker)
            aligned_frames.append(aligned.with_columns(marker_expr))
        else:
            present_columns.append(f"__present_{i}")
            aligned_frames.append(aligned.with_columns(pl.lit(True).alias(f"__present_{i}")))

    aligned = aligned_frames[0]
    for frame in aligned_frames[1:]:
        aligned = aligned.join(frame, on=ts_col, how="outer")

    aligned = aligned.sort(ts_col).unique(subset=[ts_col], keep="last")
    if how == "inner":
        if present_columns:
            aligned = aligned.filter(pl.all_horizontal([pl.col(marker) for marker in present_columns]))
        else:
            aligned = aligned.filter(False)

    aligned = aligned.drop(present_columns)
    return _apply_fill(aligned, method=method, ts_col=ts_col).sort(ts_col)
