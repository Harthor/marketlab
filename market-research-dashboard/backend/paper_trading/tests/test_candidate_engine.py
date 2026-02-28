"""Tests for candidate generation engine."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from django.test import TestCase

from paper_trading.candidate_engine.conflict_resolver import resolve_conflicts
from paper_trading.candidate_engine.derived_features import (
    compute_freshness,
    compute_liquidity_quality,
    compute_priority_score,
    compute_risk_penalty,
)
from paper_trading.candidate_engine.generator import CandidateGenerator
from paper_trading.candidate_engine.portfolio_overlay import apply_overlay
from paper_trading.models import PaperPortfolio, PaperPosition
from paper_trading.playbooks.loader import PortfolioRiskConfig

CONFIGS_DIR = (
    Path(__file__).resolve().parent.parent / "configs" / "playbooks"
)


def _make_token(**overrides) -> dict:
    """Create a token state dict."""
    base = {
        "asset_uid": "sol:pump_test",
        "symbol": "TEST",
        "chain": "solana",
        "category": "meme",
        "universe_score": 65,
        "risk_score": 25,
        "liquidity_usd": 80_000,
        "volume_24h_usd": 60_000,
        "market_cap_usd": 500_000,
        "age_hours": 72,
        "price_usd": 0.001,
        "price_change_24h_pct": 15,
        "smart_money": {
            "consensus_direction": "accumulate",
            "consensus_score": 70,
            "unique_wallets_buying": 3,
            "tier_a_active": True,
            "accumulation_net_usd": 15000,
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Derived features
# ---------------------------------------------------------------------------


class TestDerivedFeatures(TestCase):
    def test_liquidity_quality_high(self):
        q = compute_liquidity_quality({"liquidity_usd": 500_000, "volume_24h_usd": 300_000})
        self.assertGreater(q, 0.8)

    def test_liquidity_quality_low(self):
        q = compute_liquidity_quality({"liquidity_usd": 1_000, "volume_24h_usd": 500})
        self.assertLess(q, 0.1)

    def test_freshness_new_token(self):
        f = compute_freshness({"age_hours": 10})
        self.assertGreater(f, 0.9)

    def test_freshness_old_token(self):
        f = compute_freshness({"age_hours": 1000})
        self.assertAlmostEqual(f, 0.0, places=1)

    def test_risk_penalty_low(self):
        p = compute_risk_penalty({"risk_score": 10, "security_flags": []})
        self.assertLess(p, 0.1)

    def test_risk_penalty_high(self):
        p = compute_risk_penalty({"risk_score": 75, "security_flags": ["honeypot"]})
        self.assertGreater(p, 0.7)

    def test_priority_score_positive(self):
        token = _make_token()
        s = compute_priority_score(0.7, 1.2, 0.8, token)
        self.assertGreater(s, 0)

    def test_priority_score_zero_confidence(self):
        token = _make_token()
        s = compute_priority_score(0.0, 1.2, 0.8, token)
        self.assertEqual(s, 0.0)


# ---------------------------------------------------------------------------
# Conflict resolver
# ---------------------------------------------------------------------------


class TestConflictResolver(TestCase):
    def test_picks_highest_priority(self):
        candidates = [
            {"asset_uid": "x", "priority_score": 0.5, "playbook_slug": "a"},
            {"asset_uid": "x", "priority_score": 0.8, "playbook_slug": "b"},
        ]
        result = resolve_conflicts(candidates)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["playbook_slug"], "b")

    def test_keeps_different_assets(self):
        candidates = [
            {"asset_uid": "x", "priority_score": 0.5, "playbook_slug": "a"},
            {"asset_uid": "y", "priority_score": 0.3, "playbook_slug": "a"},
        ]
        result = resolve_conflicts(candidates)
        self.assertEqual(len(result), 2)

    def test_sorted_by_priority(self):
        candidates = [
            {"asset_uid": "x", "priority_score": 0.3, "playbook_slug": "a"},
            {"asset_uid": "y", "priority_score": 0.8, "playbook_slug": "a"},
        ]
        result = resolve_conflicts(candidates)
        self.assertEqual(result[0]["asset_uid"], "y")

    def test_empty_input(self):
        self.assertEqual(resolve_conflicts([]), [])


# ---------------------------------------------------------------------------
# Portfolio overlay
# ---------------------------------------------------------------------------


class TestPortfolioOverlay(TestCase):
    def setUp(self):
        self.portfolio = PaperPortfolio.objects.create(
            name="Test Portfolio",
            initial_cash_usd=10_000,
            cash_usd=10_000,
            total_equity_usd=10_000,
            high_water_mark_usd=10_000,
            max_positions=10,
        )
        self.risk = PortfolioRiskConfig()

    def test_accepts_candidates(self):
        candidates = [
            {"asset_uid": "a", "chain": "solana"},
            {"asset_uid": "b", "chain": "base"},
        ]
        result = apply_overlay(candidates, self.portfolio, self.risk)
        self.assertEqual(len(result), 2)

    def test_rejects_duplicate_asset(self):
        PaperPosition.objects.create(
            portfolio=self.portfolio,
            asset_uid="a",
            symbol="A",
            chain="solana",
            entry_price_usd=0.01,
            avg_entry_price_usd=0.01,
            quantity=100,
            cost_basis_usd=1.0,
            status=PaperPosition.Status.OPEN,
        )
        candidates = [{"asset_uid": "a", "chain": "solana"}]
        result = apply_overlay(candidates, self.portfolio, self.risk)
        self.assertEqual(len(result), 0)

    def test_circuit_breaker_drawdown(self):
        self.portfolio.total_equity_usd = 7_000
        self.portfolio.high_water_mark_usd = 10_000
        self.portfolio.save()
        candidates = [{"asset_uid": "a", "chain": "solana"}]
        result = apply_overlay(candidates, self.portfolio, self.risk)
        self.assertEqual(len(result), 0)

    def test_max_positions_limit(self):
        self.risk.max_positions = 1
        PaperPosition.objects.create(
            portfolio=self.portfolio,
            asset_uid="existing",
            symbol="X",
            chain="solana",
            entry_price_usd=0.01,
            avg_entry_price_usd=0.01,
            quantity=100,
            cost_basis_usd=1.0,
            status=PaperPosition.Status.OPEN,
        )
        candidates = [{"asset_uid": "new", "chain": "base"}]
        result = apply_overlay(candidates, self.portfolio, self.risk)
        self.assertEqual(len(result), 0)

    def test_chain_cap(self):
        self.risk.max_per_chain = 1
        PaperPosition.objects.create(
            portfolio=self.portfolio,
            asset_uid="existing",
            symbol="X",
            chain="solana",
            entry_price_usd=0.01,
            avg_entry_price_usd=0.01,
            quantity=100,
            cost_basis_usd=1.0,
            status=PaperPosition.Status.OPEN,
        )
        candidates = [{"asset_uid": "new", "chain": "solana"}]
        result = apply_overlay(candidates, self.portfolio, self.risk)
        self.assertEqual(len(result), 0)


# ---------------------------------------------------------------------------
# Full generator (integration)
# ---------------------------------------------------------------------------


class TestCandidateGenerator(TestCase):
    def test_dry_run_generates_candidates(self):
        portfolio = PaperPortfolio.objects.create(
            name="DryRun Portfolio",
            initial_cash_usd=10_000,
            cash_usd=10_000,
            total_equity_usd=10_000,
            high_water_mark_usd=10_000,
        )
        tokens = [_make_token(asset_uid=f"sol:token_{i}") for i in range(5)]

        gen = CandidateGenerator()
        with patch.object(gen, 'loader') as mock_loader:
            from paper_trading.playbooks.loader import PlaybookLoader
            real_loader = PlaybookLoader(configs_dir=CONFIGS_DIR)
            real_loader.load()
            mock_loader.load.return_value = None
            mock_loader.get_playbooks.return_value = real_loader.get_playbooks()
            mock_loader.get_global.return_value = real_loader.get_global()

            result = gen.run(tokens, portfolio, dry_run=True)

        # Should generate some candidates (whale_momentum should match)
        self.assertGreater(len(result), 0)
        for c in result:
            self.assertIn("asset_uid", c)
            self.assertIn("priority_score", c)
            self.assertIn("playbook_slug", c)

    def test_empty_tokens(self):
        portfolio = PaperPortfolio.objects.create(
            name="Empty Portfolio",
            initial_cash_usd=10_000,
            cash_usd=10_000,
            total_equity_usd=10_000,
            high_water_mark_usd=10_000,
        )
        gen = CandidateGenerator()
        result = gen.run([], portfolio, dry_run=True)
        self.assertEqual(len(result), 0)

    def test_no_playbooks(self):
        portfolio = PaperPortfolio.objects.create(
            name="NoPB Portfolio",
            initial_cash_usd=10_000,
            cash_usd=10_000,
            total_equity_usd=10_000,
            high_water_mark_usd=10_000,
        )
        tokens = [_make_token()]
        gen = CandidateGenerator()
        with patch.object(gen, 'loader') as mock_loader:
            mock_loader.load.return_value = None
            mock_loader.get_playbooks.return_value = []
            mock_loader.get_global.return_value = (
                __import__("paper_trading.playbooks.loader", fromlist=["GlobalConfig"]).GlobalConfig()
            )
            result = gen.run(tokens, portfolio, dry_run=True)
        self.assertEqual(len(result), 0)
