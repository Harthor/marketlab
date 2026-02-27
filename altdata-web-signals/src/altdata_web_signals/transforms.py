"""Shared stationarity transforms for signal builders."""

from __future__ import annotations

import polars as pl


def add_delta(df: pl.DataFrame, col: str) -> pl.DataFrame:
    """Add absolute delta (diff) column."""
    return df.with_columns(
        (pl.col(col) - pl.col(col).shift(1)).alias(f"{col}_delta"),
    )


def add_pct_change(df: pl.DataFrame, col: str, *, winsorize: bool = True) -> pl.DataFrame:
    """Add percent-change column, optionally winsorized to [-1, 1]."""
    expr = pl.col(col).pct_change().alias(f"{col}_pct_change")
    df = df.with_columns(expr)
    if winsorize:
        df = df.with_columns(
            pl.col(f"{col}_pct_change").clip(-1.0, 1.0).alias(f"{col}_pct_change"),
        )
    return df


def add_delta_and_pct(df: pl.DataFrame, col: str) -> pl.DataFrame:
    """Add both delta and winsorized pct_change for a numeric column."""
    df = add_delta(df, col)
    df = add_pct_change(df, col)
    return df


def add_delta_log1p(df: pl.DataFrame, col: str) -> pl.DataFrame:
    """For counts: use log1p delta instead of pct_change (handles 0 base).

    Adds ``{col}_log1p`` and ``{col}_delta_log1p``.
    """
    log1p_col = f"{col}_log1p"
    delta_col = f"{col}_delta_log1p"
    return df.with_columns(
        (pl.col(col).cast(pl.Float64) + 1.0).log().alias(log1p_col),
    ).with_columns(
        (pl.col(log1p_col) - pl.col(log1p_col).shift(1)).alias(delta_col),
    )


def add_zscore_rolling(df: pl.DataFrame, col: str, window: int) -> pl.DataFrame:
    """Add z-score with rolling window."""
    return df.with_columns(
        (
            (pl.col(col) - pl.col(col).rolling_mean(window_size=window))
            / pl.col(col).rolling_std(window_size=window)
        ).alias(f"{col}_zscore_{window}d"),
    )


def add_asof_utc(df: pl.DataFrame, offset_days: int = 1) -> pl.DataFrame:
    """Add ``asof_utc`` = ts_utc + offset_days (when data is available)."""
    return df.with_columns(
        (pl.col("ts_utc") + pl.duration(days=offset_days)).alias("asof_utc"),
    )
