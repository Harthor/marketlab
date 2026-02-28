"""Tests for the fill simulator."""
from django.test import TestCase

from paper_trading.fill_simulator import simulate_fill


class FillSimulatorBaseTests(TestCase):
    """Test base-mode fill simulation across buckets."""

    def test_meme_bluechip_fill(self):
        result = simulate_fill(
            side="buy",
            token_bucket="meme_bluechip",
            requested_notional_usd=100.0,
            arrival_mid_price_usd=1.0,
            pool_fee_bps=30,
            exit_liquidity_usd=10_000_000,
        )
        self.assertEqual(result["status"], "filled")
        self.assertGreater(result["filled_qty"], 0)
        self.assertGreater(result["executed_price_usd"], 1.0)  # buy = higher price
        self.assertLess(result["impact_bps"], 100)  # small trade in large pool

    def test_dex_new_launch_fill(self):
        result = simulate_fill(
            side="buy",
            token_bucket="dex_new_launch",
            requested_notional_usd=50.0,
            arrival_mid_price_usd=0.001,
            pool_fee_bps=100,
            exit_liquidity_usd=100_000,
        )
        self.assertEqual(result["status"], "filled")
        self.assertGreater(result["impact_bps"], 0)

    def test_sell_side(self):
        result = simulate_fill(
            side="sell",
            token_bucket="meme_liquid",
            requested_notional_usd=200.0,
            arrival_mid_price_usd=5.0,
            pool_fee_bps=30,
            sell_tax_bps=200,
            exit_liquidity_usd=1_000_000,
        )
        self.assertEqual(result["status"], "filled")
        self.assertLess(result["executed_price_usd"], 5.0)  # sell = lower price
        self.assertGreater(result["tax_usd"], 0)

    def test_cpmm_formula(self):
        result = simulate_fill(
            side="buy",
            token_bucket="meme_bluechip",
            requested_notional_usd=1000.0,
            arrival_mid_price_usd=0.50,
            pool_fee_bps=30,
            reserve_quote_usd=500_000,
            reserve_token_units=1_000_000,
            exit_liquidity_usd=500_000,
        )
        self.assertEqual(result["status"], "filled")
        self.assertGreater(result["impact_bps"], 0)

    def test_reject_honeypot(self):
        result = simulate_fill(
            side="buy",
            token_bucket="dex_new_launch",
            requested_notional_usd=100.0,
            arrival_mid_price_usd=0.01,
            pool_fee_bps=30,
            exit_liquidity_usd=50_000,
            security_flags={"honeypot": True},
        )
        self.assertEqual(result["status"], "rejected")
        self.assertIn("Honeypot", result["reject_reason"])

    def test_reject_exceeds_liquidity_cap(self):
        result = simulate_fill(
            side="buy",
            token_bucket="dex_new_launch",
            requested_notional_usd=5000.0,
            arrival_mid_price_usd=0.01,
            pool_fee_bps=30,
            exit_liquidity_usd=10_000,  # cap = 3% = $300
        )
        self.assertEqual(result["status"], "rejected")
        self.assertIn("liquidity cap", result["reject_reason"])

    def test_reject_zero_liquidity(self):
        result = simulate_fill(
            side="buy",
            token_bucket="microcap_listed",
            requested_notional_usd=100.0,
            arrival_mid_price_usd=0.05,
            pool_fee_bps=30,
            exit_liquidity_usd=0,
        )
        self.assertEqual(result["status"], "rejected")

    def test_reject_invalid_price(self):
        result = simulate_fill(
            side="buy",
            token_bucket="meme_bluechip",
            requested_notional_usd=100.0,
            arrival_mid_price_usd=0,
            pool_fee_bps=30,
        )
        self.assertEqual(result["status"], "rejected")

    def test_gas_included(self):
        result = simulate_fill(
            side="buy",
            token_bucket="meme_bluechip",
            requested_notional_usd=100.0,
            arrival_mid_price_usd=1.0,
            pool_fee_bps=30,
            chain_fee_usd=0.50,
            priority_fee_usd=0.10,
            exit_liquidity_usd=10_000_000,
        )
        self.assertEqual(result["status"], "filled")
        self.assertAlmostEqual(result["gas_usd"], 0.60, places=2)


class FillSimulatorStressedTests(TestCase):
    """Test stressed-mode parameters."""

    def test_stressed_higher_impact(self):
        base = simulate_fill(
            side="buy",
            token_bucket="meme_liquid",
            requested_notional_usd=500.0,
            arrival_mid_price_usd=2.0,
            pool_fee_bps=30,
            exit_liquidity_usd=500_000,
            stressed=False,
        )
        stressed = simulate_fill(
            side="buy",
            token_bucket="meme_liquid",
            requested_notional_usd=500.0,
            arrival_mid_price_usd=2.0,
            pool_fee_bps=30,
            exit_liquidity_usd=500_000,
            stressed=True,
        )
        self.assertGreater(stressed["impact_bps"], base["impact_bps"])

    def test_stressed_higher_gas(self):
        base = simulate_fill(
            side="buy",
            token_bucket="meme_bluechip",
            requested_notional_usd=100.0,
            arrival_mid_price_usd=1.0,
            pool_fee_bps=30,
            chain_fee_usd=1.0,
            exit_liquidity_usd=10_000_000,
            stressed=False,
        )
        stressed = simulate_fill(
            side="buy",
            token_bucket="meme_bluechip",
            requested_notional_usd=100.0,
            arrival_mid_price_usd=1.0,
            pool_fee_bps=30,
            chain_fee_usd=1.0,
            exit_liquidity_usd=10_000_000,
            stressed=True,
        )
        self.assertGreater(stressed["gas_usd"], base["gas_usd"])

    def test_stressed_higher_failure_prob(self):
        base = simulate_fill(
            side="buy",
            token_bucket="dex_new_launch",
            requested_notional_usd=50.0,
            arrival_mid_price_usd=0.001,
            pool_fee_bps=100,
            exit_liquidity_usd=100_000,
            stressed=False,
        )
        stressed = simulate_fill(
            side="buy",
            token_bucket="dex_new_launch",
            requested_notional_usd=50.0,
            arrival_mid_price_usd=0.001,
            pool_fee_bps=100,
            exit_liquidity_usd=100_000,
            stressed=True,
        )
        self.assertGreater(
            stressed["failure_probability"], base["failure_probability"]
        )
