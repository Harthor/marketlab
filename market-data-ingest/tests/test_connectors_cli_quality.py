"""Integration-style tests over mocked connectors, CLI, y calidad."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

if "duckdb" not in sys.modules:
    sys.modules["duckdb"] = types.ModuleType("duckdb")

from market_data_ingest import ingestion
from market_data_ingest.config import Paths
from market_data_ingest.connectors.ccxt_connector import CCXTConnector
from market_data_ingest.quality import _run_quality_metrics, _run_outliers


class FakeConnector:
    def __init__(self) -> None:
        self.fetched = []

    @property
    def venue(self) -> str:
        return "MOCK"

    def fetch_ohlcv(self, symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
        self.fetched.append((symbol, timeframe, start, end))
        idx = pd.date_range(start, end, freq="D", inclusive="left")
        return pd.DataFrame(
            {
                "Open": [10.0] * len(idx),
                "High": [11.0] * len(idx),
                "Low": [9.5] * len(idx),
                "Close": [10.5] * len(idx),
                "Volume": [1200] * len(idx),
            },
            index=idx,
        )


class TestConnectorAndCli(unittest.TestCase):
    def test_download_command_uses_connector_and_returns_report(self) -> None:
        connector = FakeConnector()

        original_get_connector = ingestion.get_connector
        original_logger = ingestion.logger
        original_raw = ingestion.write_raw_dump
        original_processed = ingestion.write_processed_parquet

        with TemporaryDirectory() as tmp_root:
            paths = Paths.default(tmp_root)
            paths.create()

            ingestion.get_connector = lambda source, exchange=None: connector
            ingestion.logger = types.SimpleNamespace(info=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None)
            ingestion.write_raw_dump = lambda *args, **kwargs: Path(tmp_root) / "raw.csv"
            ingestion.write_processed_parquet = lambda *args, **kwargs: Path(tmp_root) / "processed.parquet"

            try:
                report = ingestion.run_download(
                    paths=paths,
                    symbols="AAPL,MSFT",
                    start="2024-01-01",
                    end="2024-01-03",
                    timeframe="1d",
                    source="yfinance",
                )
            finally:
                ingestion.get_connector = original_get_connector
                ingestion.logger = original_logger
                ingestion.write_raw_dump = original_raw
                ingestion.write_processed_parquet = original_processed

        self.assertEqual(len(report), 2)
        self.assertEqual(report[0]["rows"], 2)
        self.assertEqual(connector.fetched, [("AAPL", "1d", "2024-01-01", "2024-01-03"), ("MSFT", "1d", "2024-01-01", "2024-01-03")])

    def test_ccxt_connector_parses_ohlcv(self) -> None:
        fake_ccxt = types.ModuleType("ccxt")

        class _FakeExchange:
            def __init__(self, *_args, **_kwargs):
                pass

            def fetch_ohlcv(self, symbol, timeframe, since, params):
                return [
                    [1_700_000_000_000, 100.0, 101.0, 99.0, 100.5, 123.0, 1],
                    [1_700_003_600_000, 100.5, 101.5, 100.0, 101.0, 150.0, 2],
                ]

        fake_ccxt.binance = _FakeExchange
        original_ccxt = sys.modules.get("ccxt")
        sys.modules["ccxt"] = fake_ccxt
        try:
            conn = CCXTConnector()
            frame = conn.fetch_ohlcv("BTC/USDT", "1h", "2023-11-14", "2023-11-14")
        finally:
            if original_ccxt is None:
                sys.modules.pop("ccxt", None)
            else:
                sys.modules["ccxt"] = original_ccxt

        self.assertEqual(list(frame.columns), ["open", "high", "low", "close", "volume"])
        self.assertEqual(len(frame), 2)

    def test_quality_detects_gaps_duplicates_and_outliers(self) -> None:
        group = pd.DataFrame(
            {
                "ts_utc": pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z", "2024-01-03T00:00:00Z"]),
                "symbol": ["AAPL", "AAPL", "AAPL"],
                "venue": ["NYSE", "NYSE", "NYSE"],
                "timeframe": ["1d", "1d", "1d"],
                "open": [1.0, 1.1, 1000.0],
                "high": [1.2, 1.3, 1001.0],
                "low": [0.8, 1.0, 999.0],
                "close": [1.1, 0.95, 1000.5],
                "volume": [1000, 1200, 800],
            }
        )

        duplicates, nulls, missing, gaps = _run_quality_metrics(group)
        outliers = _run_outliers(group)

        self.assertEqual(duplicates, 1)
        self.assertEqual(missing, 1)
        self.assertGreaterEqual(gaps, 1)
        self.assertGreaterEqual(outliers, 1)
        self.assertEqual(nulls, 0)

    def test_cli_download_uses_default_dependencies(self) -> None:
        fake_typer = types.ModuleType("typer")
        emitted = []

        class _FakeTyper:
            def __init__(self, *args, **kwargs):
                pass

            def command(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

            def __call__(self):
                return None

        def _option(default, *args, **kwargs):
            return default

        fake_typer.Option = _option
        fake_typer.Typer = _FakeTyper
        fake_typer.echo = emitted.append

        original_typer = sys.modules.get("typer")
        sys.modules["typer"] = fake_typer

        fake_calls = []

        try:
            cli = importlib.import_module("market_data_ingest.cli")
            cli.run_download = lambda **kwargs: fake_calls.append(kwargs) or [
                {
                    "symbol": "AAPL",
                    "rows": 5,
                    "raw_path": "raw",
                    "processed_path": "processed",
                    "from": "2024-01-01",
                    "to": "2024-01-02",
                }
            ]

            cli.download(
                symbols="AAPL",
                start="2024-01-01",
                end="2024-01-02",
                timeframe="1d",
                source="yfinance",
                exchange="binance",
                venue="",
                root=".",
                log_level="INFO",
            )
        finally:
            if original_typer is None:
                sys.modules.pop("typer", None)
            else:
                sys.modules["typer"] = original_typer

        self.assertEqual(len(fake_calls), 1)
        self.assertTrue(emitted)


if __name__ == "__main__":
    unittest.main()
