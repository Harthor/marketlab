"""Tests that processed parquet writes are atomic."""

from __future__ import annotations

from pathlib import Path
import unittest
from tempfile import TemporaryDirectory

import pandas as pd

from market_data_ingest.storage import write_parquet_atomic


class TestStorageAtomicWrite(unittest.TestCase):
    def test_write_parquet_atomic_no_partial_final_file_on_error(self) -> None:
        frame = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

        with TemporaryDirectory() as tmp_root:
            target = Path(tmp_root) / "A" / "demo.parquet"

            original_to_parquet = pd.DataFrame.to_parquet

            def broken_to_parquet(self: pd.DataFrame, path: str | Path, *args, **kwargs) -> None:
                Path(path).write_text("partial-bytes")
                raise RuntimeError("simulated write failure")

            pd.DataFrame.to_parquet = broken_to_parquet
            try:
                with self.assertRaises(RuntimeError):
                    write_parquet_atomic(target, frame)
            finally:
                pd.DataFrame.to_parquet = original_to_parquet

            self.assertFalse(target.exists())
            self.assertEqual([], [path for path in Path(tmp_root).rglob("*.tmp")])


if __name__ == "__main__":
    unittest.main()
