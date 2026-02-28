"""Portfolio overlay — apply global risk limits before emitting candidates."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

from paper_trading.models import PaperPortfolio, PaperPosition, PaperTrade
from paper_trading.playbooks.loader import PortfolioRiskConfig

logger = logging.getLogger(__name__)


def apply_overlay(
    candidates: list[dict[str, Any]],
    portfolio: PaperPortfolio,
    risk_config: PortfolioRiskConfig,
) -> list[dict[str, Any]]:
    """Filter candidates through portfolio risk limits.

    Checks (in order):
        1. Circuit breaker: drawdown too deep → reject ALL
        2. Circuit breaker: consecutive loss streak → reject ALL
        3. Max positions: skip if portfolio is full
        4. Max daily trades: skip if daily limit reached
        5. Max per chain: skip if chain cap reached
        6. Already holding: skip duplicate asset_uid

    Returns:
        Filtered list of candidates that pass all checks.
    """
    # Circuit breakers (reject ALL if tripped)
    if portfolio.drawdown_pct >= risk_config.circuit_breaker_drawdown_pct:
        logger.warning(
            "Circuit breaker: drawdown %.1f%% >= %.1f%%",
            portfolio.drawdown_pct,
            risk_config.circuit_breaker_drawdown_pct,
        )
        return []

    if _consecutive_losses(portfolio) >= risk_config.circuit_breaker_loss_streak:
        logger.warning("Circuit breaker: loss streak >= %d", risk_config.circuit_breaker_loss_streak)
        return []

    # Current state
    open_positions = list(
        portfolio.positions.filter(status=PaperPosition.Status.OPEN),
    )
    open_count = len(open_positions)
    open_uids = {p.asset_uid for p in open_positions}
    chain_counts = _count_by_chain(open_positions)
    daily_trades = _count_daily_trades(portfolio)

    accepted = []
    for c in candidates:
        uid = c.get("asset_uid", "")
        chain = c.get("chain", "")

        # Max positions
        if open_count >= risk_config.max_positions:
            logger.debug("Skip %s: max positions reached", uid)
            continue

        # Max daily trades
        if daily_trades >= risk_config.max_daily_trades:
            logger.debug("Skip %s: daily trade limit reached", uid)
            continue

        # Already holding
        if uid in open_uids:
            logger.debug("Skip %s: already holding", uid)
            continue

        # Max per chain
        if chain and chain_counts.get(chain, 0) >= risk_config.max_per_chain:
            logger.debug("Skip %s: chain cap for %s", uid, chain)
            continue

        accepted.append(c)
        open_count += 1
        open_uids.add(uid)
        chain_counts[chain] = chain_counts.get(chain, 0) + 1
        daily_trades += 1

    return accepted


def _consecutive_losses(portfolio: PaperPortfolio) -> int:
    """Count consecutive sell trades with negative PnL (most recent first)."""
    recent_sells = (
        PaperTrade.objects.filter(
            portfolio=portfolio,
            side=PaperTrade.Side.SELL,
            status=PaperTrade.TradeStatus.FILLED,
        )
        .order_by("-executed_at")[:20]
    )
    streak = 0
    for trade in recent_sells:
        if trade.position and trade.position.realized_pnl_usd < 0:
            streak += 1
        else:
            break
    return streak


def _count_by_chain(positions: list[PaperPosition]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in positions:
        counts[p.chain] = counts.get(p.chain, 0) + 1
    return counts


def _count_daily_trades(portfolio: PaperPortfolio) -> int:
    cutoff = timezone.now() - timedelta(hours=24)
    return PaperTrade.objects.filter(
        portfolio=portfolio,
        side=PaperTrade.Side.BUY,
        executed_at__gte=cutoff,
    ).count()
