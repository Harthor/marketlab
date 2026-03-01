"""Run one full paper trading cycle without Celery.

Usage:
    python manage.py run_paper_cycle              # MTM + exits + candidates
    python manage.py run_paper_cycle --mtm-only   # Only mark-to-market + exits
    python manage.py run_paper_cycle --create-portfolio "My Portfolio" --cash 10000
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run one paper trading cycle: MTM + exits + candidate generation"

    def add_arguments(self, parser):
        parser.add_argument(
            "--mtm-only",
            action="store_true",
            help="Only run mark-to-market and exit checks, skip candidate generation",
        )
        parser.add_argument(
            "--create-portfolio",
            type=str,
            default=None,
            help="Create a new portfolio with the given name (if it doesn't exist)",
        )
        parser.add_argument(
            "--cash",
            type=float,
            default=10000.0,
            help="Initial cash for new portfolio (default: 10000)",
        )

    def handle(self, *args, **options):
        from paper_trading.models import PaperPortfolio, RegimeSnapshot
        from paper_trading.trade_engine import PaperTradeEngine

        # Create portfolio if requested
        if options["create_portfolio"]:
            name = options["create_portfolio"]
            cash = Decimal(str(options["cash"]))
            portfolio, created = PaperPortfolio.objects.get_or_create(
                name=name,
                defaults={
                    "initial_cash_usd": cash,
                    "cash_usd": cash,
                    "total_equity_usd": cash,
                    "high_water_mark_usd": cash,
                    "status": "active",
                    "execution_mode": "base",
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"Created portfolio '{name}' (slug={portfolio.slug}) with ${cash} cash"
                ))
            else:
                self.stdout.write(f"Portfolio '{name}' already exists (slug={portfolio.slug})")

        # List active portfolios
        active = PaperPortfolio.objects.filter(status="active")
        if not active.exists():
            self.stdout.write(self.style.WARNING(
                "No active portfolios. Use --create-portfolio to create one."
            ))
            return

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Paper Trading Cycle — {timezone.now().isoformat()}")
        self.stdout.write(f"{'='*60}")

        engine = PaperTradeEngine()

        # Phase 1: Mark-to-market + exits
        self.stdout.write(self.style.MIGRATE_HEADING("\n[Phase 1] Mark-to-market + Exit checks"))
        for portfolio in active:
            exits = engine.check_exits(portfolio)
            snap = engine.take_equity_snapshot(portfolio)
            n_open = portfolio.positions.filter(status="open").count()
            self.stdout.write(
                f"  {portfolio.name}: equity=${snap.total_equity_usd:.2f}  "
                f"cash=${portfolio.cash_usd:.2f}  "
                f"open={n_open}  exits={len(exits)}"
            )

        if options["mtm_only"]:
            self.stdout.write(self.style.SUCCESS("\nDone (MTM only)."))
            return

        # Phase 2: Candidate generation
        self.stdout.write(self.style.MIGRATE_HEADING("\n[Phase 2] Candidate generation"))

        try:
            from api.degen_service import get_watchlist
            watchlist = get_watchlist()
            tokens = watchlist.get("tokens", [])
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  Could not load watchlist: {exc}"))
            return

        if not tokens:
            self.stdout.write(self.style.WARNING("  Empty watchlist — skipping candidates"))
            return

        self.stdout.write(f"  Watchlist: {len(tokens)} tokens loaded")

        try:
            from paper_trading.candidate_engine.generator import CandidateGenerator

            generator = CandidateGenerator()

            for portfolio in active:
                emitted = generator.run(tokens, portfolio)
                self.stdout.write(
                    f"  {portfolio.name}: {len(emitted)} candidates emitted"
                )

            # Save regime snapshot
            regime_result = generator.regime_detector.detect(tokens)
            RegimeSnapshot.objects.create(
                regime=regime_result.current_regime,
                confidence=regime_result.confidence,
                scores={
                    name: {"score": s.score, "components": s.components}
                    for name, s in regime_result.scores.items()
                },
                aggregate_metrics=regime_result.aggregate_metrics,
                token_count=len(tokens),
            )
            self.stdout.write(
                f"  Regime: {regime_result.current_regime} "
                f"(confidence={regime_result.confidence:.0%})"
            )
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"  Candidate generation error: {exc}"))
            logger.exception("Candidate generation failed")
            return

        self.stdout.write(self.style.SUCCESS("\nCycle complete."))
