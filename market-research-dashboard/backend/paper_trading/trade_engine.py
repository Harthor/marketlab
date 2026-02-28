"""Paper Trade Engine — orchestrates fill simulation, sizing, exits."""
from __future__ import annotations

from django.utils import timezone

from .fill_simulator import simulate_fill
from .models import (
    PaperEquitySnapshot,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
)
from .sizing import compute_position_size


class PaperTradeEngine:
    """Orchestrates paper-trade lifecycle: entry, exit, mark-to-market."""

    def process_candidate(
        self,
        portfolio: PaperPortfolio,
        candidate: dict,
    ) -> PaperTrade:
        """Process a trade candidate through the full pipeline.

        Args:
            portfolio: The paper portfolio to trade in.
            candidate: Dict with keys: asset_uid, symbol, chain, category,
                token_address, token_bucket, arrival_price_usd,
                exit_liquidity_usd, volume_24h_usd, pool_fee_bps,
                buy_tax_bps, sell_tax_bps, chain_fee_usd, priority_fee_usd,
                reserve_quote_usd, reserve_token_units, route_hops,
                security_flags, confidence_multiplier, trigger_type,
                signal_context.

        Returns:
            PaperTrade instance (saved).
        """
        # 1. Validate filters
        reject = self._validate_candidate(portfolio, candidate)
        if reject:
            return self._create_rejected_trade(portfolio, candidate, reject)

        # 2. Compute position size
        notional = compute_position_size(
            equity_usd=portfolio.total_equity_usd,
            base_risk_pct=portfolio.base_risk_pct,
            confidence_multiplier=candidate.get("confidence_multiplier", 1.0),
            exit_liquidity_usd=candidate.get("exit_liquidity_usd", 0),
            volume_24h_usd=candidate.get("volume_24h_usd", 0),
            token_bucket=candidate.get("token_bucket", "microcap_listed"),
            hard_abs_cap_usd=portfolio.hard_abs_cap_usd,
        )
        if notional < 1.0:
            return self._create_rejected_trade(
                portfolio, candidate, "Position size below $1 minimum"
            )

        # 3. Simulate fill (base)
        fill = simulate_fill(
            side="buy",
            token_bucket=candidate.get("token_bucket", "microcap_listed"),
            requested_notional_usd=notional,
            arrival_mid_price_usd=candidate["arrival_price_usd"],
            pool_fee_bps=candidate.get("pool_fee_bps", 30),
            buy_tax_bps=candidate.get("buy_tax_bps", 0),
            sell_tax_bps=candidate.get("sell_tax_bps", 0),
            chain_fee_usd=candidate.get("chain_fee_usd", 0.0),
            priority_fee_usd=candidate.get("priority_fee_usd", 0.0),
            exit_liquidity_usd=candidate.get("exit_liquidity_usd"),
            reserve_quote_usd=candidate.get("reserve_quote_usd"),
            reserve_token_units=candidate.get("reserve_token_units"),
            route_hops=candidate.get("route_hops", 1),
            security_flags=candidate.get("security_flags"),
            stressed=False,
        )

        if fill["status"] == "rejected":
            return self._create_rejected_trade(
                portfolio, candidate, fill["reject_reason"]
            )

        # 4. Stressed fill (if dual mode)
        stressed_fill = None
        if portfolio.execution_mode in ("stressed", "dual"):
            stressed_fill = simulate_fill(
                side="buy",
                token_bucket=candidate.get("token_bucket", "microcap_listed"),
                requested_notional_usd=notional,
                arrival_mid_price_usd=candidate["arrival_price_usd"],
                pool_fee_bps=candidate.get("pool_fee_bps", 30),
                buy_tax_bps=candidate.get("buy_tax_bps", 0),
                sell_tax_bps=candidate.get("sell_tax_bps", 0),
                chain_fee_usd=candidate.get("chain_fee_usd", 0.0),
                priority_fee_usd=candidate.get("priority_fee_usd", 0.0),
                exit_liquidity_usd=candidate.get("exit_liquidity_usd"),
                reserve_quote_usd=candidate.get("reserve_quote_usd"),
                reserve_token_units=candidate.get("reserve_token_units"),
                route_hops=candidate.get("route_hops", 1),
                security_flags=candidate.get("security_flags"),
                stressed=True,
            )

        # 5. Create position
        position = PaperPosition.objects.create(
            portfolio=portfolio,
            asset_uid=candidate["asset_uid"],
            symbol=candidate["symbol"],
            chain=candidate.get("chain", ""),
            entry_price_usd=fill["executed_price_usd"],
            avg_entry_price_usd=fill["executed_price_usd"],
            quantity=fill["filled_qty"],
            cost_basis_usd=fill["filled_notional_usd"],
            current_price_usd=fill["executed_price_usd"],
            current_value_usd=fill["filled_notional_usd"],
            category=candidate.get("category", ""),
            token_address=candidate.get("token_address", ""),
        )

        # 6. Create trade record
        trade = PaperTrade.objects.create(
            portfolio=portfolio,
            position=position,
            asset_uid=candidate["asset_uid"],
            symbol=candidate["symbol"],
            chain=candidate.get("chain", ""),
            token_bucket=candidate.get("token_bucket", ""),
            side=PaperTrade.Side.BUY,
            status=PaperTrade.TradeStatus.FILLED,
            requested_notional_usd=notional,
            filled_notional_usd=fill["filled_notional_usd"],
            filled_quantity=fill["filled_qty"],
            arrival_price_usd=fill["arrival_price_usd"],
            executed_price_usd=fill["executed_price_usd"],
            slippage_bps=fill["slippage_bps"],
            impact_bps=fill["impact_bps"],
            venue_fee_usd=fill["venue_fee_usd"],
            tax_usd=fill["tax_usd"],
            gas_usd=fill["gas_usd"],
            total_cost_usd=fill["total_cost_usd"],
            failure_probability=fill["failure_probability"],
            liquidity_snapshot={
                "exit_liquidity_usd": candidate.get("exit_liquidity_usd"),
                "reserve_quote_usd": candidate.get("reserve_quote_usd"),
                "reserve_token_units": candidate.get("reserve_token_units"),
            },
            signal_context=candidate.get("signal_context", {}),
            trigger_type=candidate.get("trigger_type", ""),
            stressed_executed_price_usd=(
                stressed_fill["executed_price_usd"] if stressed_fill else None
            ),
            stressed_impact_bps=(
                stressed_fill["impact_bps"] if stressed_fill else None
            ),
            stressed_total_cost_usd=(
                stressed_fill["total_cost_usd"] if stressed_fill else None
            ),
            stressed_failure_probability=(
                stressed_fill["failure_probability"] if stressed_fill else None
            ),
        )

        # 7. Update portfolio cash
        total_spent = fill["filled_notional_usd"] + fill["total_cost_usd"]
        portfolio.cash_usd -= total_spent
        portfolio.save()

        return trade

    def check_exits(self, portfolio: PaperPortfolio) -> list[PaperTrade]:
        """Evaluate exit conditions for all open positions."""
        exit_trades = []
        now = timezone.now()

        for pos in portfolio.positions.filter(status=PaperPosition.Status.OPEN):
            reason = self._should_exit(portfolio, pos, now)
            if reason:
                trade = self._execute_exit(portfolio, pos, reason)
                exit_trades.append(trade)

        return exit_trades

    def take_equity_snapshot(
        self, portfolio: PaperPortfolio
    ) -> PaperEquitySnapshot:
        """Mark-to-market all positions and create an equity snapshot."""
        positions_value = 0.0
        open_count = 0
        for pos in portfolio.positions.filter(status=PaperPosition.Status.OPEN):
            positions_value += pos.current_value_usd
            open_count += 1

        total_equity = portfolio.cash_usd + positions_value
        portfolio.total_equity_usd = total_equity
        if total_equity > portfolio.high_water_mark_usd:
            portfolio.high_water_mark_usd = total_equity
        portfolio.save()

        return PaperEquitySnapshot.objects.create(
            portfolio=portfolio,
            cash_usd=portfolio.cash_usd,
            positions_value_usd=positions_value,
            total_equity_usd=total_equity,
            drawdown_pct=portfolio.drawdown_pct,
            open_positions=open_count,
        )

    # --- Private helpers ---

    def _validate_candidate(
        self, portfolio: PaperPortfolio, candidate: dict
    ) -> str:
        """Return rejection reason or empty string if valid."""
        if portfolio.status != PaperPortfolio.Status.ACTIVE:
            return "Portfolio is not active"

        if portfolio.cash_usd < 1.0:
            return "Insufficient cash"

        open_count = portfolio.positions.filter(
            status=PaperPosition.Status.OPEN
        ).count()
        if open_count >= portfolio.max_positions:
            return f"Max positions reached ({portfolio.max_positions})"

        # Already have position in this asset?
        existing = portfolio.positions.filter(
            asset_uid=candidate.get("asset_uid", ""),
            status=PaperPosition.Status.OPEN,
        ).exists()
        if existing:
            return "Already holding this asset"

        liq = candidate.get("exit_liquidity_usd", 0)
        if liq is not None and liq < 1000:
            return "Exit liquidity below $1000 minimum"

        return ""

    def _create_rejected_trade(
        self,
        portfolio: PaperPortfolio,
        candidate: dict,
        reason: str,
    ) -> PaperTrade:
        return PaperTrade.objects.create(
            portfolio=portfolio,
            asset_uid=candidate.get("asset_uid", ""),
            symbol=candidate.get("symbol", ""),
            chain=candidate.get("chain", ""),
            token_bucket=candidate.get("token_bucket", ""),
            side=PaperTrade.Side.BUY,
            status=PaperTrade.TradeStatus.REJECTED,
            requested_notional_usd=0,
            arrival_price_usd=candidate.get("arrival_price_usd", 0),
            reject_reason=reason,
            trigger_type=candidate.get("trigger_type", ""),
            signal_context=candidate.get("signal_context", {}),
        )

    def _should_exit(
        self,
        portfolio: PaperPortfolio,
        pos: PaperPosition,
        now,
    ) -> str:
        """Check all exit conditions. Return reason string or empty."""
        # Time stop
        if pos.opened_at:
            hours_held = (now - pos.opened_at).total_seconds() / 3600
            if hours_held >= portfolio.max_holding_hours:
                return "time_stop"

        # Price stop (loss from entry)
        if pos.avg_entry_price_usd > 0 and pos.current_price_usd > 0:
            loss_pct = 1 - pos.current_price_usd / pos.avg_entry_price_usd
            if loss_pct >= portfolio.stop_loss_pct:
                return "stop_loss"

        # Rug detection — price dropped > 90%
        if pos.avg_entry_price_usd > 0 and pos.current_price_usd > 0:
            drop = 1 - pos.current_price_usd / pos.avg_entry_price_usd
            if drop >= 0.90:
                return "rug_detected"

        return ""

    def _execute_exit(
        self,
        portfolio: PaperPortfolio,
        pos: PaperPosition,
        reason: str,
    ) -> PaperTrade:
        """Execute a sell for an open position."""
        if reason == "rug_detected":
            pos.write_off()
            return PaperTrade.objects.create(
                portfolio=portfolio,
                position=pos,
                asset_uid=pos.asset_uid,
                symbol=pos.symbol,
                chain=pos.chain,
                side=PaperTrade.Side.SELL,
                status=PaperTrade.TradeStatus.FILLED,
                requested_notional_usd=0,
                filled_notional_usd=0,
                filled_quantity=0,
                arrival_price_usd=pos.current_price_usd,
                executed_price_usd=0,
                trigger_type=reason,
            )

        # Normal exit at current price
        exit_price = pos.current_price_usd
        notional = pos.quantity * exit_price

        pos.close(exit_price)
        portfolio.cash_usd += notional
        portfolio.save()

        return PaperTrade.objects.create(
            portfolio=portfolio,
            position=pos,
            asset_uid=pos.asset_uid,
            symbol=pos.symbol,
            chain=pos.chain,
            side=PaperTrade.Side.SELL,
            status=PaperTrade.TradeStatus.FILLED,
            requested_notional_usd=notional,
            filled_notional_usd=notional,
            filled_quantity=pos.quantity,
            arrival_price_usd=exit_price,
            executed_price_usd=exit_price,
            trigger_type=reason,
        )
