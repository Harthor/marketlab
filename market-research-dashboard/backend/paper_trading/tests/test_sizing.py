"""Tests for position sizing."""
from django.test import TestCase

from paper_trading.sizing import compute_position_size


class SizingTests(TestCase):
    def test_basic_sizing(self):
        size = compute_position_size(
            equity_usd=10_000,
            base_risk_pct=0.01,
            confidence_multiplier=1.0,
            exit_liquidity_usd=1_000_000,
            volume_24h_usd=5_000_000,
            token_bucket="meme_bluechip",
        )
        # raw = 10000 * 0.01 * 1.0 = 100
        # liq_cap = 1M * 0.05 = 50000
        # vol_cap = 5M * 0.02 = 100000
        # hard_cap = 500
        # min(100, 50000, 100000, 500) = 100
        self.assertAlmostEqual(size, 100.0)

    def test_liquidity_cap_binding(self):
        size = compute_position_size(
            equity_usd=100_000,
            base_risk_pct=0.05,
            confidence_multiplier=2.0,
            exit_liquidity_usd=10_000,
            volume_24h_usd=1_000_000,
            token_bucket="dex_new_launch",
        )
        # raw = 100000 * 0.05 * 2.0 = 10000
        # liq_cap = 10000 * 0.01 = 100
        # vol_cap = 1M * 0.003 = 3000
        # hard_cap = 500
        # min(10000, 100, 3000, 500) = 100
        self.assertAlmostEqual(size, 100.0)

    def test_volume_cap_binding(self):
        size = compute_position_size(
            equity_usd=50_000,
            base_risk_pct=0.02,
            confidence_multiplier=1.5,
            exit_liquidity_usd=10_000_000,
            volume_24h_usd=5000,
            token_bucket="microcap_listed",
        )
        # raw = 50000 * 0.02 * 1.5 = 1500
        # liq_cap = 10M * 0.02 = 200000
        # vol_cap = 5000 * 0.005 = 25
        # hard_cap = 500
        # min(1500, 200000, 25, 500) = 25
        self.assertAlmostEqual(size, 25.0)

    def test_hard_cap_binding(self):
        size = compute_position_size(
            equity_usd=100_000,
            base_risk_pct=0.05,
            confidence_multiplier=2.0,
            exit_liquidity_usd=100_000_000,
            volume_24h_usd=100_000_000,
            token_bucket="meme_bluechip",
            hard_abs_cap_usd=500.0,
        )
        # raw = 100000 * 0.05 * 2.0 = 10000
        # liq_cap = huge, vol_cap = huge
        # hard_cap = 500
        self.assertAlmostEqual(size, 500.0)

    def test_zero_equity(self):
        size = compute_position_size(
            equity_usd=0,
            base_risk_pct=0.01,
            confidence_multiplier=1.0,
            exit_liquidity_usd=1_000_000,
            volume_24h_usd=1_000_000,
            token_bucket="meme_bluechip",
        )
        self.assertEqual(size, 0.0)
