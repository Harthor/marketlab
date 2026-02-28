"""Tests for playbook system: helpers, loader, evaluator, confidence."""
from __future__ import annotations

from pathlib import Path

from django.test import TestCase

from paper_trading.playbooks.confidence import ConfidenceCalculator
from paper_trading.playbooks.evaluator import (
    EvalResult,
    PlaybookEvaluator,
    _eval_condition,
    _resolve_field,
)
from paper_trading.playbooks.helpers import boolf, clip01, inv_ramp, ramp
from paper_trading.playbooks.loader import (
    ConditionConfig,
    ConfidenceComponent,
    GlobalConfig,
    PlaybookConfig,
    PlaybookLoader,
)

CONFIGS_DIR = (
    Path(__file__).resolve().parent.parent / "configs" / "playbooks"
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers(TestCase):
    """Test ramp, inv_ramp, clip01, boolf."""

    def test_clip01_within_range(self):
        self.assertEqual(clip01(0.5), 0.5)

    def test_clip01_below_zero(self):
        self.assertEqual(clip01(-3), 0.0)

    def test_clip01_above_one(self):
        self.assertEqual(clip01(5), 1.0)

    def test_ramp_below_lo(self):
        self.assertAlmostEqual(ramp(10, 20, 80), 0.0)

    def test_ramp_above_hi(self):
        self.assertAlmostEqual(ramp(100, 20, 80), 1.0)

    def test_ramp_midpoint(self):
        self.assertAlmostEqual(ramp(50, 0, 100), 0.5)

    def test_ramp_lo_equals_hi(self):
        self.assertEqual(ramp(5, 5, 5), 1.0)
        self.assertEqual(ramp(3, 5, 5), 0.0)

    def test_inv_ramp_below_lo(self):
        self.assertAlmostEqual(inv_ramp(10, 20, 80), 1.0)

    def test_inv_ramp_above_hi(self):
        self.assertAlmostEqual(inv_ramp(100, 20, 80), 0.0)

    def test_inv_ramp_midpoint(self):
        self.assertAlmostEqual(inv_ramp(50, 0, 100), 0.5)

    def test_inv_ramp_lo_equals_hi(self):
        self.assertEqual(inv_ramp(5, 5, 5), 0.0)
        self.assertEqual(inv_ramp(3, 5, 5), 1.0)

    def test_boolf_truthy(self):
        self.assertEqual(boolf(True), 1.0)
        self.assertEqual(boolf(42), 1.0)
        self.assertEqual(boolf("yes"), 1.0)

    def test_boolf_falsy(self):
        self.assertEqual(boolf(False), 0.0)
        self.assertEqual(boolf(0), 0.0)
        self.assertEqual(boolf(None), 0.0)
        self.assertEqual(boolf(""), 0.0)


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


class TestConditionEval(TestCase):
    """Test _resolve_field and _eval_condition."""

    def test_resolve_flat_field(self):
        state = {"risk_score": 42}
        self.assertEqual(_resolve_field(state, "risk_score"), 42)

    def test_resolve_nested_field(self):
        state = {"smart_money": {"consensus_score": 75}}
        self.assertEqual(
            _resolve_field(state, "smart_money.consensus_score"), 75,
        )

    def test_resolve_missing_field(self):
        self.assertIsNone(_resolve_field({}, "missing"))

    def test_eval_gt(self):
        c = ConditionConfig(field="score", operator="gt", value=50)
        self.assertTrue(_eval_condition({"score": 60}, c))
        self.assertFalse(_eval_condition({"score": 50}, c))

    def test_eval_gte(self):
        c = ConditionConfig(field="score", operator="gte", value=50)
        self.assertTrue(_eval_condition({"score": 50}, c))

    def test_eval_lt(self):
        c = ConditionConfig(field="x", operator="lt", value=10)
        self.assertTrue(_eval_condition({"x": 5}, c))
        self.assertFalse(_eval_condition({"x": 15}, c))

    def test_eval_eq(self):
        c = ConditionConfig(field="dir", operator="eq", value="accumulate")
        self.assertTrue(_eval_condition({"dir": "accumulate"}, c))
        self.assertFalse(_eval_condition({"dir": "dump"}, c))

    def test_eval_neq(self):
        c = ConditionConfig(field="dir", operator="neq", value="dump")
        self.assertTrue(_eval_condition({"dir": "accumulate"}, c))

    def test_eval_in(self):
        c = ConditionConfig(
            field="chain", operator="in", value=["solana", "base"],
        )
        self.assertTrue(_eval_condition({"chain": "solana"}, c))
        self.assertFalse(_eval_condition({"chain": "bsc"}, c))

    def test_eval_between(self):
        c = ConditionConfig(
            field="pct", operator="between", value=[-60, -15],
        )
        self.assertTrue(_eval_condition({"pct": -30}, c))
        self.assertFalse(_eval_condition({"pct": -5}, c))

    def test_eval_missing_field_returns_false(self):
        c = ConditionConfig(field="missing", operator="gte", value=0)
        self.assertFalse(_eval_condition({}, c))


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class TestPlaybookLoader(TestCase):
    """Test PlaybookLoader with real YAML configs."""

    def setUp(self):
        self.loader = PlaybookLoader(configs_dir=CONFIGS_DIR)
        self.loader.load()

    def test_loads_all_playbooks(self):
        pbs = self.loader.get_playbooks()
        slugs = {p.slug for p in pbs}
        self.assertIn("whale_momentum", slugs)
        self.assertIn("fresh_sniper", slugs)
        self.assertIn("dip_recovery", slugs)
        self.assertIn("liquidity_surge", slugs)
        self.assertIn("social_viral", slugs)
        self.assertIn("volume_breakout", slugs)
        self.assertIn("smart_dip_buy", slugs)
        self.assertEqual(len(pbs), 7)

    def test_global_config_loaded(self):
        g = self.loader.get_global()
        self.assertIsInstance(g, GlobalConfig)
        self.assertGreater(len(g.vetos), 0)
        self.assertGreater(len(g.filters), 0)
        self.assertEqual(g.portfolio_risk.max_positions, 10)

    def test_get_playbook_by_slug(self):
        pb = self.loader.get_playbook("whale_momentum")
        self.assertIsNotNone(pb)
        self.assertEqual(pb.name, "Whale Momentum")
        self.assertGreater(len(pb.required), 0)
        self.assertGreater(len(pb.confidence_components), 0)

    def test_missing_dir_no_crash(self):
        loader = PlaybookLoader(configs_dir=Path("/tmp/nonexistent_dir_xyz"))
        loader.load()
        self.assertEqual(len(loader.get_playbooks()), 0)

    def test_reload(self):
        self.loader.reload()
        self.assertEqual(len(self.loader.get_playbooks()), 7)

    def test_playbook_has_regime_fit(self):
        pb = self.loader.get_playbook("whale_momentum")
        self.assertIn("mania", pb.regime_fit)
        self.assertIn("capitulation", pb.regime_fit)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


def _make_whale_token() -> dict:
    """Token state that should match whale_momentum playbook."""
    return {
        "asset_uid": "sol:pump_abc",
        "symbol": "ABC",
        "chain": "solana",
        "category": "meme",
        "universe_score": 65,
        "risk_score": 30,
        "liquidity_usd": 80000,
        "volume_24h_usd": 50000,
        "market_cap_usd": 500000,
        "age_hours": 100,
        "smart_money": {
            "consensus_direction": "accumulate",
            "consensus_score": 72,
            "unique_wallets_buying": 3,
            "tier_a_active": True,
            "accumulation_net_usd": 15000,
        },
    }


class TestPlaybookEvaluator(TestCase):
    """Test PlaybookEvaluator."""

    def setUp(self):
        self.loader = PlaybookLoader(configs_dir=CONFIGS_DIR)
        self.loader.load()
        self.evaluator = PlaybookEvaluator(
            global_config=self.loader.get_global(),
        )

    def test_whale_momentum_passes(self):
        pb = self.loader.get_playbook("whale_momentum")
        token = _make_whale_token()
        result = self.evaluator.evaluate(pb, token)
        self.assertTrue(result.passed)
        self.assertFalse(result.vetoed)
        self.assertEqual(result.required_passed, result.required_total)

    def test_whale_momentum_fails_low_consensus(self):
        pb = self.loader.get_playbook("whale_momentum")
        token = _make_whale_token()
        token["smart_money"]["consensus_score"] = 20
        result = self.evaluator.evaluate(pb, token)
        self.assertFalse(result.passed)

    def test_global_veto_high_risk(self):
        pb = self.loader.get_playbook("whale_momentum")
        token = _make_whale_token()
        token["risk_score"] = 90  # global veto at >= 85
        result = self.evaluator.evaluate(pb, token)
        self.assertTrue(result.vetoed)
        self.assertIn("global_veto", result.veto_reason)

    def test_playbook_veto(self):
        pb = self.loader.get_playbook("whale_momentum")
        token = _make_whale_token()
        token["smart_money"]["consensus_score"] = 35  # playbook veto at < 40
        result = self.evaluator.evaluate(pb, token)
        self.assertTrue(result.vetoed)
        self.assertIn("playbook_veto", result.veto_reason)

    def test_filter_wrong_chain(self):
        """Playbook with chain filter should fail for wrong chain."""
        pb = PlaybookConfig(
            name="Test",
            slug="test",
            chains=["solana"],
            required=[],
        )
        evaluator = PlaybookEvaluator()
        result = evaluator.evaluate(pb, {"chain": "bsc"})
        self.assertFalse(result.passed)

    def test_filter_low_liquidity(self):
        pb = self.loader.get_playbook("whale_momentum")
        token = _make_whale_token()
        token["liquidity_usd"] = 5000  # below playbook min 20000
        result = self.evaluator.evaluate(pb, token)
        self.assertFalse(result.passed)

    def test_fresh_sniper_passes(self):
        pb = self.loader.get_playbook("fresh_sniper")
        token = {
            "universe_score": 80,
            "risk_score": 25,
            "liquidity_usd": 60000,
            "volume_24h_usd": 100000,
            "age_hours": 12,
            "chain": "solana",
        }
        result = self.evaluator.evaluate(pb, token)
        self.assertTrue(result.passed)

    def test_fresh_sniper_too_old(self):
        pb = self.loader.get_playbook("fresh_sniper")
        token = {
            "universe_score": 80,
            "risk_score": 25,
            "liquidity_usd": 60000,
            "volume_24h_usd": 100000,
            "age_hours": 72,  # too old (> max_age_hours 48)
        }
        result = self.evaluator.evaluate(pb, token)
        self.assertFalse(result.passed)

    def test_confirmations_counted(self):
        pb = self.loader.get_playbook("whale_momentum")
        token = _make_whale_token()
        result = self.evaluator.evaluate(pb, token)
        self.assertTrue(result.passed)
        self.assertGreater(result.confirmations_passed, 0)

    def test_check_global_veto(self):
        reason = self.evaluator.check_global_veto({"risk_score": 90})
        self.assertIn("global_veto", reason)

    def test_check_global_veto_clean(self):
        reason = self.evaluator.check_global_veto(
            {"risk_score": 30, "liquidity_usd": 50000},
        )
        self.assertEqual(reason, "")

    def test_check_global_filters(self):
        ok = self.evaluator.check_global_filters({
            "liquidity_usd": 50000,
            "volume_24h_usd": 20000,
            "risk_score": 30,
        })
        self.assertTrue(ok)

    def test_check_global_filters_fail(self):
        ok = self.evaluator.check_global_filters({
            "liquidity_usd": 500,  # below 10000
            "volume_24h_usd": 20000,
            "risk_score": 30,
        })
        self.assertFalse(ok)


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


class TestConfidenceCalculator(TestCase):
    """Test ConfidenceCalculator."""

    def setUp(self):
        self.loader = PlaybookLoader(configs_dir=CONFIGS_DIR)
        self.loader.load()
        self.evaluator = PlaybookEvaluator(
            global_config=self.loader.get_global(),
        )
        self.calculator = ConfidenceCalculator()

    def test_whale_momentum_confidence(self):
        pb = self.loader.get_playbook("whale_momentum")
        token = _make_whale_token()
        result = self.evaluator.evaluate(pb, token)
        self.assertTrue(result.passed)
        conf = self.calculator.compute(pb, token, result)
        # Should be between base (0.55) and 1.0
        self.assertGreaterEqual(conf, 0.55)
        self.assertLessEqual(conf, 1.0)

    def test_failed_eval_zero_confidence(self):
        pb = self.loader.get_playbook("whale_momentum")
        result = EvalResult("whale_momentum")
        result.passed = False
        conf = self.calculator.compute(pb, {}, result)
        self.assertEqual(conf, 0.0)

    def test_confidence_increases_with_score(self):
        """Higher consensus_score → higher confidence."""
        pb = self.loader.get_playbook("whale_momentum")
        token_low = _make_whale_token()
        token_low["smart_money"]["consensus_score"] = 56
        token_high = _make_whale_token()
        token_high["smart_money"]["consensus_score"] = 88

        res_low = self.evaluator.evaluate(pb, token_low)
        res_high = self.evaluator.evaluate(pb, token_high)
        conf_low = self.calculator.compute(pb, token_low, res_low)
        conf_high = self.calculator.compute(pb, token_high, res_high)
        self.assertGreater(conf_high, conf_low)

    def test_confidence_clamped_01(self):
        """Confidence should always be in [0, 1]."""
        pb = PlaybookConfig(
            name="Test",
            slug="test",
            base_confidence=0.9,
            confidence_components=[
                ConfidenceComponent(
                    field="score", weight=10, func="ramp", lo=0, hi=10,
                ),
            ],
        )
        result = EvalResult("test")
        result.passed = True
        conf = self.calculator.compute(pb, {"score": 100}, result)
        self.assertLessEqual(conf, 1.0)
        self.assertGreaterEqual(conf, 0.0)

    def test_no_components_uses_base(self):
        """Without components, confidence equals base_confidence."""
        pb = PlaybookConfig(name="T", slug="t", base_confidence=0.6)
        result = EvalResult("t")
        result.passed = True
        conf = self.calculator.compute(pb, {}, result)
        self.assertAlmostEqual(conf, 0.6, places=2)
