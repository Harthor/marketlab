from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from django.test import SimpleTestCase, TestCase, override_settings
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
        from datetime import datetime, timezone
        from pathlib import Path

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

    @staticmethod
    def _canonical_manifest(**overrides) -> dict:
        manifest = {
            'schema_version': '2.0',
            'kind': 'correlation',
            'status': 'complete',
            'run_id': 'canonical-run',
            'created_at_utc': '2026-07-01T00:00:00+00:00',
            'started_at_utc': '2026-07-01T00:00:00+00:00',
            'dataset_path': 'dataset.parquet',
            'dataset_hash': 'alpha',
            'config_hash': 'cfg',
            'seed': 1,
            'top_features': {'pearson': []},
            'artifacts': [],
            'warnings': [],
        }
        manifest.update(overrides)
        return manifest

    def test_runs_endpoint_marks_legacy_manifest_invalid(self) -> None:
        # Producers validate at write time; the reader refuses pre-2.0
        # manifests instead of guessing, pointing at the migration tool.
        with tempfile.TemporaryDirectory() as temp_root:
            workspace = Path(temp_root)
            self._write_manifest(
                workspace=workspace,
                kind='correlation',
                name='run-legacy',
                payload={
                    'dataset_hash': 'alpha',
                    'schema_version': '1.0',
                    'top_features': 5,
                    'stats': {'score': 1.0},
                },
            )

            with override_settings(MARKETLAB_WORKSPACE=workspace):
                response = APIClient().get('/api/runs')

            self.assertEqual(response.status_code, 200)
            payload = json.loads(response.content.decode('utf-8'))
            self.assertEqual(len(payload), 1)
            item = payload[0]
            self.assertEqual(item['status'], 'invalid')
            self.assertIn('migrate_manifests', item['error']['message'])

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

            manifest = self._canonical_manifest(
                run_id='art-list',
                dataset_hash='beta',
                artifacts=[
                    {'type': 'table', 'name': 'feature_report', 'path': 'tables/feature_report.csv'},
                    {'type': 'plot', 'name': 'feature_plot', 'path': 'plots/feature_plot.png'},
                ],
            )
            (base_dir / 'summary.json').write_text(json.dumps(manifest), encoding='utf-8')

            with override_settings(MARKETLAB_WORKSPACE=workspace):
                response = APIClient().get('/api/runs?type=correlation')

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIsInstance(payload, list)
            self.assertEqual(len(payload), 1)
            self.assertTrue(any('feature_report' in name for name in payload[0]['table_names']))
            self.assertTrue(any('feature_plot' in name for name in payload[0]['plot_names']))


# ---------------------------------------------------------------------------
# Alert Engine v1 tests
# ---------------------------------------------------------------------------

MOCK_DASHBOARD: dict[str, Any] = {
    "runId": "test-run",
    "generatedAt": "2026-02-28T00:00:00Z",
    "asset": "BTC-USD",
    "modeDefault": "simple",
    "signals": [
        {
            "cardKey": "fng",
            "signalId": "signal_fng",
            "displayName": "Fear & Greed Index",
            "simpleName": "Miedo y codicia",
            "state": "yellow",
            "icon": "thermometer",
            "confidence": 50,
            "confidenceBreakdown": {"total": 50, "strength": 10},
            "sampleSize": 2248,
            "stats": {
                "primaryCorrelation": 0.35,
                "primaryPValue": 0.001,
                "stabilityScore": 50,
            },
            "detail": {
                "cardKey": "fng",
                "granger": {
                    "available": True, "direction": "signal_to_price",
                    "pValueForward": 0.01, "pValueReverse": 0.4,
                },
                "bootstrap": {"available": True, "pValueMaxStat": 0.05},
            },
            "dataFrequency": "daily",
            "narrative": {
                "simple": {"title": "FNG", "subtitle": "", "summary": "", "cta": ""},
                "pro": {"title": "FNG", "subtitle": "", "summary": "", "cta": ""},
            },
        },
        {
            "cardKey": "onchain",
            "signalId": "signal_onchain",
            "displayName": "On-Chain Metrics",
            "simpleName": "On-chain",
            "state": "green",
            "icon": "link",
            "confidence": 60,
            "stats": {
                "primaryCorrelation": -0.07,
                "primaryPValue": 0.0004,
                "stabilityScore": 54,
            },
            "detail": {"cardKey": "onchain"},
            "dataFrequency": "daily",
            "narrative": {
                "simple": {"title": "OC", "subtitle": "", "summary": "", "cta": ""},
                "pro": {"title": "OC", "subtitle": "", "summary": "", "cta": ""},
            },
        },
    ],
}


class AlertEvaluatorTests(TestCase):
    """Tests for the alert evaluator logic."""

    def _make_rule(self, **kwargs: Any) -> Any:
        from .models import AlertRule
        defaults = {
            "name": "Test Rule",
            "alert_type": AlertRule.AlertType.SIGNAL_STATE_CHANGE,
            "card_key": "fng",
            "config": {},
        }
        defaults.update(kwargs)
        return AlertRule.objects.create(**defaults)

    def test_signal_state_change_fires(self) -> None:
        from .evaluator import evaluate_all_rules
        rule = self._make_rule(
            alert_type="signal_state_change",
            card_key="fng",
            config={"from_states": ["green"], "to_states": ["yellow"]},
        )
        events = evaluate_all_rules(
            dashboard=MOCK_DASHBOARD,
            previous_states={"fng": "green"},
        )
        self.assertEqual(len(events), 1)
        self.assertIn("green", events[0].title)
        self.assertIn("yellow", events[0].title)
        self.assertEqual(events[0].rule_id, rule.id)

    def test_signal_state_change_no_fire_same_state(self) -> None:
        from .evaluator import evaluate_all_rules
        self._make_rule(
            alert_type="signal_state_change",
            card_key="fng",
            config={},
        )
        events = evaluate_all_rules(
            dashboard=MOCK_DASHBOARD,
            previous_states={"fng": "yellow"},  # same as current
        )
        self.assertEqual(len(events), 0)

    def test_threshold_breach_fires(self) -> None:
        from .evaluator import evaluate_all_rules
        rule = self._make_rule(
            alert_type="threshold_breach",
            card_key="fng",
            config={"metric": "primaryCorrelation", "operator": "gt", "value": 0.3},
        )
        events = evaluate_all_rules(
            dashboard=MOCK_DASHBOARD,
            previous_states={},
        )
        self.assertEqual(len(events), 1)
        self.assertIn("primaryCorrelation", events[0].title)
        self.assertEqual(events[0].rule_id, rule.id)

    def test_threshold_breach_no_fire(self) -> None:
        from .evaluator import evaluate_all_rules
        self._make_rule(
            alert_type="threshold_breach",
            card_key="fng",
            config={"metric": "primaryCorrelation", "operator": "gt", "value": 0.9},
        )
        events = evaluate_all_rules(
            dashboard=MOCK_DASHBOARD,
            previous_states={},
        )
        self.assertEqual(len(events), 0)

    def test_anomaly_fires(self) -> None:
        from .evaluator import evaluate_all_rules
        # primaryCorrelation is 0.35, sigma=0.1 → |0.35| > 0.1 → anomaly
        self._make_rule(
            alert_type="anomaly",
            card_key="fng",
            config={"metric": "primaryCorrelation", "sigma": 0.1},
        )
        events = evaluate_all_rules(
            dashboard=MOCK_DASHBOARD,
            previous_states={},
        )
        self.assertEqual(len(events), 1)
        self.assertIn("anomaly", events[0].title)

    def test_anomaly_no_fire_within_sigma(self) -> None:
        from .evaluator import evaluate_all_rules
        self._make_rule(
            alert_type="anomaly",
            card_key="fng",
            config={"metric": "primaryCorrelation", "sigma": 5.0},
        )
        events = evaluate_all_rules(
            dashboard=MOCK_DASHBOARD,
            previous_states={},
        )
        self.assertEqual(len(events), 0)

    def test_cooldown_prevents_duplicate(self) -> None:
        from .evaluator import evaluate_all_rules
        self._make_rule(
            alert_type="threshold_breach",
            card_key="fng",
            config={"metric": "primaryCorrelation", "operator": "gt", "value": 0.3},
            cooldown_minutes=60,
        )
        # First evaluation fires
        events1 = evaluate_all_rules(dashboard=MOCK_DASHBOARD, previous_states={})
        self.assertEqual(len(events1), 1)
        # Second evaluation within cooldown → no fire
        events2 = evaluate_all_rules(dashboard=MOCK_DASHBOARD, previous_states={})
        self.assertEqual(len(events2), 0)

    def test_disabled_rule_not_evaluated(self) -> None:
        from .evaluator import evaluate_all_rules
        self._make_rule(
            alert_type="threshold_breach",
            card_key="fng",
            config={"metric": "primaryCorrelation", "operator": "gt", "value": 0.3},
            enabled=False,
        )
        events = evaluate_all_rules(dashboard=MOCK_DASHBOARD, previous_states={})
        self.assertEqual(len(events), 0)


class AlertApiTests(TestCase):
    """Tests for alert REST API endpoints."""

    def setUp(self) -> None:
        self.client = APIClient()

    def test_create_rule(self) -> None:
        resp = self.client.post('/api/alerts/rules', {
            'name': 'FNG Drop',
            'alertType': 'threshold_breach',
            'cardKey': 'fng',
            'config': {'metric': 'primaryCorrelation', 'operator': 'lt', 'value': -0.5},
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data['name'], 'FNG Drop')
        self.assertEqual(data['alertType'], 'threshold_breach')

    def test_list_rules(self) -> None:
        from .models import AlertRule
        AlertRule.objects.create(
            name='Test', alert_type='threshold_breach', card_key='fng',
        )
        resp = self.client.get('/api/alerts/rules')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_update_rule(self) -> None:
        from .models import AlertRule
        rule = AlertRule.objects.create(
            name='Old Name', alert_type='threshold_breach', card_key='fng',
        )
        resp = self.client.put(
            f'/api/alerts/rules/{rule.id}',
            {'name': 'New Name', 'enabled': False},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['name'], 'New Name')
        self.assertFalse(resp.json()['enabled'])

    def test_delete_rule(self) -> None:
        from .models import AlertRule
        rule = AlertRule.objects.create(
            name='Del', alert_type='threshold_breach', card_key='fng',
        )
        resp = self.client.delete(f'/api/alerts/rules/{rule.id}')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(AlertRule.objects.filter(id=rule.id).exists())

    def test_list_events(self) -> None:
        from .models import AlertEvent, AlertRule
        rule = AlertRule.objects.create(
            name='R', alert_type='threshold_breach', card_key='fng',
        )
        AlertEvent.objects.create(
            rule=rule, title='Test Event', severity='warning',
        )
        resp = self.client.get('/api/alerts/events')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_dismiss_event(self) -> None:
        from .models import AlertEvent, AlertRule
        rule = AlertRule.objects.create(
            name='R', alert_type='threshold_breach', card_key='fng',
        )
        event = AlertEvent.objects.create(
            rule=rule, title='Dismissable', severity='info',
        )
        resp = self.client.post(f'/api/alerts/events/{event.id}/dismiss')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.json()['dismissedAt'])

    def test_create_rule_missing_name(self) -> None:
        resp = self.client.post('/api/alerts/rules', {
            'alertType': 'threshold_breach',
            'cardKey': 'fng',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_create_rule_invalid_type(self) -> None:
        resp = self.client.post('/api/alerts/rules', {
            'name': 'Bad',
            'alertType': 'invalid_type',
            'cardKey': 'fng',
        }, format='json')
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Degen Alert Evaluator tests
# ---------------------------------------------------------------------------

MOCK_WATCHLIST: dict[str, Any] = {
    "snapshot_id": "test",
    "total_tokens": 3,
    "category_counts": {"meme_bluechip": 2, "dex_new_launch": 1},
    "tokens": [
        {
            "asset_uid": "solana:TOKEN_A",
            "symbol": "TOKA",
            "name": "Token A",
            "chain": "solana",
            "category": "meme_bluechip",
            "risk_score": 20,
            "universe_score": 85,
            "liquidity_usd": 500000,
            "volume_24h_usd": 2000000,
            "market_cap_usd": 50000000,
            "age_hours": 720,
            "security_flags": [],
        },
        {
            "asset_uid": "solana:TOKEN_B",
            "symbol": "TOKB",
            "name": "Token B",
            "chain": "solana",
            "category": "dex_new_launch",
            "risk_score": 80,
            "universe_score": 45,
            "liquidity_usd": 30000,
            "volume_24h_usd": 100000,
            "market_cap_usd": 1000000,
            "age_hours": 48,
            "security_flags": ["honeypot_risk", "mint_enabled"],
        },
        {
            "asset_uid": "base:TOKEN_C",
            "symbol": "TOKC",
            "name": "Token C",
            "chain": "base",
            "category": "meme_bluechip",
            "risk_score": 15,
            "universe_score": 92,
            "liquidity_usd": 1000000,
            "volume_24h_usd": 5000000,
            "market_cap_usd": 100000000,
            "age_hours": 2000,
            "security_flags": [],
        },
    ],
}

MOCK_SM_FEATURES: dict[str, dict[str, Any]] = {
    "solana:TOKEN_A": {
        "consensus_score": 75.0,
        "consensus_direction": "accumulate",
        "accumulation_net_usd": 5000.0,
        "unique_wallets_buying": 3,
        "unique_wallets_selling": 0,
        "first_buy_detected": False,
        "tier_a_active": True,
        "whale_buy_count": 2,
        "total_buy_volume": 1000.0,
        "total_sell_volume": 0.0,
        "latest_activity": "2026-02-28T12:00:00Z",
    },
}


class DegenAlertEvaluatorTests(TestCase):
    """Tests for the degen-specific alert evaluator."""

    def _make_degen_rule(self, **kwargs: Any) -> Any:
        from .models import AlertRule
        defaults = {
            "name": "Degen Test Rule",
            "alert_type": AlertRule.AlertType.WHALE_ACCUMULATION,
            "card_key": "degen",
            "config": {},
        }
        defaults.update(kwargs)
        return AlertRule.objects.create(**defaults)

    def test_whale_accumulation_fires(self) -> None:
        from .evaluator_degen import evaluate_degen_rules
        self._make_degen_rule(
            alert_type="whale_accumulation",
            config={"min_consensus": 60, "min_wallets": 2},
        )
        events = evaluate_degen_rules(
            watchlist=MOCK_WATCHLIST,
            sm_features=MOCK_SM_FEATURES,
        )
        self.assertEqual(len(events), 1)
        self.assertIn("TOKA", events[0].title)
        self.assertEqual(events[0].severity, "critical")  # tier_a_active

    def test_whale_accumulation_no_fire_low_consensus(self) -> None:
        from .evaluator_degen import evaluate_degen_rules
        self._make_degen_rule(
            alert_type="whale_accumulation",
            config={"min_consensus": 90, "min_wallets": 2},
        )
        events = evaluate_degen_rules(
            watchlist=MOCK_WATCHLIST,
            sm_features=MOCK_SM_FEATURES,
        )
        self.assertEqual(len(events), 0)

    def test_liquidity_event_fires(self) -> None:
        from .evaluator_degen import evaluate_degen_rules
        self._make_degen_rule(
            alert_type="liquidity_event",
            config={"min_liquidity_usd": 50000},
        )
        events = evaluate_degen_rules(
            watchlist=MOCK_WATCHLIST,
            sm_features={},
        )
        # TOKEN_B has 30k < 50k threshold
        self.assertEqual(len(events), 1)
        self.assertIn("TOKB", events[0].title)

    def test_rug_risk_fires(self) -> None:
        from .evaluator_degen import evaluate_degen_rules
        self._make_degen_rule(
            alert_type="rug_risk_detected",
            config={"risk_threshold": 75},
        )
        events = evaluate_degen_rules(
            watchlist=MOCK_WATCHLIST,
            sm_features={},
        )
        # TOKEN_B has risk_score 80 > 75
        self.assertEqual(len(events), 1)
        self.assertIn("TOKB", events[0].title)
        self.assertEqual(events[0].severity, "critical")

    def test_rug_risk_no_fire_below_threshold(self) -> None:
        from .evaluator_degen import evaluate_degen_rules
        self._make_degen_rule(
            alert_type="rug_risk_detected",
            config={"risk_threshold": 90},
        )
        events = evaluate_degen_rules(
            watchlist=MOCK_WATCHLIST,
            sm_features={},
        )
        self.assertEqual(len(events), 0)

    def test_explosion_score_fires(self) -> None:
        from .evaluator_degen import evaluate_degen_rules
        self._make_degen_rule(
            alert_type="explosion_score_jump",
            config={"score_threshold": 80},
        )
        events = evaluate_degen_rules(
            watchlist=MOCK_WATCHLIST,
            sm_features={},
        )
        # TOKEN_A (85) and TOKEN_C (92) exceed 80
        self.assertEqual(len(events), 2)
        symbols = {e.title for e in events}
        self.assertTrue(any("TOKA" in s for s in symbols))
        self.assertTrue(any("TOKC" in s for s in symbols))

    def test_cooldown_prevents_degen_duplicate(self) -> None:
        from .evaluator_degen import evaluate_degen_rules
        self._make_degen_rule(
            alert_type="rug_risk_detected",
            config={"risk_threshold": 75},
            cooldown_minutes=60,
        )
        events1 = evaluate_degen_rules(
            watchlist=MOCK_WATCHLIST, sm_features={},
        )
        self.assertEqual(len(events1), 1)
        events2 = evaluate_degen_rules(
            watchlist=MOCK_WATCHLIST, sm_features={},
        )
        self.assertEqual(len(events2), 0)

    def test_disabled_degen_rule_not_evaluated(self) -> None:
        from .evaluator_degen import evaluate_degen_rules
        self._make_degen_rule(
            alert_type="whale_accumulation",
            config={"min_consensus": 50, "min_wallets": 1},
            enabled=False,
        )
        events = evaluate_degen_rules(
            watchlist=MOCK_WATCHLIST,
            sm_features=MOCK_SM_FEATURES,
        )
        self.assertEqual(len(events), 0)

    def test_template_rendering_es(self) -> None:
        from .evaluator_degen import evaluate_degen_rules
        self._make_degen_rule(
            alert_type="rug_risk_detected",
            config={"risk_threshold": 75},
        )
        events = evaluate_degen_rules(
            watchlist=MOCK_WATCHLIST,
            sm_features={},
            lang="es",
        )
        self.assertEqual(len(events), 1)
        self.assertIn("Riesgo de Rug", events[0].title)

    def test_create_degen_rule_via_api(self) -> None:
        client = APIClient()
        resp = client.post('/api/alerts/rules', {
            'name': 'Whale Watch',
            'alertType': 'whale_accumulation',
            'cardKey': 'degen',
            'config': {'min_consensus': 70, 'min_wallets': 2},
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['alertType'], 'whale_accumulation')
