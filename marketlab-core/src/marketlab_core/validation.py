"""Validation helpers for market data."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import polars as pl

from .timeseries import _parse_duration


def validate_timestamp_series(df: pl.DataFrame, ts_col: str = "timestamp") -> dict[str, Any]:
    """Validate timestamp column and return a compact validation report."""

    errors: list[str] = []
    warnings: list[str] = []
    if ts_col not in df.columns:
        errors.append(f"missing column '{ts_col}'")
        return {"ok": False, "errors": errors, "warnings": warnings, "rows": df.height}

    d = df[ts_col]
    if d.len() == 0:
        return {
            "ok": True,
            "errors": errors,
            "warnings": warnings + ["empty dataframe"],
            "rows": 0,
            "duplicated_timestamps": 0,
            "null_timestamps": 0,
        }

    if not str(d.dtype).startswith("Datetime"):
        errors.append(f"column '{ts_col}' must be Datetime")
        return {
            "ok": False,
            "errors": errors,
            "warnings": warnings,
            "rows": df.height,
            "duplicated_timestamps": 0,
            "null_timestamps": 0,
        }

    if not d.is_sorted():
        errors.append(f"'{ts_col}' is not sorted")

    null_count = int(d.is_null().sum())
    if null_count:
        errors.append(f"{null_count} null timestamps")

    duplicate_count = d.is_duplicated().sum()
    if duplicate_count:
        errors.append(f"{duplicate_count} duplicated timestamps")

    if any("not sorted" in item.lower() for item in errors):
        warnings.append("sorting required before resampling/aligning")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "rows": df.height,
        "duplicated_timestamps": int(duplicate_count),
        "null_timestamps": null_count,
    }


def is_regular_grid(df: pl.DataFrame, freq: str, ts_col: str = "timestamp") -> bool:
    """Return True if timestamp spacing is regular with the provided frequency."""

    report = validate_timestamp_series(df, ts_col=ts_col)
    if not report["ok"]:
        return False

    if df.height < 2:
        return True

    duration = _parse_duration(freq)
    if duration is None:
        raise ValueError(f"unsupported frequency '{freq}'")

    delta = df[ts_col].diff().dt.total_nanoseconds()
    diff = pl.DataFrame({"delta": delta})
    expected = duration.total_seconds() * 1_000_000_000
    cleaned = diff.filter(pl.col("delta").is_not_null())
    return cleaned["delta"].drop_nans().n_unique() <= 1 and (
        cleaned["delta"].drop_nans().max() == expected
    )


def ensure_regular_grid(df: pl.DataFrame, freq: str, ts_col: str = "timestamp") -> None:
    """Raise ValueError when the grid is not regular."""

    if not is_regular_grid(df, freq=freq, ts_col=ts_col):
        raise ValueError(f"timestamps are not regular at freq {freq}")


def to_timedelta(freq: str) -> timedelta:
    """Expose duration parser in timedelta format for docs and tests."""

    duration = _parse_duration(freq)
    if duration is None:
        raise ValueError(f"unsupported duration '{freq}'")
    return duration
