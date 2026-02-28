"""Tests for paper trading models."""
from django.test import TestCase

from paper_trading.models import PaperPortfolio, PaperPosition


class PaperPortfolioTests(TestCase):
    def test_create_with_slug(self):
        p = PaperPortfolio.objects.create(name="My Degen Portfolio")
        self.assertEqual(p.slug, "my-degen-portfolio")
        self.assertEqual(p.status, "active")
        self.assertEqual(p.cash_usd, 10_000)

    def test_pnl_calculation(self):
        p = PaperPortfolio.objects.create(
            name="PnL Test",
            initial_cash_usd=10_000,
            total_equity_usd=12_000,
        )
        self.assertAlmostEqual(p.pnl_usd, 2_000)
        self.assertAlmostEqual(p.pnl_pct, 20.0)

    def test_drawdown_calculation(self):
        p = PaperPortfolio.objects.create(
            name="DD Test",
            total_equity_usd=8_000,
            high_water_mark_usd=10_000,
        )
        self.assertAlmostEqual(p.drawdown_pct, 20.0)


class PaperPositionTests(TestCase):
    def setUp(self):
        self.portfolio = PaperPortfolio.objects.create(name="Pos Test")

    def test_mark_to_market(self):
        pos = PaperPosition.objects.create(
            portfolio=self.portfolio,
            asset_uid="solana:TEST",
            symbol="TEST",
            chain="solana",
            entry_price_usd=1.0,
            avg_entry_price_usd=1.0,
            quantity=100,
            cost_basis_usd=100,
        )
        pos.mark_to_market(1.50)
        pos.refresh_from_db()
        self.assertAlmostEqual(pos.current_price_usd, 1.50)
        self.assertAlmostEqual(pos.current_value_usd, 150.0)
        self.assertAlmostEqual(pos.unrealized_pnl_usd, 50.0)
        self.assertAlmostEqual(pos.unrealized_pnl_pct, 50.0)

    def test_partial_close(self):
        pos = PaperPosition.objects.create(
            portfolio=self.portfolio,
            asset_uid="solana:TEST2",
            symbol="TEST2",
            chain="solana",
            entry_price_usd=2.0,
            avg_entry_price_usd=2.0,
            quantity=100,
            cost_basis_usd=200,
        )
        pos.close(exit_price=3.0, quantity_sold=50)
        pos.refresh_from_db()
        self.assertEqual(pos.status, "open")
        self.assertAlmostEqual(pos.quantity, 50.0)
        self.assertAlmostEqual(pos.realized_pnl_usd, 50.0)

    def test_full_close(self):
        pos = PaperPosition.objects.create(
            portfolio=self.portfolio,
            asset_uid="solana:TEST3",
            symbol="TEST3",
            chain="solana",
            entry_price_usd=1.0,
            avg_entry_price_usd=1.0,
            quantity=100,
            cost_basis_usd=100,
        )
        pos.close(exit_price=0.80)
        pos.refresh_from_db()
        self.assertEqual(pos.status, "closed")
        self.assertAlmostEqual(pos.realized_pnl_usd, -20.0)
