"""Dataset assembly for research-ready signal + return tables."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version as _pkg_version

import polars as pl

from .config import PathConfig, slugify_topic
from .core import align_frames, compute_returns
from .storage import list_signal_frames


SCHEMA_VERSION = "2.0.0"


def _find_price_file(root: str | Path, symbol: str, freq: str, source: str = "yfinance") -> Path:
    root_path = Path(root) / source / symbol / freq
    candidates = sorted(root_path.glob("*.parquet"))
    if not candidates:
        root_path = Path(root) / symbol / freq
        candidates = sorted(root_path.glob("*.parquet"))
    if not candidates:
        legacy_file = Path(root) / symbol / f"{freq}.parquet"
        if legacy_file.exists():
            return legacy_file
        raise FileNotFoundError(
            "No se encontró parquet de precios. Verificar rutas:\n"
            f"- {Path(root) / source / symbol / freq}\n"
            f"- {Path(root) / symbol / freq}\n"
            f"- {Path(root) / symbol / f'{freq}.parquet'}"
        )
    # el parquet más reciente suele ser el último por nombre de run_id/rango
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _load_price_series(path: Path) -> pl.DataFrame:
    frame = pl.read_parquet(path)

    if "ts_utc" not in frame.columns and "timestamp" in frame.columns:
        frame = frame.with_columns(pl.col("timestamp").alias("ts_utc"))
    if "ts_utc" not in frame.columns:
        raise ValueError(f"Parquet de precios inválido (faltan columnas): {path}")
    if "close" not in frame.columns:
        raise ValueError(f"Parquet de precios inválido (faltan columnas): {path}")

    available_cols = [col for col in ["ts_utc", "close", "symbol"] if col in frame.columns]
    if "symbol" in frame.columns:
        return frame.select(available_cols)
    return frame.select([col for col in ["ts_utc", "close"]])


def _returns_definition(method: str, horizon: int) -> str:
    if method == "log":
        return f"returns_1d = ln(close / close.shift({horizon}))"
    return f"returns_1d = close / close.shift({horizon}) - 1"


def _coverage_column_name(signal_col: str) -> str:
    return f"coverage_{signal_col}"


def _parse_datetime(value: str | None, *, end: bool = False) -> datetime | None:
    if value is None:
        return None

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if end and "T" not in value:
        parsed = (parsed + timedelta(days=1)).replace(microsecond=0) - timedelta(microseconds=1)
    return parsed


def _normalize_signal_frame(
    frame: pl.DataFrame,
    source: str,
    topic: str,
) -> pl.DataFrame:
    if "ts_utc" not in frame.columns and "timestamp" in frame.columns:
        frame = frame.with_columns(pl.col("timestamp").alias("ts_utc"))
    if "ts_utc" not in frame.columns:
        raise ValueError(f"Frame de señal sin columna ts_utc en {source}/{topic}")

    signal_cols = [col for col in frame.columns if col != "ts_utc"]
    if not signal_cols:
        raise ValueError(f"Frame de señal vacío en {source}/{topic}")

    target_col = signal_cols[0]
    canonical_col = f"signal_{slugify_topic(source)}_{slugify_topic(topic)}"
    if canonical_col not in frame.columns:
        frame = frame.rename({target_col: canonical_col})
        signal_cols = [canonical_col]
    else:
        signal_cols = [canonical_col]

    return frame.select(["ts_utc"] + signal_cols)


def _read_signal_frames(paths: list[Path], *, freq: str, start: datetime | None, end: datetime | None) -> tuple[list[pl.DataFrame], dict[str, list[str]], set[str]]:
    frames: list[pl.DataFrame] = []
    topics_by_source: dict[str, list[str]] = {}
    signal_sources: set[str] = set()

    for signal_path in paths:
        if signal_path.name != f"{freq}.parquet":
            continue

        source = signal_path.parent.parent.name
        topic = signal_path.parent.name
        topics_by_source.setdefault(source, [])
        if topic not in topics_by_source[source]:
            topics_by_source[source].append(topic)
        signal_sources.add(source)

        frame = pl.read_parquet(signal_path)
        frame = _normalize_signal_frame(frame, source=source, topic=topic)
        if start is not None:
            frame = frame.filter(pl.col("ts_utc") >= start)
        if end is not None:
            frame = frame.filter(pl.col("ts_utc") <= end)

        frames.append(frame)

    for values in topics_by_source.values():
        values.sort()
    return frames, topics_by_source, signal_sources


def _resolve_version() -> str:
    try:
        return _pkg_version("altdata-web-signals")
    except PackageNotFoundError:
        from . import __version__

        return __version__


def _dataset_columns(frame: pl.DataFrame) -> list[str]:
    signal_cols = sorted([col for col in frame.columns if col.startswith("signal_")])
    coverage_cols = [col for col in frame.columns if col.startswith("coverage_signal_")]
    base_cols = ["ts_utc", "symbol", "close", "returns_1d"]
    return base_cols + signal_cols + coverage_cols


def build_research_dataset(
    symbol: str,
    *,
    freq: str = "1d",
    join: str = "inner",
    fill_method: str = "none",
    returns_method: str = "simple",
    returns_horizon: int = 1,
    signals_root: str | Path = "data/signals",
    prices_root: str | Path = "../market-data-ingest/data/processed",
    price_source: str = "yfinance",
    datasets_root: str | Path = "data/datasets",
    start: str | None = None,
    end: str | None = None,
):
    fill_method = fill_method.lower().strip()
    if fill_method not in {"none", "forward", "backward"}:
        raise ValueError("fill_method inválido: use none|forward|backward")

    returns_method = returns_method.strip().lower()
    if returns_method not in {"simple", "log"}:
        raise ValueError("returns_method inválido: use simple|log")
    if str(prices_root) == "../market-data-ingest/data/processed":
        prices_root = PathConfig.default().market_data_root

    price_file = _find_price_file(prices_root, symbol=symbol, freq=freq, source=price_source)
    prices = _load_price_series(price_file)
    if "symbol" not in prices.columns:
        prices = prices.with_columns(pl.lit(symbol).alias("symbol"))
    else:
        prices = prices.filter(pl.col("symbol") == symbol)
    if prices.is_empty():
        raise ValueError(f"No hay precios para {symbol} en {price_file}")

    if returns_method == "simple":
        prices = compute_returns(
            prices,
            value_col="close",
            ts_col="ts_utc",
            method="simple",
            horizon=returns_horizon,
            out_col="returns_1d",
        )
    else:
        prices = prices.with_columns(
            (pl.col("close").log() - pl.col("close").shift(returns_horizon).log()).alias("returns_1d")
        )

    start_ts = _parse_datetime(start, end=False)
    end_ts = _parse_datetime(end, end=True)
    if start_ts is not None:
        prices = prices.filter(pl.col("ts_utc") >= start_ts)
    if end_ts is not None:
        prices = prices.filter(pl.col("ts_utc") <= end_ts)

    frames: list[pl.DataFrame] = [prices]
    signal_frames, topics_by_source, signal_sources = _read_signal_frames(
        paths=list_signal_frames(signals_root, freq=freq),
        freq=freq,
        start=start_ts,
        end=end_ts,
    )
    frames.extend(signal_frames)

    if len(frames) == 1:
        aligned = frames[0]
    else:
        aligned = align_frames(
            frames,
            how=join,
            freq=freq,
            method="none" if fill_method == "none" else fill_method,
            ts_col="ts_utc",
        )

    signal_columns = sorted([col for col in aligned.columns if col.startswith("signal_")])
    coverage_columns: list[str] = []
    if signal_columns:
        for col in signal_columns:
            coverage_col = _coverage_column_name(col)
            coverage_columns.append(coverage_col)
            aligned = aligned.with_columns(
                pl.when(pl.col(col).is_not_null())
                .then(1)
                .otherwise(0)
                .cast(pl.Int8)
                .alias(coverage_col)
            )
        if fill_method in {"forward", "backward"}:
            fill_exprs = [
                pl.col(col).fill_null(strategy="forward" if fill_method == "forward" else "backward").alias(col)
                for col in signal_columns
            ]
            aligned = aligned.with_columns(fill_exprs)

    dataset = aligned.select(_dataset_columns(aligned)).sort("ts_utc").drop_nulls(subset=["returns_1d"])

    missingness: dict[str, dict[str, float | int | None]] = {}
    for signal_col in signal_columns:
        coverage_col = _coverage_column_name(signal_col)
        if coverage_col not in dataset.columns or dataset.height == 0:
            missingness[signal_col] = {
                "rows": int(dataset.height),
                "coverage_count": 0,
                "coverage_ratio": 0.0,
            }
            continue
        cov_sum = int(dataset.select(pl.col(coverage_col).sum()).item(0, 0))
        ratio = float(cov_sum / dataset.height) if dataset.height else 0.0
        missingness[signal_col] = {
            "rows": int(dataset.height),
            "coverage_count": int(cov_sum),
            "coverage_ratio": ratio,
        }

    # mantener consistencia de señales sin drops de filas por cobertura
    # (las filas con 0 se mantienen y quedan trazables por coverage_*)

    out_root = Path(datasets_root)
    out_root.mkdir(parents=True, exist_ok=True)
    dataset_path = out_root / symbol / f"{freq}.parquet"
    meta_path = out_root / symbol / f"{freq}.meta.json"
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_parquet(dataset_path)

    ts_range: dict[str, str | None] = {"start": None, "end": None}
    if len(dataset) > 0:
        start_value = dataset["ts_utc"].min()
        end_value = dataset["ts_utc"].max()
        if start_value is not None and end_value is not None:
            ts_range["start"] = str(start_value)
            ts_range["end"] = str(end_value)

    dataset_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()

    ordered_signals = []
    for source in sorted(signal_sources):
        for topic in topics_by_source.get(source, []):
            topic_slug = slugify_topic(topic)
            ordered_signals.append(
                {
                    "source": source,
                    "topic": topic,
                    "topic_slug": topic_slug,
                    "keyword": topic_slug,
                }
            )

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "freq": freq,
        "sources": sorted(signal_sources),
        "topics": topics_by_source,
        "keywords": topics_by_source,
        "signals": ordered_signals,
        "ts_range": ts_range,
        "date_range": ts_range,
        "join_mode": join,
        "fill_method": fill_method,
        "returns_method": returns_method,
        "returns_horizon": returns_horizon,
        "returns_def": {
            "method": returns_method,
            "horizon": returns_horizon,
            "definition": _returns_definition(returns_method, returns_horizon),
        },
        "returns_1d": _returns_definition(returns_method, returns_horizon),
        "missingness": missingness,
        "dataset_hash": dataset_hash,
        "code_version": _resolve_version(),
        "rows": dataset.height,
        "start_arg": start,
        "end_arg": end,
        "coverage_columns": coverage_columns,
    }

    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return dataset_path
