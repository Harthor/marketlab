"""Tests for the trade engine — end-to-end paper trading flow."""
from django.test import TestCase

from paper_trading.models import PaperPortfolio, PaperPosition
from paper_trading.trade_engine import PaperTradeEngine


def _make_candidate(**overrides):
    base = {
        "asset_uid": "solana:TEST_TOKEN",
        "symbol": "TEST",
        "chain": "solana",
        "category": "meme_emerging",
        "token_address": "TESTADDR123",
        "token_bucket": "meme_liquid",
        "arrival_price_usd": 0.50,
        "exit_liquidity_usd": 500_000,
        "volume_24h_usd": 2_000_000,
        "pool_fee_bps": 30,
        "buy_tax_bps": 0,
        "sell_tax_bps": 0,
        "chain_fee_usd": 0.01,
        "priority_fee_usd": 0.005,
        "route_hops": 1,
        "security_flags": {},
        "confidence_multiplier": 1.5,
        "trigger_type": "smart_money",
        "signal_context": {"source": "test"},
    }
    base.update(overrides)
    return base


class TradeEngineTests(TestCase):
    def setUp(self):
        self.portfolio = PaperPortfolio.objects.create(
            name="Test Portfolio",
            slug="test-portfolio",
            initial_cash_usd=10_000,
            cash_usd=10_000,
            total_equity_usd=10_000,
            high_water_mark_usd=10_000,
            execution_mode="base",
        )
        self.engine = PaperTradeEngine()

    def test_full_buy_flow(self):
        candidate = _make_candidate()
        trade = self.engine.process_candidate(self.portfolio, candidate)

        self.assertEqual(trade.status, "filled")
        self.assertEqual(trade.side, "buy")
        self.assertGreater(trade.filled_quantity, 0)
        self.assertGreater(trade.filled_notional_usd, 0)
        self.assertEqual(trade.trigger_type, "smart_money")

        # Position created
        pos = PaperPosition.objects.get(portfolio=self.portfolio, asset_uid="solana:TEST_TOKEN")
        self.assertEqual(pos.status, "open")
        self.assertGreater(pos.quantity, 0)

        # Cash reduced
        self.portfolio.refresh_from_db()
        self.assertLess(self.portfolio.cash_usd, 10_000)

    def test_dual_mode_fills(self):
        self.portfolio.execution_mode = "dual"
        self.portfolio.save()

        candidate = _make_candidate()
        trade = self.engine.process_candidate(self.portfolio, candidate)

        self.assertEqual(trade.status, "filled")
        self.assertIsNotNone(trade.stressed_executed_price_usd)
        self.assertIsNotNone(trade.stressed_impact_bps)
        self.assertGreater(trade.stressed_impact_bps, trade.impact_bps)

    def test_reject_max_positions(self):
        self.portfolio.max_positions = 1
        self.portfolio.save()

        # Fill first position
        c1 = _make_candidate(asset_uid="solana:T1", symbol="T1")
        t1 = self.engine.process_candidate(self.portfolio, c1)
        self.assertEqual(t1.status, "filled")

        # Second should be rejected
        c2 = _make_candidate(asset_uid="solana:T2", symbol="T2")
        t2 = self.engine.process_candidate(self.portfolio, c2)
        self.assertEqual(t2.status, "rejected")
        self.assertIn("Max positions", t2.reject_reason)

    def test_reject_duplicate_asset(self):
        c1 = _make_candidate()
        self.engine.process_candidate(self.portfolio, c1)

        c2 = _make_candidate()
        t2 = self.engine.process_candidate(self.portfolio, c2)
        self.assertEqual(t2.status, "rejected")
        self.assertIn("Already holding", t2.reject_reason)

    def test_reject_low_liquidity(self):
        candidate = _make_candidate(exit_liquidity_usd=500)
        trade = self.engine.process_candidate(self.portfolio, candidate)
        self.assertEqual(trade.status, "rejected")
        self.assertIn("liquidity", trade.reject_reason.lower())

    def test_equity_snapshot(self):
        candidate = _make_candidate()
        self.engine.process_candidate(self.portfolio, candidate)

        snap = self.engine.take_equity_snapshot(self.portfolio)
        self.assertGreater(snap.total_equity_usd, 0)
        self.assertEqual(snap.open_positions, 1)


class WriteOffTests(TestCase):
    def setUp(self):
        self.portfolio = PaperPortfolio.objects.create(
            name="WriteOff Test",
            slug="writeoff-test",
            initial_cash_usd=10_000,
            cash_usd=10_000,
            total_equity_usd=10_000,
            high_water_mark_usd=10_000,
        )

    def test_write_off(self):
        pos = PaperPosition.objects.create(
            portfolio=self.portfolio,
            asset_uid="solana:RUG",
            symbol="RUG",
            chain="solana",
            entry_price_usd=1.0,
            avg_entry_price_usd=1.0,
            quantity=100,
            cost_basis_usd=100,
            current_price_usd=1.0,
            current_value_usd=100,
        )

        pos.write_off()
        pos.refresh_from_db()

        self.assertEqual(pos.status, "written_off")
        self.assertEqual(pos.current_price_usd, 0.0)
        self.assertEqual(pos.current_value_usd, 0.0)
        self.assertEqual(pos.realized_pnl_usd, -100.0)
        self.assertIsNotNone(pos.closed_at)


class ExitCheckTests(TestCase):
    def setUp(self):
        self.portfolio = PaperPortfolio.objects.create(
            name="Exit Test",
            slug="exit-test",
            initial_cash_usd=10_000,
            cash_usd=9_000,
            total_equity_usd=10_000,
            high_water_mark_usd=10_000,
            max_holding_hours=24,
            stop_loss_pct=0.20,
        )
        self.engine = PaperTradeEngine()

    def test_stop_loss_exit(self):
        PaperPosition.objects.create(
            portfolio=self.portfolio,
            asset_uid="solana:DUMP",
            symbol="DUMP",
            chain="solana",
            entry_price_usd=1.0,
            avg_entry_price_usd=1.0,
            quantity=100,
            cost_basis_usd=100,
            current_price_usd=0.70,  # 30% loss > 20% stop
            current_value_usd=70,
        )

        exits = self.engine.check_exits(self.portfolio)
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0].trigger_type, "stop_loss")
