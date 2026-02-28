"""Paper Trading API views."""
from __future__ import annotations

from django.db.models import Avg, Count, Sum
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    RegimeSnapshot,
)
from .serializers import PortfolioCreateSerializer, PortfolioUpdateSerializer


def _portfolio_to_dict(p: PaperPortfolio) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "slug": p.slug,
        "status": p.status,
        "execution_mode": p.execution_mode,
        "initial_cash_usd": p.initial_cash_usd,
        "cash_usd": p.cash_usd,
        "total_equity_usd": p.total_equity_usd,
        "high_water_mark_usd": p.high_water_mark_usd,
        "pnl_usd": p.pnl_usd,
        "pnl_pct": round(p.pnl_pct, 2),
        "drawdown_pct": round(p.drawdown_pct, 2),
        "open_position_count": p.open_position_count,
        "max_positions": p.max_positions,
        "base_risk_pct": p.base_risk_pct,
        "hard_abs_cap_usd": p.hard_abs_cap_usd,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _position_to_dict(pos: PaperPosition) -> dict:
    return {
        "id": str(pos.id),
        "asset_uid": pos.asset_uid,
        "symbol": pos.symbol,
        "chain": pos.chain,
        "status": pos.status,
        "category": pos.category,
        "entry_price_usd": pos.entry_price_usd,
        "avg_entry_price_usd": pos.avg_entry_price_usd,
        "quantity": pos.quantity,
        "cost_basis_usd": pos.cost_basis_usd,
        "current_price_usd": pos.current_price_usd,
        "current_value_usd": pos.current_value_usd,
        "unrealized_pnl_usd": pos.unrealized_pnl_usd,
        "unrealized_pnl_pct": round(pos.unrealized_pnl_pct, 2),
        "opened_at": pos.opened_at.isoformat() if pos.opened_at else None,
    }


def _trade_to_dict(t: PaperTrade) -> dict:
    return {
        "id": str(t.id),
        "asset_uid": t.asset_uid,
        "symbol": t.symbol,
        "chain": t.chain,
        "side": t.side,
        "status": t.status,
        "requested_notional_usd": t.requested_notional_usd,
        "filled_notional_usd": t.filled_notional_usd,
        "arrival_price_usd": t.arrival_price_usd,
        "executed_price_usd": t.executed_price_usd,
        "impact_bps": t.impact_bps,
        "total_cost_usd": t.total_cost_usd,
        "failure_probability": t.failure_probability,
        "trigger_type": t.trigger_type,
        "reject_reason": t.reject_reason,
        "executed_at": t.executed_at.isoformat() if t.executed_at else None,
    }


# ---------------------------------------------------------------------------
# Portfolio endpoints
# ---------------------------------------------------------------------------


class PortfolioListView(APIView):
    """GET: list portfolios. POST: create portfolio."""

    def get(self, request):
        portfolios = PaperPortfolio.objects.all()
        return Response([_portfolio_to_dict(p) for p in portfolios])

    def post(self, request):
        ser = PortfolioCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        p = PaperPortfolio.objects.create(
            name=d["name"],
            execution_mode=d.get("execution_mode", "base"),
            initial_cash_usd=d.get("initial_cash_usd", 10_000),
            cash_usd=d.get("initial_cash_usd", 10_000),
            total_equity_usd=d.get("initial_cash_usd", 10_000),
            high_water_mark_usd=d.get("initial_cash_usd", 10_000),
            max_positions=d.get("max_positions", 10),
            base_risk_pct=d.get("base_risk_pct", 0.01),
            hard_abs_cap_usd=d.get("hard_abs_cap_usd", 500.0),
            max_holding_hours=d.get("max_holding_hours", 168),
            stop_loss_pct=d.get("stop_loss_pct", 0.20),
        )
        return Response(_portfolio_to_dict(p), status=status.HTTP_201_CREATED)


class PortfolioDetailView(APIView):
    """GET: portfolio detail. PATCH: update status/name."""

    def get(self, request, slug):
        try:
            p = PaperPortfolio.objects.get(slug=slug)
        except PaperPortfolio.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        data = _portfolio_to_dict(p)
        data["positions"] = [
            _position_to_dict(pos)
            for pos in p.positions.filter(status="open")
        ]
        return Response(data)

    def patch(self, request, slug):
        try:
            p = PaperPortfolio.objects.get(slug=slug)
        except PaperPortfolio.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        ser = PortfolioUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if "status" in ser.validated_data:
            p.status = ser.validated_data["status"]
        if "name" in ser.validated_data:
            p.name = ser.validated_data["name"]
        p.save()
        return Response(_portfolio_to_dict(p))


# ---------------------------------------------------------------------------
# Trade endpoints
# ---------------------------------------------------------------------------


class TradeListView(APIView):
    """GET: list trades for a portfolio."""

    def get(self, request, slug):
        try:
            p = PaperPortfolio.objects.get(slug=slug)
        except PaperPortfolio.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        limit = min(int(request.query_params.get("limit", 50)), 200)
        trades = p.trades.all()[:limit]
        return Response([_trade_to_dict(t) for t in trades])


class TradeDetailView(APIView):
    """GET: single trade detail."""

    def get(self, request, slug, trade_id):
        try:
            trade = PaperTrade.objects.get(
                id=trade_id, portfolio__slug=slug
            )
        except PaperTrade.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        data = _trade_to_dict(trade)
        data["liquidity_snapshot"] = trade.liquidity_snapshot
        data["signal_context"] = trade.signal_context
        return Response(data)


# ---------------------------------------------------------------------------
# Position endpoints
# ---------------------------------------------------------------------------


class PositionListView(APIView):
    """GET: list open positions for a portfolio."""

    def get(self, request, slug):
        try:
            p = PaperPortfolio.objects.get(slug=slug)
        except PaperPortfolio.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        positions = p.positions.filter(status="open")
        return Response([_position_to_dict(pos) for pos in positions])


# ---------------------------------------------------------------------------
# Equity curve
# ---------------------------------------------------------------------------


class EquityCurveView(APIView):
    """GET: equity snapshots for charting."""

    def get(self, request, slug):
        try:
            p = PaperPortfolio.objects.get(slug=slug)
        except PaperPortfolio.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        limit = min(int(request.query_params.get("limit", 500)), 2000)
        snaps = p.equity_snapshots.all()[:limit]
        return Response([
            {
                "timestamp": s.timestamp.isoformat(),
                "total_equity_usd": s.total_equity_usd,
                "cash_usd": s.cash_usd,
                "positions_value_usd": s.positions_value_usd,
                "drawdown_pct": s.drawdown_pct,
                "open_positions": s.open_positions,
            }
            for s in snaps
        ])


# ---------------------------------------------------------------------------
# Scorecards — aggregate metrics by trigger type
# ---------------------------------------------------------------------------


class ScorecardView(APIView):
    """GET: performance metrics grouped by trigger_type."""

    def get(self, request, slug):
        try:
            p = PaperPortfolio.objects.get(slug=slug)
        except PaperPortfolio.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        filled = p.trades.filter(status="filled")
        groups = (
            filled
            .values("trigger_type")
            .annotate(
                trade_count=Count("id"),
                total_notional=Sum("filled_notional_usd"),
                avg_impact_bps=Avg("impact_bps"),
                avg_failure_prob=Avg("failure_probability"),
            )
            .order_by("-trade_count")
        )
        return Response(list(groups))


# ---------------------------------------------------------------------------
# Regime endpoints
# ---------------------------------------------------------------------------


def _regime_snapshot_to_dict(snap: RegimeSnapshot) -> dict:
    return {
        "id": str(snap.id),
        "regime": snap.regime,
        "confidence": round(snap.confidence, 4),
        "scores": snap.scores,
        "aggregate_metrics": snap.aggregate_metrics,
        "token_count": snap.token_count,
        "detected_at": snap.detected_at.isoformat(),
    }


class RegimeCurrentView(APIView):
    """GET: current (latest) regime snapshot."""

    def get(self, request):
        snap = RegimeSnapshot.objects.first()  # ordered by -detected_at
        if snap is None:
            return Response({
                "regime": "low_activity",
                "confidence": 0.0,
                "scores": {},
                "aggregate_metrics": {},
                "token_count": 0,
                "detected_at": None,
            })
        return Response(_regime_snapshot_to_dict(snap))


class RegimeHistoryView(APIView):
    """GET: regime history (last N snapshots)."""

    def get(self, request):
        limit = min(int(request.query_params.get("limit", 48)), 200)
        snaps = RegimeSnapshot.objects.all()[:limit]
        return Response([_regime_snapshot_to_dict(s) for s in snaps])
