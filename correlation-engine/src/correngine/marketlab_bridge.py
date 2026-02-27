"""Adapters for marketlab-core dependencies with safe fallbacks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

try:
    from marketlab_core import (
        align as ml_align,
        compute_returns as ml_compute_returns,
        read_csv as ml_read_csv,
        read_parquet as ml_read_parquet,
        write_parquet as ml_write_parquet,
    )
    from marketlab_core import Cache as MLCache
except Exception:  # pragma: no cover - fallback when marketlab-core is unavailable
    ml_align = None
    ml_compute_returns = None
    ml_read_csv = None
    ml_read_parquet = None
    ml_write_parquet = None
    MLCache = None


def read_table(path: str | Path) -> pl.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        if ml_read_parquet is not None:
            return ml_read_parquet(path)
        return pl.read_parquet(path)
    if suffix == ".csv":
        if ml_read_csv is not None:
            return ml_read_csv(path)
        return pl.read_csv(path)
    raise ValueError(f"Formato no soportado para dataset: {path.suffix}")


def write_table(df: pl.DataFrame, path: str | Path) -> Path:
    if ml_write_parquet is not None:
        return ml_write_parquet(df, path)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(target)
    return target


def align_frames(frames: list[pl.DataFrame], *, ts_col: str) -> pl.DataFrame:
    if ml_align is None:
        if not frames:
            return pl.DataFrame()
        work = frames[0].sort(ts_col)
        for frame in frames[1:]:
            work = work.join(frame.sort(ts_col), on=ts_col, how="outer")
        return work.sort(ts_col)
    return ml_align(frames, ts_col=ts_col, how="outer", method="ffill")


def compute_returns_safe(df: pl.DataFrame, *, value_col: str, timestamp_col: str, out_col: str = "returns_1d") -> pl.DataFrame:
    if ml_compute_returns is not None:
        return ml_compute_returns(df, value_col=value_col, ts_col=timestamp_col, method="simple", horizon=1).rename(
            {f"{value_col}_simple_ret_1": out_col}
        )
    prev = pl.col(value_col).shift(1)
    ret = pl.when(prev.is_not_null() & (prev != 0)).then(pl.col(value_col) / prev - 1.0).otherwise(None).alias(out_col)
    return df.with_columns(ret)


def get_cache(root: str | Path):
    if MLCache is None:
        return _FallbackCache()
    return MLCache(root=Path(root).expanduser())


class _FallbackCache:
    """Cache no-op cuando no hay implementacion de marketlab-core."""

    def get(self, key: str) -> Any | None:
        return None

    def set(self, key: str, obj: Any, ttl: int | None = None) -> str:
        return str(key)

    def cache_info(self) -> dict:
        return {"entries": 0, "size_bytes": 0, "root": ""}
