"""Position sizing for paper trading.

Computes optimal position size respecting equity risk, liquidity caps,
and volume caps per token bucket.
"""
from __future__ import annotations

# Max fraction of exit liquidity to take
LIQUIDITY_TAKE_PCT = {
    "meme_bluechip": 0.05,
    "meme_liquid": 0.03,
    "microcap_listed": 0.02,
    "dex_new_launch": 0.01,
}

# Max fraction of 24h volume to take
VOLUME_TAKE_PCT = {
    "meme_bluechip": 0.02,
    "meme_liquid": 0.01,
    "microcap_listed": 0.005,
    "dex_new_launch": 0.003,
}


def compute_position_size(
    *,
    equity_usd: float,
    base_risk_pct: float,
    confidence_multiplier: float,
    exit_liquidity_usd: float,
    volume_24h_usd: float,
    token_bucket: str,
    hard_abs_cap_usd: float = 500.0,
) -> float:
    """Compute the notional USD for a new position.

    Applies four caps:
    1. Equity risk: equity * base_risk_pct * confidence_multiplier
    2. Liquidity cap: exit_liquidity * LIQUIDITY_TAKE_PCT[bucket]
    3. Volume cap: volume_24h * VOLUME_TAKE_PCT[bucket]
    4. Hard absolute cap
    """
    raw = equity_usd * base_risk_pct * confidence_multiplier

    liq_take = LIQUIDITY_TAKE_PCT.get(token_bucket, 0.01)
    liq_cap = exit_liquidity_usd * liq_take

    vol_take = VOLUME_TAKE_PCT.get(token_bucket, 0.003)
    vol_cap = volume_24h_usd * vol_take

    return max(0.0, min(raw, liq_cap, vol_cap, hard_abs_cap_usd))
