from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from market_data_ingest import ingestion
from market_data_ingest.config import Paths
from market_data_ingest.storage import write_price_metadata


class TestRunDownloadManifest(unittest.TestCase):
    def test_run_download_writes_ingest_manifest(self) -> None:
        class FakeConnector:
            @property
            def venue(self) -> str:
                return "NYSE"

            def fetch_ohlcv(self, symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
                idx = pd.date_range(start, end, freq="D", inclusive="left")
                return pd.DataFrame(
                    {
                        "Open": [10.0, 11.0],
                        "High": [10.5, 11.5],
                        "Low": [9.9, 10.8],
                        "Close": [10.2, 11.2],
                        "Volume": [100, 200],
                    },
                    index=idx,
                )

        with TemporaryDirectory() as tmp_root:
            paths = Paths.default(tmp_root)
            paths.create()

            connector = FakeConnector()
            original_get_connector = ingestion.get_connector
            original_raw_dump = ingestion.write_raw_dump
            original_processed = ingestion.write_processed_parquet

            ingestion.get_connector = lambda source, exchange=None: connector
            ingestion.write_raw_dump = lambda *args, **kwargs: Path(tmp_root) / "raw.csv"

            def fake_processed(*args: object, **kwargs: object) -> Path:
                frame = kwargs["frame"]
                paths = kwargs["paths"]
                source = kwargs["source"]
                symbol = kwargs["symbol"]
                timeframe = kwargs["timeframe"]
                output = paths.processed_dir / source / symbol / timeframe / f"{symbol}_{timeframe}.parquet"
                output.parent.mkdir(parents=True, exist_ok=True)
                frame.to_parquet(output, index=False)
                write_price_metadata(output, frame, provider=source)
                return output

            ingestion.write_processed_parquet = fake_processed

            try:
                report = ingestion.run_download(
                    paths=paths,
                    symbols="AAPL",
                    start="2024-01-01",
                    end="2024-01-03",
                    timeframe="1d",
                    source="yfinance",
                )
            finally:
                ingestion.get_connector = original_get_connector
                ingestion.write_raw_dump = original_raw_dump
                ingestion.write_processed_parquet = original_processed

            manifest_path = paths.processed_dir / "ingest_summary.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["kind"], "ingest")
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(len(manifest["artifacts"]), 1)
            artifact = manifest["artifacts"][0]
            self.assertEqual(artifact["symbol"], "AAPL")
            self.assertEqual(artifact["status"], "complete")
            self.assertIsNotNone(artifact["dataset_hash"])

            self.assertEqual(report[0]["symbol"], "AAPL")
            self.assertEqual(report[0]["rows"], 2)
            self.assertEqual(report[0]["manifest_path"], str(manifest_path))


if __name__ == "__main__":
    unittest.main()
