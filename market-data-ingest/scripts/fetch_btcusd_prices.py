#!/usr/bin/env python3
"""Fetch BTC-USD historical OHLCV into the local processed parquet layout.

Defaults are aimed at producing a two-year daily history.
"""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import date, timedelta
from pathlib import Path
import sys

from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_data_ingest.config import Paths
from market_data_ingest.ingestion import run_download


def _default_start(days_back: int = 730) -> str:
    return (date.today() - timedelta(days=days_back)).isoformat()


def _publish_latest(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = f".{destination.name}.{uuid4().hex}.tmp"
    temp = destination.parent / tmp_name
    try:
        shutil.copy2(source, temp)
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


def fetch_btc_prices(
    symbol: str,
    start: str,
    end: str,
    timeframe: str,
    source: str,
    root: str,
    venue: str,
    exchange: str,
    publish_canonical: bool,
) -> list[Path]:
    paths = Paths.default(root)
    paths.create()

    report = run_download(
        paths=paths,
        symbols=symbol,
        start=start,
        end=end,
        timeframe=timeframe,
        source=source,
        exchange=exchange,
        venue=venue,
    )

    if not report:
        raise RuntimeError("No se pudo obtener data del source seleccionado.")

    outputs: list[Path] = []
    for row in report:
        processed = Path(str(row["processed_path"]))
        outputs.append(processed)

        if publish_canonical:
            canonical = paths.processed_dir / str(row["symbol"]) / f"{timeframe}.parquet"
            _publish_latest(processed, canonical)

    return outputs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga histórica de BTC-USD desde fuente libre (yfinance por defecto).")
    parser.add_argument(
        "--symbol",
        default="BTC-USD",
        help="Símbolo a descargar. Default: BTC-USD",
    )
    parser.add_argument(
        "--start",
        default=_default_start(),
        help="Inicio YYYY-MM-DD (por defecto: hace 730 días).",
    )
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="Fin YYYY-MM-DD (exclusivo). Default: hoy",
    )
    parser.add_argument(
        "--timeframe",
        default="1d",
        help="Timeframe: 1d, 1h, 5m, etc.",
    )
    parser.add_argument(
        "--source",
        default="yfinance",
        help="Fuente: yfinance | ccxt",
    )
    parser.add_argument(
        "--exchange",
        default="binance",
        help="Exchange para ccxt (si aplica).",
    )
    parser.add_argument(
        "--venue",
        default="",
        help="Venue opcional para normalización.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Raíz del repositorio market-data-ingest (contiene data/).",
    )
    parser.add_argument(
        "--publish-canonical",
        action="store_true",
        help="Publica además a data/processed/<symbol>/<timeframe>.parquet",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = fetch_btc_prices(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        timeframe=args.timeframe,
        source=args.source,
        root=args.root,
        venue=args.venue,
        exchange=args.exchange,
        publish_canonical=args.publish_canonical,
    )

    print("BTC precios generados:")
    for path in rows:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
