from __future__ import annotations

import json
import tempfile
from typing import Any
from pathlib import Path

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from .utils import json_sanitize, sanitize_for_json


class SanitizeForJsonTests(SimpleTestCase):
    def test_sanitize_nested_payload_removes_non_finite_floats(self) -> None:
        raw: dict[str, Any] = {
            "run_id": "correlation::demo",
            "score": float("nan"),
            "loss": float("inf"),
            "tuple_payload": (float("inf"), {"x": float("-inf")}),
            "nested": {
                "finite": 1.5,
                "bad": [float("-inf"), {"val": float("nan"), "label": "ok"}],
            },
        }

        cleaned = sanitize_for_json(raw)
        assert cleaned["score"] is None
        assert cleaned["loss"] is None
        assert cleaned["tuple_payload"][0] is None
        assert cleaned["tuple_payload"][1]["x"] is None
        assert cleaned["nested"]["bad"][0] is None
        assert cleaned["nested"]["bad"][1]["val"] is None

    def test_json_sanitize_entrypoint(self) -> None:
        raw = {"v": float("nan")}
        cleaned = json_sanitize(raw)
        assert cleaned["v"] is None


class RunIdSanitizerTests(SimpleTestCase):
    def test_sanitize_path_and_datetime_roundtrip(self) -> None:
        from pathlib import Path
        from datetime import datetime, timezone

        raw = {
            "path": Path("/tmp/demo.csv"),
            "created_at": datetime(2026, 2, 27, 0, 0, tzinfo=timezone.utc),
            "children": [Path("/tmp/a"), {"path": Path("/tmp/b")}],
        }

        cleaned = sanitize_for_json(raw)
        assert cleaned["path"] == "/tmp/demo.csv"
        assert cleaned["children"][0] == "/tmp/a"
        assert cleaned["children"][1]["path"] == "/tmp/b"
        assert cleaned["created_at"] == "2026-02-27T00:00:00+00:00"

    def test_sanitize_numpy_values_if_numpy_is_available(self) -> None:
        try:
            import numpy as np
        except Exception:
            return

        raw = {
            "float": np.float64(float("inf")),
            "int": np.int64(7),
            "matrix": [np.float64(float("nan")), [np.int32(1)]],
        }

        cleaned = sanitize_for_json(raw)
        assert cleaned["float"] is None
        assert cleaned["int"] == 7
        assert cleaned["matrix"][0] is None
        assert cleaned["matrix"][1][0] == 1


class RunsApiTests(SimpleTestCase):
    def _write_manifest(self, workspace: Path, kind: str, name: str, payload: Any) -> None:
        base_dir = {
            'correlation': workspace / 'correlation-engine' / 'reports',
            'forecast': workspace / 'forecasting-backtest' / 'runs',
        }[kind]
        manifest_dir = base_dir / name
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_name = 'summary.json' if kind == 'correlation' else 'run_summary.json'
        (manifest_dir / manifest_name).write_text(json.dumps(payload), encoding='utf-8')

    def test_runs_endpoint_sanitizes_non_finite_in_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root)
            self._write_manifest(
                workspace=workspace,
                kind='correlation',
                name='run-nonfinite',
                payload={
                    'dataset_hash': 'alpha',
                    'schema_version': '1.0',
                    'top_features': 5,
                    'stats': {'score': float('nan'), 'loss': float('inf')},
                },
            )

            with override_settings(MARKETLAB_WORKSPACE=workspace):
                response = APIClient().get('/api/runs')

            self.assertEqual(response.status_code, 200)
            payload = json.loads(response.content.decode('utf-8'))
            self.assertIsInstance(payload, list)
            self.assertGreaterEqual(len(payload), 1)
            item = payload[0]
            self.assertEqual(item['status'], 'complete')
            self.assertEqual(item['summary']['stats']['score'], None)
            self.assertEqual(item['summary']['stats']['loss'], None)
            self.assertIn('sanitized_nonfinite_values', item.get('warnings', []))

    def test_runs_endpoint_does_not_crash_on_corrupt_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root)
            manifest_path = workspace / 'correlation-engine' / 'reports' / 'corrupt'
            manifest_path.mkdir(parents=True, exist_ok=True)
            (manifest_path / 'summary.json').write_text('{not valid json}', encoding='utf-8')

            with override_settings(MARKETLAB_WORKSPACE=workspace):
                response = APIClient().get('/api/runs')

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIsInstance(payload, list)
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]['status'], 'invalid')

    def test_runs_endpoint_reads_manifest_artifacts_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root)
            base_dir = workspace / 'correlation-engine' / 'reports' / 'art-list'
            base_dir.mkdir(parents=True, exist_ok=True)
            table_path = base_dir / 'tables' / 'feature_report.csv'
            plot_path = base_dir / 'plots' / 'feature_plot.png'
            table_path.parent.mkdir(parents=True, exist_ok=True)
            plot_path.parent.mkdir(parents=True, exist_ok=True)
            table_path.write_text('a,b\n1,2\n3,4\n', encoding='utf-8')
            plot_path.write_text('fake image', encoding='utf-8')

            manifest = {
                'dataset_hash': 'beta',
                'schema_version': '1.0',
                'top_features': 4,
                'artifacts': [
                    {'type': 'table', 'name': 'feature_report', 'path': 'tables/feature_report.csv'},
                    {'type': 'plot', 'name': 'feature_plot', 'path': 'plots/feature_plot.png'},
                ],
            }
            (base_dir / 'summary.json').write_text(json.dumps(manifest), encoding='utf-8')

            with override_settings(MARKETLAB_WORKSPACE=workspace):
                response = APIClient().get('/api/runs?type=correlation')

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIsInstance(payload, list)
            self.assertEqual(len(payload), 1)
            self.assertTrue(any('feature_report' in name for name in payload[0]['table_names']))
            self.assertTrue(any('feature_plot' in name for name in payload[0]['plot_names']))
