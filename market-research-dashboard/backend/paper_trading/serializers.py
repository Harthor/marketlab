"""DRF serializers for paper trading API."""
from __future__ import annotations

from rest_framework import serializers


class PortfolioCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    execution_mode = serializers.ChoiceField(
        choices=["base", "stressed", "dual"],
        default="base",
    )
    initial_cash_usd = serializers.FloatField(default=10_000.0)
    max_positions = serializers.IntegerField(default=10)
    base_risk_pct = serializers.FloatField(default=0.01)
    hard_abs_cap_usd = serializers.FloatField(default=500.0)
    max_holding_hours = serializers.IntegerField(default=168)
    stop_loss_pct = serializers.FloatField(default=0.20)


class PortfolioUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["active", "paused", "archived"],
        required=False,
    )
    name = serializers.CharField(max_length=200, required=False)
