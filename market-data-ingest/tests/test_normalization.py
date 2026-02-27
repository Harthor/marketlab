"""Unit tests for normalization (sin red)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

import pandas as pd

from market_data_ingest.normalization import CANONICAL_COLUMNS, normalize_ohlcv


class TestNormalization(unittest.TestCase):
    def test_normalize_ohlcv_returns_canonical_schema(self) -> None:
        raw = pd.DataFrame(
            {
                "Open": [100.0, 101.5],
                "High": [102.0, 103.2],
                "Low": [99.1, 100.8],
                "Close": [100.8, 102.7],
                "Volume": [1500, 1700],
            },
            index=pd.to_datetime(["2023-01-02", "2023-01-03"]),
        )

        out = normalize_ohlcv(
            raw=raw,
            symbol="AAPL",
            venue="NYSE",
            timeframe="1d",
            source="yfinance",
            ingestion_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(list(out.columns), CANONICAL_COLUMNS)
        self.assertEqual(len(out), 2)
        self.assertEqual(out["symbol"].nunique(), 1)
        self.assertTrue(str(out["ts_utc"].dtype).startswith("datetime64") and "UTC" in str(out["ts_utc"].dtype))
        self.assertTrue(out["checksum"].str.len().eq(32).all())

    def test_normalize_ohlcv_raises_when_missing_columns(self) -> None:
        raw = pd.DataFrame({"Open": [1, 2], "Close": [1, 2]}, index=pd.date_range("2023-01-01", periods=2))

        with self.assertRaises(ValueError) as err:
            normalize_ohlcv(
                raw=raw,
                symbol="AAPL",
                venue="NYSE",
                timeframe="1d",
                source="yfinance",
                ingestion_ts=datetime(2025, 1, 1, tzinfo=timezone.utc),
            )
        self.assertIn("Faltan columnas requeridas", str(err.exception))


if __name__ == "__main__":
    unittest.main()
