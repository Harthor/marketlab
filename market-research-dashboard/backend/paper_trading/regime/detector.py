"""Regime detector — 5 market regimes scored from aggregate watchlist metrics.

Regimes:
    mania             — broad euphoria, many tokens pumping
    rotation          — mixed: some sectors up, others down
    flight_to_quality — money moving to BTC/ETH/stables
    low_activity      — low volume and engagement across the board
    capitulation      — heavy selling, rising risk scores, dropping liquidity
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from paper_trading.playbooks.helpers import clip01, inv_ramp, ramp

logger = logging.getLogger(__name__)

REGIMES = (
    "mania",
    "rotation",
    "flight_to_quality",
    "low_activity",
    "capitulation",
)


@dataclass
class RegimeScore:
    """Score breakdown for a single regime."""

    name: str
    score: float = 0.0
    components: dict[str, float] = field(default_factory=dict)


@dataclass
class RegimeResult:
    """Full regime detection result."""

    current_regime: str = "low_activity"
    confidence: float = 0.0
    scores: dict[str, RegimeScore] = field(default_factory=dict)
    aggregate_metrics: dict[str, float] = field(default_factory=dict)


class RegimeDetector:
    """Detect current market regime from aggregate watchlist metrics."""

    def detect(self, tokens: list[dict[str, Any]]) -> RegimeResult:
        """Classify the current market regime.

        Args:
            tokens: List of token dicts from the degen watchlist.

        Returns:
            RegimeResult with scored regimes and the winner.
        """
        metrics = self._compute_aggregate_metrics(tokens)
        scores = {}

        for regime in REGIMES:
            method = getattr(self, f"_score_{regime}", None)
            if method:
                scores[regime] = method(metrics)

        # Winner = highest score
        if scores:
            best = max(scores.values(), key=lambda s: s.score)
            current = best.name
            confidence = best.score
        else:
            current = "low_activity"
            confidence = 0.0

        return RegimeResult(
            current_regime=current,
            confidence=confidence,
            scores=scores,
            aggregate_metrics=metrics,
        )

    def _compute_aggregate_metrics(
        self,
        tokens: list[dict[str, Any]],
    ) -> dict[str, float]:
        """Compute aggregate metrics from watchlist tokens."""
        if not tokens:
            return {
                "count": 0,
                "avg_score": 0,
                "avg_risk": 50,
                "avg_volume_24h": 0,
                "avg_liquidity": 0,
                "pct_positive_24h": 0,
                "pct_high_risk": 0,
                "avg_age_hours": 0,
                "total_volume_24h": 0,
                "avg_price_change_24h": 0,
            }

        n = len(tokens)
        scores = [t.get("universe_score", 0) or 0 for t in tokens]
        risks = [t.get("risk_score", 0) or 0 for t in tokens]
        volumes = [t.get("volume_24h_usd", 0) or 0 for t in tokens]
        liquidities = [t.get("liquidity_usd", 0) or 0 for t in tokens]
        price_changes = [t.get("price_change_24h_pct", 0) or 0 for t in tokens]
        ages = [t.get("age_hours", 0) or 0 for t in tokens]

        positive_count = sum(1 for p in price_changes if p > 0)
        high_risk_count = sum(1 for r in risks if r >= 60)

        return {
            "count": n,
            "avg_score": sum(scores) / n,
            "avg_risk": sum(risks) / n,
            "avg_volume_24h": sum(volumes) / n,
            "avg_liquidity": sum(liquidities) / n,
            "pct_positive_24h": (positive_count / n) * 100,
            "pct_high_risk": (high_risk_count / n) * 100,
            "avg_age_hours": sum(ages) / n,
            "total_volume_24h": sum(volumes),
            "avg_price_change_24h": sum(price_changes) / n,
        }

    # --- Per-regime scorers ---

    def _score_mania(self, m: dict[str, float]) -> RegimeScore:
        """Mania: high scores, positive prices, high volume, low risk."""
        components = {
            "avg_score": ramp(m["avg_score"], 40, 75),
            "pct_positive": ramp(m["pct_positive_24h"], 50, 85),
            "avg_volume": ramp(m["avg_volume_24h"], 50_000, 500_000),
            "low_risk": inv_ramp(m["avg_risk"], 20, 50),
            "price_momentum": ramp(m["avg_price_change_24h"], 5, 30),
        }
        weights = {"avg_score": 2.5, "pct_positive": 2.0, "avg_volume": 1.5,
                    "low_risk": 1.5, "price_momentum": 2.5}
        total_w = sum(weights.values())
        score = sum(components[k] * weights[k] for k in components) / total_w
        return RegimeScore(name="mania", score=clip01(score), components=components)

    def _score_rotation(self, m: dict[str, float]) -> RegimeScore:
        """Rotation: mixed — some up, some down, moderate volume."""
        # Rotation is strongest when ~50% are positive (not extreme)
        balance = 1.0 - abs(m["pct_positive_24h"] - 50) / 50
        components = {
            "balance": clip01(balance),
            "moderate_vol": ramp(m["avg_volume_24h"], 20_000, 200_000),
            "moderate_score": ramp(m["avg_score"], 30, 55),
            "moderate_risk": 1.0 - abs(ramp(m["avg_risk"], 0, 100) - 0.5) * 2,
        }
        weights = {"balance": 3.0, "moderate_vol": 1.5, "moderate_score": 1.5,
                    "moderate_risk": 2.0}
        total_w = sum(weights.values())
        score = sum(components[k] * weights[k] for k in components) / total_w
        return RegimeScore(name="rotation", score=clip01(score), components=components)

    def _score_flight_to_quality(self, m: dict[str, float]) -> RegimeScore:
        """Flight to quality: moderate risk, selective selling (not total crash)."""
        # FtQ is about *moderate* drops — extreme drops are capitulation.
        # Penalize when avg_risk is extreme (>75) or drops exceed -30%.
        not_extreme_risk = inv_ramp(m["avg_risk"], 55, 80)
        not_extreme_drop = ramp(m["avg_price_change_24h"], -35, -5)
        components = {
            "rising_risk": ramp(m["avg_risk"], 35, 65),
            "negative_prices": inv_ramp(m["pct_positive_24h"], 20, 50),
            "moderate_drop": not_extreme_drop,
            "not_extreme_risk": not_extreme_risk,
            "moderate_vol": ramp(m["avg_volume_24h"], 30_000, 200_000),
        }
        weights = {"rising_risk": 2.0, "negative_prices": 2.0,
                    "moderate_drop": 2.5, "not_extreme_risk": 2.0,
                    "moderate_vol": 1.0}
        total_w = sum(weights.values())
        score = sum(components[k] * weights[k] for k in components) / total_w
        return RegimeScore(
            name="flight_to_quality", score=clip01(score), components=components,
        )

    def _score_low_activity(self, m: dict[str, float]) -> RegimeScore:
        """Low activity: low volume, low scores, stagnant prices."""
        components = {
            "low_volume": inv_ramp(m["avg_volume_24h"], 10_000, 100_000),
            "low_scores": inv_ramp(m["avg_score"], 20, 50),
            "flat_prices": 1.0 - clip01(abs(m["avg_price_change_24h"]) / 10),
            "few_tokens": inv_ramp(m["count"], 5, 30),
        }
        weights = {"low_volume": 3.0, "low_scores": 2.0,
                    "flat_prices": 2.0, "few_tokens": 1.0}
        total_w = sum(weights.values())
        score = sum(components[k] * weights[k] for k in components) / total_w
        return RegimeScore(
            name="low_activity", score=clip01(score), components=components,
        )

    def _score_capitulation(self, m: dict[str, float]) -> RegimeScore:
        """Capitulation: heavy selling, high risk, dropping liquidity."""
        components = {
            "high_risk": ramp(m["avg_risk"], 50, 80),
            "negative_prices": inv_ramp(m["pct_positive_24h"], 10, 40),
            "heavy_drop": inv_ramp(m["avg_price_change_24h"], -40, -10),
            "high_volume": ramp(m["avg_volume_24h"], 50_000, 500_000),
        }
        weights = {"high_risk": 2.5, "negative_prices": 2.5,
                    "heavy_drop": 3.0, "high_volume": 1.0}
        total_w = sum(weights.values())
        score = sum(components[k] * weights[k] for k in components) / total_w
        return RegimeScore(
            name="capitulation", score=clip01(score), components=components,
        )
