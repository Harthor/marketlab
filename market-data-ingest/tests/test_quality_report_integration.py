"""Integration-quality smoke test with synthetic demo parquet (offline)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from market_data_ingest.config import Paths
from market_data_ingest import quality

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "make_demo_prices.py"

spec = importlib.util.spec_from_file_location("market_data_ingest_demo_script", str(SCRIPT_PATH))
if spec is None or spec.loader is None:
    raise RuntimeError("No se pudo cargar scripts/make_demo_prices.py")

demo_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo_script)


class TestQualityReportIntegration(unittest.TestCase):
    def test_quality_report_detects_issues_from_demo_parquet(self) -> None:
        with TemporaryDirectory() as tmp_root:
            paths = Paths.default(tmp_root)
            paths.create()

            demo_script.generate_demo_prices(
                symbols=["AAPL"],
                start="2024-01-01",
                end="2024-01-08",
                timeframe="1d",
                root=tmp_root,
                venue="GEN",
                inject_gap=True,
                inject_duplicate=True,
                inject_null=True,
            )

            reports = quality.quality_report(paths)

            report_map = {rep.symbol: rep for rep in reports}
            self.assertIn("AAPL", report_map)
            aapl_report = report_map["AAPL"]
            self.assertGreaterEqual(aapl_report.duplicates, 1)
            self.assertGreaterEqual(aapl_report.null_rows, 1)
            self.assertGreaterEqual(aapl_report.missing_timestamps, 1)
            self.assertGreaterEqual(aapl_report.suspicious_gaps, 0)

            manifest_path = paths.processed_dir / "ingest_summary.json"
            self.assertTrue(manifest_path.exists())
            self.assertTrue((paths.processed_dir / "AAPL" / "1d.parquet").exists())
            self.assertTrue((paths.processed_dir / "AAPL" / "1d.meta.json").exists())


if __name__ == "__main__":
    unittest.main()
