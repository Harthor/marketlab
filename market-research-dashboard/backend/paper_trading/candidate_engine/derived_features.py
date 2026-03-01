"""Derive additional features from token state for candidate scoring."""
from __future__ import annotations

from typing import Any

from paper_trading.playbooks.helpers import clip01, inv_ramp, ramp


def compute_liquidity_quality(token: dict[str, Any]) -> float:
    """Score how tradeable this token is based on liquidity and volume.

    Returns float in [0, 1].
    """
    liq = token.get("liquidity_usd", 0) or 0
    vol = token.get("volume_24h_usd", 0) or 0
    liq_score = ramp(liq, 10_000, 500_000)
    vol_score = ramp(vol, 5_000, 300_000)
    return clip01(liq_score * 0.6 + vol_score * 0.4)


def compute_freshness(token: dict[str, Any]) -> float:
    """Score how recent/fresh the token data is.

    Two-tier approach:
    - New launches (< 720h / 30d): full ramp from 1.0 → 0.5
    - Established tokens (>= 720h): gentle decline 0.5 → 0.25 over 1 year
    Ensures bluechip tokens are never zeroed out by age alone.
    Returns float in [0.25, 1].
    """
    age = token.get("age_hours", 0) or 0
    if age < 720:
        # New launches: bonus for freshness, ramps from 1.0 down to 0.5
        return 0.5 + 0.5 * inv_ramp(age, 2, 720)
    # Established tokens: gentle decline from 0.5 to floor of 0.25
    return max(0.25, 0.5 * inv_ramp(age, 720, 87600))


def compute_risk_penalty(token: dict[str, Any]) -> float:
    """Compute a risk penalty based on risk_score and security flags.

    Returns float in [0, 1] where 0 = no penalty, 1 = max penalty.
    """
    risk = token.get("risk_score", 0) or 0
    flags = token.get("security_flags", []) or []
    base_penalty = ramp(risk, 30, 80)
    # Each security flag adds 0.1 penalty
    flag_penalty = min(len(flags) * 0.1, 0.5)
    return clip01(base_penalty + flag_penalty)


def compute_priority_score(
    confidence: float,
    edge_prior: float,
    regime_fit: float,
    token: dict[str, Any],
) -> float:
    """Compute the priority score for ranking candidates.

    Formula:
        priority = confidence × edge_prior × regime_fit
                   × liquidity_quality × freshness × (1 - risk_penalty)
    """
    liq_q = compute_liquidity_quality(token)
    fresh = compute_freshness(token)
    risk_pen = compute_risk_penalty(token)

    return (
        confidence
        * edge_prior
        * regime_fit
        * liq_q
        * fresh
        * (1.0 - risk_pen)
    )
