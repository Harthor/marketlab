from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

import pandas as pd

from market_data_ingest.storage import validate_prices_df, write_parquet_with_metadata


class TestPriceValidation(unittest.TestCase):
    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "ts_utc": pd.to_datetime([
                    "2024-01-01T00:00:00Z",
                    "2024-01-02T00:00:00Z",
                    "2024-01-03T00:00:00Z",
                ]),
                "open": [1.0, 2.0, 3.0],
                "high": [1.2, 2.2, 3.2],
                "low": [0.9, 1.8, 2.9],
                "close": [1.1, 2.1, 3.1],
                "volume": [100, 110, 120],
            }
        )

    def test_validate_prices_df_rejects_invalid(self) -> None:
        frame = self._frame()
        frame.loc[1, "close"] = None
        with self.assertRaises(ValueError):
            validate_prices_df(frame, min_rows=1, nan_policy="reject")

    def test_validate_prices_df_accepts_drop_policy(self) -> None:
        frame = self._frame()
        frame.loc[1, "open"] = None
        frame = validate_prices_df(frame, min_rows=1, nan_policy="drop")
        self.assertEqual(len(frame), 2)

    def test_validate_prices_df_rejects_duplicates(self) -> None:
        frame = self._frame()
        frame.loc[2, "ts_utc"] = frame.loc[1, "ts_utc"]
        with self.assertRaises(ValueError):
            validate_prices_df(frame, min_rows=1, nan_policy="allow")

    def test_validate_prices_df_rejects_bad_ohlc(self) -> None:
        frame = self._frame()
        frame.loc[1, "high"] = 0.5
        with self.assertRaises(ValueError):
            validate_prices_df(frame, min_rows=1)

    def test_write_parquet_with_metadata_generates_sidecar(self) -> None:
        with TemporaryDirectory() as tmp_root:
            root = Path(tmp_root)
            frame = self._frame()
            target = root / "demo.parquet"
            path, meta = write_parquet_with_metadata(target, frame, provider="demo")

            self.assertEqual(path, target)
            self.assertTrue((root / "demo.meta.json").exists())
            self.assertEqual(meta["provider"], "demo")
            self.assertEqual(meta["rows"], 3)
