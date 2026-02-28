"""Celery tasks for paper trading."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="paper_trading.hourly")
def paper_trading_hourly():
    """Every 1h: mark-to-market + check exits + equity snapshot."""
    from .models import PaperPortfolio
    from .trade_engine import PaperTradeEngine

    engine = PaperTradeEngine()
    results = []

    for portfolio in PaperPortfolio.objects.filter(status="active"):
        exits = engine.check_exits(portfolio)
        snap = engine.take_equity_snapshot(portfolio)
        results.append({
            "portfolio": portfolio.slug,
            "exits": len(exits),
            "equity": snap.total_equity_usd,
        })

    return results


@shared_task(name="paper_trading.generate_candidates")
def generate_candidates_task():
    """Hourly: detect regime + evaluate playbooks + emit candidates.

    Runs after paper_trading.hourly so exits and MTM are fresh.
    """
    from .candidate_engine.generator import CandidateGenerator
    from .models import PaperPortfolio, RegimeSnapshot

    # Load watchlist
    try:
        from api.degen_service import get_watchlist
        watchlist = get_watchlist()
        tokens = watchlist.get("tokens", [])
    except Exception:
        logger.warning("Could not load degen watchlist for candidate generation")
        return {"error": "watchlist_unavailable"}

    if not tokens:
        return {"skipped": "empty_watchlist"}

    generator = CandidateGenerator()
    results = []

    for portfolio in PaperPortfolio.objects.filter(status="active"):
        emitted = generator.run(tokens, portfolio)
        results.append({
            "portfolio": portfolio.slug,
            "emitted": len(emitted),
        })

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

    return results
