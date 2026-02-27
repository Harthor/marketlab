"""Generate synthetic OHLCV parquet files for local pipeline testing."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_data_ingest.config import Paths
from market_data_ingest.storage import (
    write_parquet_atomic,
    write_ingest_manifest,
    write_parquet_with_metadata,
    write_price_metadata,
)

TIMEFRAME_TO_PANDAS_FREQ = {
    "1m": "1min",
    "2m": "2min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1D",
    "1wk": "1W",
    "1mo": "1MS",
}


def _timeframe_to_freq(timeframe: str) -> str:
    freq = TIMEFRAME_TO_PANDAS_FREQ.get(timeframe)
    if freq is None:
        raise ValueError(
            "Timeframe '{timeframe}' no soportado para demo. Usá 1m, 2m, 5m, 15m, 30m, "
            "1h, 2h, 4h, 6h, 8h, 12h, 1d, 1wk o 1mo.".format(timeframe=timeframe)
        )
    return freq


def _row_checksum(row: pd.Series) -> str:
    parts = [
        str(row["ts_utc"]).replace("+00:00", "Z"),
        str(row["symbol"]),
        str(row["venue"]),
        str(row["timeframe"]),
        f"{row['open']:.8f}",
        f"{row['high']:.8f}",
        f"{row['low']:.8f}",
        f"{row['close']:.8f}",
        f"{row['volume']:.8f}",
    ]
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def generate_demo_frame(
    symbol: str,
    start: str,
    end: str,
    timeframe: str,
    venue: str = "NYSE",
    source: str = "demo",
    seed: int = 42,
    inject_gap: bool = False,
    inject_duplicate: bool = False,
    inject_null: bool = False,
) -> pd.DataFrame:
    freq = _timeframe_to_freq(timeframe)
    timestamps = pd.date_range(start=start, end=end, freq=freq, tz="UTC", inclusive="left")
    if len(timestamps) == 0:
        raise ValueError("El rango generado está vacío. Ajustá --start/--end.")

    if inject_gap and len(timestamps) >= 4:
        timestamps = timestamps.delete(len(timestamps) // 2)

    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=0.0, scale=0.35, size=len(timestamps))
    base = 100 + np.cumsum(np.concatenate(([0.0], steps[:-1])))

    open_series = base
    close_series = base + steps
    high_series = np.maximum(open_series, close_series) + np.abs(rng.normal(0.0, 0.2, size=len(timestamps)))
    low_series = np.minimum(open_series, close_series) - np.abs(rng.normal(0.0, 0.2, size=len(timestamps)))
    volume_series = np.clip(rng.normal(1200, 90, size=len(timestamps)), 10, None)

    frame = pd.DataFrame(
        {
            "ts_utc": timestamps,
            "symbol": symbol,
            "timeframe": timeframe,
            "open": open_series,
            "high": high_series,
            "low": low_series,
            "close": close_series,
            "volume": volume_series,
            "venue": venue,
            "source": source,
            "ingestion_ts": pd.Timestamp.now(tz=timezone.utc),
        }
    )

    if inject_null and len(frame) >= 2:
        frame.loc[frame.index[1], "close"] = np.nan

    if inject_duplicate and not frame.empty:
        frame = pd.concat([frame, frame.iloc[[0]].copy()], ignore_index=True)

    frame["checksum"] = frame.apply(_row_checksum, axis=1)
    return frame.sort_values("ts_utc").reset_index(drop=True)


def _publish_latest(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.parent / f".{destination.name}.{uuid4().hex}.tmp"
    try:
        shutil.copy2(source, temp)
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


def _write_parquet(path: Path, frame: pd.DataFrame) -> None:
    try:
        write_parquet_atomic(path, frame)
    except (ImportError, ValueError, RuntimeError) as exc:
        raise RuntimeError(
            "No se pudo guardar parquet. Instalá uno de los motores: `pip install pyarrow` "
            "(recomendado) o `pip install fastparquet`."
        ) from exc


def _write_parquet_with_meta(path: Path, frame: pd.DataFrame, provider: str) -> dict[str, object]:
    _write_parquet(path, frame)
    return write_price_metadata(path, frame, provider=provider)


def generate_demo_prices(
    symbols: Iterable[str],
    start: str,
    end: str,
    timeframe: str,
    root: str | Path = ".",
    venue: str = "NYSE",
    seed: int = 42,
    inject_gap: bool = False,
    inject_duplicate: bool = False,
    inject_null: bool = False,
    write_contract_layout: bool = False,
    contract_root: str | Path | None = None,
    run_id: str | None = None,
    publish_latest: bool = False,
) -> dict[str, Path]:
    paths = Paths.default(root)
    paths.create()
    out = {}
    artifacts: list[dict[str, object]] = []
    total_rows = 0
    effective_run_id = run_id
    manifest_path = paths.processed_dir / "ingest_summary.json"
    warnings: list[str] = []
    errors: list[str] = []
    started_at = datetime.now(timezone.utc).isoformat()

    for symbol in symbols:
        frame = generate_demo_frame(
            symbol=symbol,
            start=start,
            end=end,
            timeframe=timeframe,
            venue=venue,
            seed=seed,
            inject_gap=inject_gap,
            inject_duplicate=inject_duplicate,
            inject_null=inject_null,
        )

        run_dir = paths.processed_dir / "runs" / effective_run_id if effective_run_id else None
        primary_path = (
            run_dir / symbol / f"{timeframe}.parquet"
            if run_dir is not None
            else paths.processed_dir / symbol / f"{timeframe}.parquet"
        )
        primary_path.parent.mkdir(parents=True, exist_ok=True)

        warning_lines: list[str] = []
        if inject_gap:
            warning_lines.append("inject_gap")
        if inject_duplicate:
            warning_lines.append("inject_duplicate")
        if inject_null:
            warning_lines.append("inject_null")
        if warning_lines:
            warnings.append(f"{symbol}: {', '.join(warning_lines)}")

        meta: dict[str, object] = {}
        published_path = primary_path
        try:
            if warning_lines:
                _write_parquet_with_meta(primary_path, frame, provider="demo")
            else:
                # for clean runs, validate through write_parquet_with_metadata to keep a consistent guardrail.
                _, meta = write_parquet_with_metadata(primary_path, frame, provider="demo")
            meta = meta or {}
            total_rows += len(frame)
            artifact_status = "complete"
        except Exception as exc:
            error = f"{symbol}: failed writing demo parquet: {exc}"
            errors.append(error)
            artifact_status = "partial"
            artifacts.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "provider": "demo",
                    "status": "partial",
                    "rows": 0,
                    "dataset_path": str(primary_path),
                    "meta_path": str(primary_path.with_suffix(".meta.json")),
                    "dataset_hash": None,
                    "warnings": warning_lines,
                    "errors": [str(error)],
                }
            )
            out[symbol] = primary_path
            continue

        if not meta:
            try:
                meta = write_price_metadata(primary_path, frame, provider="demo")
            except Exception as meta_exc:
                errors.append(f"{symbol}: failed metadata write: {meta_exc}")
                artifact_status = "partial"

        if publish_latest:
            published_path = paths.processed_dir / symbol / f"{timeframe}.parquet"
            _publish_latest(primary_path, published_path)

        out[symbol] = published_path

        if write_contract_layout:
            contract_root_path = Path(
                contract_root
                if contract_root is not None
                else os.getenv("MARKETLAB_DATA_ROOT", str(paths.root / "data" / "clean" / "prices"))
            )
            contract_path = contract_root_path / symbol / timeframe / "part-00000.parquet"
            contract_frame = frame[["ts_utc", "symbol", "timeframe", "open", "high", "low", "close", "volume"]].copy()
            contract_frame = contract_frame.rename(columns={"ts_utc": "timestamp"})
            contract_path.parent.mkdir(parents=True, exist_ok=True)
            _write_parquet(contract_path, contract_frame)

        artifacts.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "provider": "demo",
                "status": artifact_status,
                "rows": int(len(frame)),
                "dataset_path": str(published_path),
                "meta_path": str(primary_path.with_suffix(".meta.json")),
                "dataset_hash": meta.get("sha256") if meta else None,
                "artifacts": {
                    "parquet_path": str(published_path),
                    "run_path": str(primary_path),
                    "meta_path": str(primary_path.with_suffix(".meta.json")),
                },
                "warnings": warning_lines,
                "errors": [],
            }
        )

    if not artifacts:
        status = "skipped"
    elif errors:
        status = "partial"
    elif any(item.get("status") == "skipped" for item in artifacts):
        status = "partial"
    elif any(item.get("status") == "partial" for item in artifacts):
        status = "partial"
    else:
        status = "complete"

    manifest = {
        "kind": "ingest",
        "status": status,
        "provider": "demo",
        "run_id": effective_run_id,
        "started_at_utc": started_at,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": int(total_rows),
        "artifacts": artifacts,
        "warnings": warnings,
        "errors": errors,
    }
    write_ingest_manifest(manifest_path, manifest)

    return out


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera OHLCV sintético para pruebas locales y pipeline offline."
    )
    parser.add_argument("--symbols", default="AAPL", help="Símbolos separados por coma. Ej: AAPL,MSFT")
    parser.add_argument("--start", default="2024-01-01", help="Inicio (YYYY-MM-DD)")
    parser.add_argument("--end", default="2024-01-10", help="Fin exclusivo (YYYY-MM-DD)")
    parser.add_argument("--timeframe", default="1d", help="Timeframe: 1m, 5m, 1h, 1d, 1wk, 1mo")
    parser.add_argument("--root", default=".", help="Raíz del repo. Si omitís, usa el cwd actual.")
    parser.add_argument("--venue", default="NYSE", help="Venue del output. Ej: NYSE, NASDAQ")
    parser.add_argument("--seed", type=int, default=42, help="Seed reproducible")
    parser.add_argument("--inject-gap", action="store_true", help="Inyectar un hueco temporal")
    parser.add_argument("--inject-duplicate", action="store_true", help="Inyectar fila duplicada")
    parser.add_argument("--inject-null", action="store_true", help="Inyectar valores nulos")
    parser.add_argument(
        "--write-contract-layout",
        action="store_true",
        help="Generar además el layout recomendado por marketlab-core (data/clean/prices/<symbol>/<timeframe>).",
    )
    parser.add_argument(
        "--contract-root",
        default=None,
        help="Ruta base para layout contrato (por defecto MARKETLAB_DATA_ROOT o <root>/data/clean/prices)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Identificador opcional de corrida para aislar escrituras concurrentes.",
    )
    parser.add_argument(
        "--publish-latest",
        action="store_true",
        help="Publica al path canonical con reemplazo atómico (`data/processed/<symbol>/<timeframe>.parquet`).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]

    written: dict[str, Path] = generate_demo_prices(
        symbols=symbols,
        start=args.start,
        end=args.end,
        timeframe=args.timeframe,
        root=args.root,
        venue=args.venue,
        seed=args.seed,
        inject_gap=args.inject_gap,
        inject_duplicate=args.inject_duplicate,
        inject_null=args.inject_null,
        write_contract_layout=args.write_contract_layout,
        contract_root=args.contract_root,
        run_id=args.run_id,
        publish_latest=args.publish_latest,
    )

    if not written:
        print("No se generó ningún archivo")
        return

    print("Parquet(s) sintético(s) generados:")
    for symbol, path in written.items():
        print(f"  {symbol}: {path}")


if __name__ == "__main__":
    main()
