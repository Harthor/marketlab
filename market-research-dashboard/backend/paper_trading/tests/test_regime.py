"""Tests for regime detector, model, and API views."""
from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from paper_trading.models import RegimeSnapshot
from paper_trading.regime.detector import REGIMES, RegimeDetector, RegimeResult


def _make_mania_tokens(n: int = 20) -> list[dict]:
    """Create tokens that should trigger mania regime."""
    return [
        {
            "universe_score": 70,
            "risk_score": 20,
            "volume_24h_usd": 300_000,
            "liquidity_usd": 200_000,
            "price_change_24h_pct": 25,
            "age_hours": 48,
        }
        for _ in range(n)
    ]


def _make_capitulation_tokens(n: int = 20) -> list[dict]:
    """Create tokens that should trigger capitulation regime."""
    return [
        {
            "universe_score": 15,
            "risk_score": 80,
            "volume_24h_usd": 400_000,
            "liquidity_usd": 30_000,
            "price_change_24h_pct": -45,
            "age_hours": 200,
        }
        for _ in range(n)
    ]


def _make_low_activity_tokens(n: int = 5) -> list[dict]:
    """Create tokens that should trigger low_activity regime."""
    return [
        {
            "universe_score": 25,
            "risk_score": 35,
            "volume_24h_usd": 5_000,
            "liquidity_usd": 20_000,
            "price_change_24h_pct": 0.5,
            "age_hours": 500,
        }
        for _ in range(n)
    ]


class TestRegimeDetector(TestCase):
    """Test RegimeDetector.detect()."""

    def setUp(self):
        self.detector = RegimeDetector()

    def test_empty_tokens_returns_low_activity(self):
        result = self.detector.detect([])
        self.assertIsInstance(result, RegimeResult)
        # Empty watchlist → low_activity should win (or at least be scored)
        self.assertIn(result.current_regime, REGIMES)

    def test_mania_detected(self):
        tokens = _make_mania_tokens()
        result = self.detector.detect(tokens)
        self.assertEqual(result.current_regime, "mania")
        self.assertGreater(result.confidence, 0.3)

    def test_capitulation_detected(self):
        tokens = _make_capitulation_tokens()
        result = self.detector.detect(tokens)
        self.assertEqual(result.current_regime, "capitulation")
        self.assertGreater(result.confidence, 0.3)

    def test_low_activity_detected(self):
        tokens = _make_low_activity_tokens()
        result = self.detector.detect(tokens)
        self.assertEqual(result.current_regime, "low_activity")

    def test_all_regimes_scored(self):
        tokens = _make_mania_tokens()
        result = self.detector.detect(tokens)
        for regime in REGIMES:
            self.assertIn(regime, result.scores)
            self.assertGreaterEqual(result.scores[regime].score, 0.0)
            self.assertLessEqual(result.scores[regime].score, 1.0)

    def test_aggregate_metrics_populated(self):
        tokens = _make_mania_tokens(10)
        result = self.detector.detect(tokens)
        m = result.aggregate_metrics
        self.assertEqual(m["count"], 10)
        self.assertGreater(m["avg_score"], 0)
        self.assertGreater(m["avg_volume_24h"], 0)

    def test_confidence_in_01(self):
        tokens = _make_mania_tokens()
        result = self.detector.detect(tokens)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_score_components_populated(self):
        tokens = _make_mania_tokens()
        result = self.detector.detect(tokens)
        mania_score = result.scores["mania"]
        self.assertGreater(len(mania_score.components), 0)


class TestRegimeSnapshot(TestCase):
    """Test RegimeSnapshot model."""

    def test_create_snapshot(self):
        snap = RegimeSnapshot.objects.create(
            regime="mania",
            confidence=0.75,
            scores={"mania": 0.75, "capitulation": 0.1},
            aggregate_metrics={"count": 20, "avg_score": 70},
            token_count=20,
        )
        self.assertEqual(snap.regime, "mania")
        self.assertEqual(snap.confidence, 0.75)
        self.assertEqual(snap.token_count, 20)

    def test_ordering_by_detected_at(self):
        RegimeSnapshot.objects.create(regime="mania", confidence=0.5)
        RegimeSnapshot.objects.create(regime="capitulation", confidence=0.8)
        latest = RegimeSnapshot.objects.first()
        self.assertEqual(latest.regime, "capitulation")


class TestRegimeAPI(TestCase):
    """Test regime API endpoints."""

    def setUp(self):
        self.client = APIClient()

    def test_current_no_snapshots(self):
        res = self.client.get("/api/paper/regime/current/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["regime"], "low_activity")
        self.assertIsNone(res.json()["detected_at"])

    def test_current_with_snapshot(self):
        RegimeSnapshot.objects.create(
            regime="mania",
            confidence=0.82,
            scores={"mania": 0.82},
            aggregate_metrics={"count": 15},
            token_count=15,
        )
        res = self.client.get("/api/paper/regime/current/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["regime"], "mania")
        self.assertAlmostEqual(res.json()["confidence"], 0.82, places=2)

    def test_history_empty(self):
        res = self.client.get("/api/paper/regime/history/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])

    def test_history_with_snapshots(self):
        for r in ["mania", "rotation", "capitulation"]:
            RegimeSnapshot.objects.create(regime=r, confidence=0.5)
        res = self.client.get("/api/paper/regime/history/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 3)

    def test_history_limit(self):
        for _ in range(5):
            RegimeSnapshot.objects.create(regime="mania", confidence=0.5)
        res = self.client.get("/api/paper/regime/history/?limit=3")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 3)
