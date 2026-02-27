"""Storage helpers for raw and processed zones."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import Paths

_PRICE_META_SCHEMA_VERSION = "1.0.0"
_VALID_NAN_POLICIES = {"reject", "drop", "allow"}


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def validate_prices_df(
    frame: pd.DataFrame,
    *,
    min_rows: int = 1,
    nan_policy: str = "reject",
) -> pd.DataFrame:
    """Validate a normalized OHLCV frame before persisting.

    Policy:
    - ``reject``: fail when any null appears in required columns.
    - ``drop``: drop null rows in required columns (warned through returned shape).
    - ``allow``: do not enforce null constraints.
    """
    required = ["ts_utc", "open", "high", "low", "close", "volume"]

    missing = [col for col in required if col not in frame.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas: {missing}")

    if nan_policy not in _VALID_NAN_POLICIES:
        raise ValueError(f"nan_policy inválida: {nan_policy}. Use reject|drop|allow")

    normalized = frame.copy()

    normalized["ts_utc"] = pd.to_datetime(normalized["ts_utc"], utc=True, errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

    required_null_mask = normalized[required].isna().any(axis=1)
    if nan_policy == "reject" and required_null_mask.any():
        raise ValueError("validación rechazada: null en columnas OHLCV/ts_utc")
    if nan_policy == "drop":
        normalized = normalized.loc[~required_null_mask].copy()

    if normalized.empty:
        raise ValueError(f"validación rechazada: el dataset quedó vacío (min_rows={min_rows})")

    if len(normalized) < min_rows:
        raise ValueError(
            f"validación rechazada: filas={len(normalized)} menores al mínimo requerido min_rows={min_rows}"
        )

    times = normalized["ts_utc"]
    if times.isna().any():
        raise ValueError("validación rechazada: timestamps inválidos en ts_utc")

    if not times.is_monotonic_increasing:
        raise ValueError("validación rechazada: ts_utc debe ser monotónico ascendente")
    if times.duplicated().any():
        raise ValueError("validación rechazada: ts_utc debe ser único")

    ohlc = normalized[["open", "high", "low", "close"]]
    if (ohlc <= 0).any().any():
        raise ValueError("validación rechazada: open/high/low/close deben ser positivos")
    if (normalized["volume"] < 0).any():
        raise ValueError("validación rechazada: volume debe ser no negativo")
    if (normalized["open"] > normalized["high"]).any() or (normalized["close"] > normalized["high"]).any():
        raise ValueError("validación rechazada: high debe ser >= open y close")
    if (normalized["open"] < normalized["low"]).any() or (normalized["close"] < normalized["low"]).any():
        raise ValueError("validación rechazada: low debe ser <= open y close")

    return normalized.copy()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    temp_path = Path(raw_temp)
    os.close(fd)

    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def write_parquet_atomic(path: Path, frame: pd.DataFrame) -> None:
    """Write parquet file using atomic rename for crash-safe outputs."""
    temp_path: Path
    fd: int
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=False,
    )
    temp_path = Path(raw_temp)
    os.close(fd)

    try:
        frame.to_parquet(temp_path, index=False)
        os.replace(temp_path, path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise
    finally:
        if temp_path.exists():
            # if os.replace succeeded, this file should not exist anymore
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _write_price_meta(path: Path, frame: pd.DataFrame, provider: str) -> dict:
    meta_path = path.with_suffix(".meta.json")

    ts_min = pd.to_datetime(frame["ts_utc"].min(), utc=True)
    ts_max = pd.to_datetime(frame["ts_utc"].max(), utc=True)
    meta = {
        "schema_version": _PRICE_META_SCHEMA_VERSION,
        "provider": provider,
        "rows": int(len(frame)),
        "min_ts_utc": ts_min.isoformat(),
        "max_ts_utc": ts_max.isoformat(),
        "sha256": _sha256_file(path),
        "generated_at_utc": _utc_now().isoformat(),
    }
    _write_json_atomic(meta_path, meta)
    return meta


def write_parquet_with_metadata(
    path: Path,
    frame: pd.DataFrame,
    provider: str,
    *,
    min_rows: int = 1,
    nan_policy: str = "reject",
) -> tuple[Path, dict]:
    validated = validate_prices_df(frame, min_rows=min_rows, nan_policy=nan_policy)
    write_parquet_atomic(path, validated)
    meta = _write_price_meta(path, validated, provider)
    return path, meta


def write_price_metadata(path: Path, frame: pd.DataFrame, provider: str) -> dict:
    """Write metadata sidecar for an already-written parquet file."""
    return _write_price_meta(path, frame, provider)


def write_raw_dump(
    raw: pd.DataFrame,
    paths: Paths,
    source: str,
    symbol: str,
    timeframe: str,
    start: str,
    end: str,
    run_id: str,
) -> Path:
    destination = paths.raw_dir / source / symbol / timeframe
    destination.mkdir(parents=True, exist_ok=True)
    filename = f"{symbol}_{timeframe}_{start}_{end}_{run_id}.csv"
    out = destination / filename
    raw.to_csv(out)
    return out


def write_processed_parquet(
    frame: pd.DataFrame,
    paths: Paths,
    source: str,
    symbol: str,
    timeframe: str,
    run_id: str,
    *,
    min_rows: int = 1,
    nan_policy: str = "reject",
) -> Path:
    destination = paths.processed_dir / source / symbol / timeframe
    destination.mkdir(parents=True, exist_ok=True)

    start = pd.to_datetime(frame["ts_utc"].min()).strftime("%Y%m%d")
    end = pd.to_datetime(frame["ts_utc"].max()).strftime("%Y%m%d")
    filename = f"{symbol}_{timeframe}_{start}_{end}_{run_id}.parquet"
    path = destination / filename
    write_parquet_with_metadata(path=path, frame=frame, provider=source, min_rows=min_rows, nan_policy=nan_policy)
    return path


def write_ingest_manifest(path: Path, manifest: dict) -> None:
    _write_json_atomic(path, manifest)
