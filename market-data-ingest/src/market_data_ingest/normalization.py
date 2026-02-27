"""Normalization utilities: convert raw OHLCV into canonical schema."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

CANONICAL_COLUMNS: list[str] = [
    "ts_utc",
    "symbol",
    "venue",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "ingestion_ts",
    "checksum",
]


def _to_series_checksum(row: pd.Series) -> str:
    parts = [
        str(row["ts_utc"]).replace("+00:00", "Z"),
        row["symbol"],
        row["venue"],
        row["timeframe"],
        f"{row['open']:.8f}",
        f"{row['high']:.8f}",
        f"{row['low']:.8f}",
        f"{row['close']:.8f}",
        f"{row['volume']:.8f}",
    ]
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def _ensure_columns(df: pd.DataFrame, required: Iterable[str]) -> pd.DataFrame:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas para normalizar: {missing}")
    return df[required].copy()


def normalize_ohlcv(
    raw: pd.DataFrame,
    symbol: str,
    venue: str,
    timeframe: str,
    source: str,
    ingestion_ts: datetime | None = None,
) -> pd.DataFrame:
    """Normalize raw connector output to canonical schema.

    Accepts:
    - DataFrame indexed by timestamps or with `timestamp` column
    - Columns open/high/low/close/volume in any case
    """
    if ingestion_ts is None:
        ingestion_ts = datetime.now(tz=timezone.utc)

    if raw is None or raw.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    frame = raw.copy()

    frame.columns = [c.lower().strip() for c in frame.columns]
    frame = _ensure_columns(frame, ["open", "high", "low", "close", "volume"])

    if isinstance(frame.index, pd.DatetimeIndex):
        ts = frame.index
    elif "timestamp" in frame.columns:
        ts = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.drop(columns=["timestamp"])
    else:
        raise ValueError("La tabla raw no tiene índice Datetime ni columna 'timestamp'.")

    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    normalized = frame.copy()
    normalized["ts_utc"] = ts
    normalized["symbol"] = symbol
    normalized["venue"] = venue
    normalized["timeframe"] = timeframe
    normalized["source"] = source
    normalized["ingestion_ts"] = pd.Timestamp(ingestion_ts)

    for col in ["open", "high", "low", "close", "volume"]:
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

    normalized = normalized.dropna(subset=["open", "high", "low", "close", "volume", "ts_utc"])
    normalized = normalized.sort_values("ts_utc").reset_index(drop=True)

    checksums = normalized.apply(_to_series_checksum, axis=1)
    normalized["checksum"] = checksums

    output = normalized.reindex(columns=CANONICAL_COLUMNS)
    return output
