"""Paper Trading models — portfolio, position, trade, equity snapshot, regime."""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone
from django.utils.text import slugify

# ---------------------------------------------------------------------------
# PaperPortfolio
# ---------------------------------------------------------------------------


class PaperPortfolio(models.Model):
    """Virtual portfolio for paper-trading degen tokens."""

    class ExecutionMode(models.TextChoices):
        BASE = "base", "Base"
        STRESSED = "stressed", "Stressed"
        DUAL = "dual", "Dual (base + stressed)"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    execution_mode = models.CharField(
        max_length=20,
        choices=ExecutionMode.choices,
        default=ExecutionMode.BASE,
    )

    # Cash & equity
    initial_cash_usd = models.FloatField(default=10_000.0)
    cash_usd = models.FloatField(default=10_000.0)
    total_equity_usd = models.FloatField(default=10_000.0)
    high_water_mark_usd = models.FloatField(default=10_000.0)

    # Risk config
    max_positions = models.IntegerField(default=10)
    max_position_pct = models.FloatField(
        default=0.05,
        help_text="Max single position as fraction of equity",
    )
    base_risk_pct = models.FloatField(
        default=0.01,
        help_text="Base risk per trade as fraction of equity",
    )
    hard_abs_cap_usd = models.FloatField(
        default=500.0,
        help_text="Absolute max USD per trade",
    )
    max_holding_hours = models.IntegerField(
        default=168,
        help_text="Time stop: max hours to hold",
    )
    stop_loss_pct = models.FloatField(
        default=0.20,
        help_text="Price stop: max loss from entry",
    )
    take_profit_ladder = models.JSONField(
        default=list,
        blank=True,
        help_text='Take-profit levels, e.g. [{"pct": 0.50, "sell_fraction": 0.25}]',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) or str(self.id)[:8]
        super().save(*args, **kwargs)

    @property
    def pnl_usd(self) -> float:
        return self.total_equity_usd - self.initial_cash_usd

    @property
    def pnl_pct(self) -> float:
        if self.initial_cash_usd == 0:
            return 0.0
        return (self.total_equity_usd / self.initial_cash_usd - 1) * 100

    @property
    def drawdown_pct(self) -> float:
        if self.high_water_mark_usd == 0:
            return 0.0
        return (1 - self.total_equity_usd / self.high_water_mark_usd) * 100

    @property
    def open_position_count(self) -> int:
        return self.positions.filter(status=PaperPosition.Status.OPEN).count()


# ---------------------------------------------------------------------------
# PaperPosition
# ---------------------------------------------------------------------------


class PaperPosition(models.Model):
    """An open or closed position within a paper portfolio."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        WRITTEN_OFF = "written_off", "Written Off"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey(
        PaperPortfolio,
        on_delete=models.CASCADE,
        related_name="positions",
    )
    asset_uid = models.CharField(max_length=200, db_index=True)
    symbol = models.CharField(max_length=50)
    chain = models.CharField(max_length=30)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )

    # Entry
    entry_price_usd = models.FloatField()
    avg_entry_price_usd = models.FloatField()
    quantity = models.FloatField()
    cost_basis_usd = models.FloatField()

    # Current mark
    current_price_usd = models.FloatField(default=0.0)
    current_value_usd = models.FloatField(default=0.0)
    unrealized_pnl_usd = models.FloatField(default=0.0)
    unrealized_pnl_pct = models.FloatField(default=0.0)

    # Exit (filled on close)
    exit_price_usd = models.FloatField(null=True, blank=True)
    realized_pnl_usd = models.FloatField(default=0.0)

    # Metadata
    category = models.CharField(max_length=50, blank=True, default="")
    token_address = models.CharField(max_length=200, blank=True, default="")
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        indexes = [
            models.Index(fields=["portfolio", "status"]),
            models.Index(fields=["asset_uid", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} {self.quantity:.4f} @ {self.avg_entry_price_usd:.6f}"

    def mark_to_market(self, price: float) -> None:
        """Update position with current market price."""
        self.current_price_usd = price
        self.current_value_usd = self.quantity * price
        self.unrealized_pnl_usd = self.current_value_usd - self.cost_basis_usd
        if self.cost_basis_usd > 0:
            self.unrealized_pnl_pct = (self.unrealized_pnl_usd / self.cost_basis_usd) * 100
        self.save()

    def write_off(self) -> None:
        """Mark position as rugged/dead — zero out value."""
        self.status = self.Status.WRITTEN_OFF
        self.current_price_usd = 0.0
        self.current_value_usd = 0.0
        self.unrealized_pnl_usd = -self.cost_basis_usd
        self.unrealized_pnl_pct = -100.0
        self.realized_pnl_usd = -self.cost_basis_usd
        self.exit_price_usd = 0.0
        self.closed_at = timezone.now()
        self.save()

    def close(self, exit_price: float, quantity_sold: float | None = None) -> None:
        """Close the position (fully or partially)."""
        qty = quantity_sold or self.quantity
        self.exit_price_usd = exit_price
        self.realized_pnl_usd = (exit_price - self.avg_entry_price_usd) * qty
        if qty >= self.quantity:
            self.status = self.Status.CLOSED
            self.quantity = 0
            self.closed_at = timezone.now()
        else:
            self.quantity -= qty
            self.cost_basis_usd = self.quantity * self.avg_entry_price_usd
        self.save()


# ---------------------------------------------------------------------------
# PaperTrade
# ---------------------------------------------------------------------------


class PaperTrade(models.Model):
    """Immutable record of a simulated trade execution."""

    class Side(models.TextChoices):
        BUY = "buy", "Buy"
        SELL = "sell", "Sell"

    class TradeStatus(models.TextChoices):
        FILLED = "filled", "Filled"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey(
        PaperPortfolio,
        on_delete=models.CASCADE,
        related_name="trades",
    )
    position = models.ForeignKey(
        PaperPosition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trades",
    )

    # Asset
    asset_uid = models.CharField(max_length=200, db_index=True)
    symbol = models.CharField(max_length=50)
    chain = models.CharField(max_length=30)
    token_bucket = models.CharField(max_length=50, blank=True, default="")

    # Trade details
    side = models.CharField(max_length=10, choices=Side.choices)
    status = models.CharField(
        max_length=20,
        choices=TradeStatus.choices,
        default=TradeStatus.FILLED,
    )
    requested_notional_usd = models.FloatField()
    filled_notional_usd = models.FloatField(default=0.0)
    filled_quantity = models.FloatField(default=0.0)

    # Prices
    arrival_price_usd = models.FloatField()
    executed_price_usd = models.FloatField(default=0.0)

    # Costs breakdown
    slippage_bps = models.FloatField(default=0.0)
    impact_bps = models.FloatField(default=0.0)
    venue_fee_usd = models.FloatField(default=0.0)
    tax_usd = models.FloatField(default=0.0)
    gas_usd = models.FloatField(default=0.0)
    total_cost_usd = models.FloatField(default=0.0)
    failure_probability = models.FloatField(default=0.0)

    # Evidence
    liquidity_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Pool liquidity data at fill time",
    )
    signal_context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Signal that triggered this trade",
    )

    # Stressed mode fill (if execution_mode=dual)
    stressed_executed_price_usd = models.FloatField(null=True, blank=True)
    stressed_impact_bps = models.FloatField(null=True, blank=True)
    stressed_total_cost_usd = models.FloatField(null=True, blank=True)
    stressed_failure_probability = models.FloatField(null=True, blank=True)

    # Trigger
    trigger_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_index=True,
        help_text="What triggered this trade (e.g. smart_money, score_jump)",
    )
    reject_reason = models.CharField(max_length=300, blank=True, default="")

    executed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-executed_at"]
        indexes = [
            models.Index(fields=["portfolio", "-executed_at"]),
            models.Index(fields=["trigger_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.side} {self.symbol} ${self.filled_notional_usd:.2f} [{self.status}]"


# ---------------------------------------------------------------------------
# PaperEquitySnapshot
# ---------------------------------------------------------------------------


class PaperEquitySnapshot(models.Model):
    """Time-series point for portfolio equity tracking."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey(
        PaperPortfolio,
        on_delete=models.CASCADE,
        related_name="equity_snapshots",
    )
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    cash_usd = models.FloatField()
    positions_value_usd = models.FloatField()
    total_equity_usd = models.FloatField()
    drawdown_pct = models.FloatField(default=0.0)
    open_positions = models.IntegerField(default=0)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["portfolio", "-timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.portfolio.name} ${self.total_equity_usd:.2f} @ {self.timestamp:%H:%M}"


# ---------------------------------------------------------------------------
# RegimeSnapshot
# ---------------------------------------------------------------------------


class RegimeSnapshot(models.Model):
    """Point-in-time snapshot of the detected market regime."""

    class Regime(models.TextChoices):
        MANIA = "mania", "Mania"
        ROTATION = "rotation", "Rotation"
        FLIGHT_TO_QUALITY = "flight_to_quality", "Flight to Quality"
        LOW_ACTIVITY = "low_activity", "Low Activity"
        CAPITULATION = "capitulation", "Capitulation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    regime = models.CharField(
        max_length=30,
        choices=Regime.choices,
        default=Regime.LOW_ACTIVITY,
        db_index=True,
    )
    confidence = models.FloatField(default=0.0)
    scores = models.JSONField(
        default=dict,
        help_text="Score breakdown per regime",
    )
    aggregate_metrics = models.JSONField(
        default=dict,
        help_text="Aggregate watchlist metrics used for detection",
    )
    token_count = models.IntegerField(default=0)
    detected_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-detected_at"]

    def __str__(self) -> str:
        return f"{self.regime} ({self.confidence:.0%}) @ {self.detected_at:%H:%M}"
