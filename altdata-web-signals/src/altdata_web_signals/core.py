"""Thin compatibility layer for marketlab-core primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha1
from pathlib import Path
from typing import Any, cast

import polars as pl

try:  # pragma: no cover - depende de si package está instalado en el entorno
    from marketlab_core import Cache as _CoreCache
    from marketlab_core import align as _align
    from marketlab_core import compute_returns as _compute_returns
    from marketlab_core import normalize_timezone as _normalize_timezone
except Exception:  # pragma: no cover
    _CoreCache = None
    _align = None
    _compute_returns = None
    _normalize_timezone = None


@dataclass
class FallbackCache:
    """Pequeña cache local compatible con la API pública de marketlab-core.Cache."""

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.data_root = self.root / "data"
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.index = self.data_root / "index.txt"
        if not self.index.exists():
            self.index.touch()

    def _paths(self) -> Path:
        return self.data_root

    def _safe_key(self, key: str) -> str:
        return sha1(key.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        path = self._paths() / f"{self._safe_key(key)}.pkl"
        if not path.exists():
            return None
        try:
            with path.open("rb") as handle:
                import pickle

                value = pickle.load(handle)
            return value
        except Exception:
            path.unlink(missing_ok=True)
            return None

    def set(self, key: str, obj: Any, ttl: int | timedelta | None = None) -> str:
        path = self._paths() / f"{self._safe_key(key)}.pkl"
        try:
            with path.open("wb") as handle:
                import pickle

                pickle.dump(obj, handle)
        except Exception:
            # si falla por permisos, sigue sin romper el flujo del fetcher
            return key
        return key

    def delete(self, key: str) -> None:
        path = self._paths() / f"{self._safe_key(key)}.pkl"
        path.unlink(missing_ok=True)



def make_cache(cache_root: str | Path) -> Any:
    if _CoreCache is not None:
        return _CoreCache(root=cache_root)
    return FallbackCache(Path(cache_root))


def normalize_timezone(frame: pl.DataFrame, ts_col: str = "ts_utc", timezone: str = "UTC") -> pl.DataFrame:
    if _normalize_timezone is None:
        return frame.with_columns(pl.col(ts_col).dt.replace_time_zone(timezone).alias(ts_col))
    return _normalize_timezone(frame, ts_col=ts_col, timezone=timezone)


def align_frames(
    frames: list[pl.DataFrame],
    *,
    how: str = "outer",
    freq: str = "1d",
    method: str = "none",
    ts_col: str = "ts_utc",
) -> pl.DataFrame:
    if not frames:
        return pl.DataFrame()
    base = frames[0]
    aligned = base
    for frame in frames[1:]:
        join_how = "full" if how == "outer" else how
        if ts_col not in frame.columns:
            continue
        right = frame.rename({ts_col: f"{ts_col}_right"})
        aligned = aligned.join(
            right,
            left_on=ts_col,
            right_on=f"{ts_col}_right",
            how=cast(Any, join_how),
        )
        if f"{ts_col}_right" in aligned.columns:
            aligned = aligned.with_columns(pl.col(f"{ts_col}_right").alias(ts_col)).drop(f"{ts_col}_right")
    return aligned.sort(ts_col)


def compute_returns(
    frame: pl.DataFrame,
    value_col: str,
    *,
    ts_col: str = "ts_utc",
    method: str = "simple",
    horizon: int = 1,
    out_col: str | None = None,
) -> pl.DataFrame:
    if _compute_returns is not None:
        return _compute_returns(
            frame,
            value_col=value_col,
            ts_col=ts_col,
            method=method,
            horizon=horizon,
            out_col=out_col,
        )

    if value_col not in frame.columns:
        raise KeyError(f"Missing value column '{value_col}'")
    if out_col is None:
        out_col = f"{value_col}_{method}_ret_{horizon}"

    expr = (pl.col(value_col) / pl.col(value_col).shift(horizon) - 1).alias(out_col)
    return frame.sort(ts_col).with_columns(expr)
