"""Quality checks for normalized/warehouse price data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pandas as pd

from .config import Paths

TIMEFRAME_ALIASES = {
    "1m": "1T",
    "2m": "2T",
    "5m": "5T",
    "15m": "15T",
    "30m": "30T",
    "1h": "1H",
    "2h": "2H",
    "4h": "4H",
    "6h": "6H",
    "8h": "8H",
    "12h": "12H",
    "1d": "1D",
    "1wk": "1W",
    "1mo": "1MS",
}


@dataclass
class SymbolQuality:
    symbol: str
    timeframe: str
    rows: int
    venue: str
    date_min: str | None
    date_max: str | None
    duplicates: int
    null_rows: int
    missing_timestamps: int
    suspicious_gaps: int
    outliers: int


def _expected_freq(timeframe: str) -> str | None:
    return TIMEFRAME_ALIASES.get(timeframe.lower())


def _to_timedelta(timeframe: str) -> timedelta | None:
    freq = _expected_freq(timeframe)
    if not freq:
        return None
    offset = pd.tseries.frequencies.to_offset(freq)
    if offset is None:
        return None
    # pd.to_timedelta(offset) fails for DateOffset subclasses in pandas 2.x;
    # use nanos attribute which works for all fixed-frequency offsets.
    return pd.Timedelta(offset.nanos)


def _calendar_expected_times(start: pd.Timestamp, end: pd.Timestamp, timeframe: str, venue: str) -> pd.DatetimeIndex | None:
    if timeframe.lower() != "1d":
        return None
    if venue.upper() not in {"NYSE", "NASDAQ", "XNAS"}:
        return None

    try:
        import pandas_market_calendars as mcal
    except ImportError:
        return None

    try:
        calendar = mcal.get_calendar("NYSE")
    except Exception:
        return None

    schedule = calendar.schedule(start_date=start.normalize(), end_date=end.normalize())
    trading_days = pd.DatetimeIndex(schedule.index.tz_localize("UTC")).tz_convert("UTC")
    return trading_days


def _collect_processed_parquet_files(processed_dir: Path) -> list[Path]:
    return [p for p in processed_dir.glob("**/*.parquet") if p.is_file()]


def _read_from_processed_paths(processed_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in _collect_processed_parquet_files(processed_dir):
        try:
            frame = pd.read_parquet(path)
        except Exception:
            continue
        frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=["ts_utc", "symbol", "timeframe", "venue", "open", "high", "low", "close", "volume"])

    return pd.concat(frames, ignore_index=True)


def _normalize_quality_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()

    if "timestamp" in normalized.columns and "ts_utc" not in normalized.columns:
        normalized["ts_utc"] = pd.to_datetime(normalized["timestamp"], utc=True, errors="coerce")
    elif "ts_utc" in normalized.columns:
        normalized["ts_utc"] = pd.to_datetime(normalized["ts_utc"], utc=True, errors="coerce")
    else:
        normalized["ts_utc"] = pd.NaT

    if "symbol" not in normalized.columns:
        normalized["symbol"] = pd.NA
    if "timeframe" not in normalized.columns:
        normalized["timeframe"] = "1d"
    if "venue" not in normalized.columns:
        normalized["venue"] = "UNKNOWN"

    for col in ["open", "high", "low", "close", "volume"]:
        if col in normalized.columns:
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce")
        else:
            normalized[col] = pd.NA

    return normalized


def _run_quality_metrics(group: pd.DataFrame) -> tuple[int, int, int, int]:
    times = pd.to_datetime(group["ts_utc"], utc=True, errors="coerce")
    expected_freq = _expected_freq(str(group["timeframe"].iloc[0]))
    expected_delta = _to_timedelta(str(group["timeframe"].iloc[0]))

    duplicates = int(times.duplicated().sum())
    null_rows = int(
        group[["ts_utc", "open", "high", "low", "close", "volume"]]
        .isna()
        .any(axis=1)
        .sum()
    )

    valid_times = times.dropna().sort_values()
    if valid_times.empty:
        return duplicates, null_rows, 0, 0

    if expected_delta is None:
        return duplicates, null_rows, 0, 0

    venue = str(group["venue"].iloc[0]) if "venue" in group.columns else "UNKNOWN"
    expected = _calendar_expected_times(valid_times.min(), valid_times.max(), str(group["timeframe"].iloc[0]), venue)

    if expected is None:
        expected = pd.date_range(
            start=valid_times.min(),
            end=valid_times.max(),
            freq=expected_freq,
            tz="UTC",
        )

    observed = pd.DatetimeIndex(valid_times.drop_duplicates())
    missing = int(max(0, len(expected) - len(expected.intersection(observed))))
    deltas = valid_times.diff().dropna().dt.total_seconds()
    suspicious_gaps = int((deltas > (expected_delta.total_seconds() * 1.5)).sum())

    return duplicates, null_rows, missing, suspicious_gaps


def _run_outliers(group: pd.DataFrame) -> int:
    invalid = (
        (group[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (group["high"] < group["low"])
    )

    returns = group["close"].pct_change(fill_method=None).abs()
    outlier_moves = returns > 0.5
    return int((invalid | outlier_moves).sum())


def _read_quality_source(paths: Paths) -> pd.DataFrame | None:
    try:
        import duckdb
    except ModuleNotFoundError:
        return None

    conn = None
    try:
        conn = duckdb.connect(str(paths.warehouse_path))
        query = """
            SELECT
                symbol,
                venue,
                timeframe,
                ts_utc,
                open,
                high,
                low,
                close,
                volume
            FROM prices
            ORDER BY symbol, timeframe, ts_utc
        """
        data = conn.execute(query).df()
        return data
    except Exception:
        return None
    finally:
        if conn is not None:
            conn.close()


def quality_report(paths: Paths) -> list[SymbolQuality]:
    data = _read_quality_source(paths)
    if data is None:
        data = _read_from_processed_paths(paths.processed_dir)

    data = _normalize_quality_frame(data)
    if data.empty:
        return []

    data = data.dropna(subset=["symbol", "timeframe"])
    if data.empty:
        return []

    reports: list[SymbolQuality] = []
    for (symbol, timeframe), group in data.groupby(["symbol", "timeframe"]):
        group = group.copy()
        duplicates, null_rows, missing, gaps = _run_quality_metrics(group)
        outliers = _run_outliers(group)

        reports.append(
            SymbolQuality(
                symbol=str(symbol),
                timeframe=str(timeframe),
                rows=int(len(group)),
                venue=str(group["venue"].iloc[0]) if "venue" in group.columns else "UNKNOWN",
                date_min=group["ts_utc"].min().isoformat() if not group.empty else None,
                date_max=group["ts_utc"].max().isoformat() if not group.empty else None,
                duplicates=duplicates,
                null_rows=null_rows,
                missing_timestamps=missing,
                suspicious_gaps=gaps,
                outliers=outliers,
            )
        )

    return reports
