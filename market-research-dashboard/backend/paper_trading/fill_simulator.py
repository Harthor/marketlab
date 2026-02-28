"""Liquidity-aware fill simulator for paper trading.

Simulates realistic trade execution with price impact, fees, taxes,
gas costs, and failure probability based on token bucket characteristics.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Bucket parameters — impact model: alpha * (notional / liquidity) ^ beta
# ---------------------------------------------------------------------------

BUCKET_PARAMS = {
    "meme_bluechip": {
        "alpha": 0.40,
        "beta": 0.90,
        "base_failure_prob": 0.02,
        "liquidity_cap_pct": 0.10,  # max 10% of pool liquidity
    },
    "meme_liquid": {
        "alpha": 0.60,
        "beta": 1.00,
        "base_failure_prob": 0.05,
        "liquidity_cap_pct": 0.08,
    },
    "microcap_listed": {
        "alpha": 0.90,
        "beta": 1.05,
        "base_failure_prob": 0.10,
        "liquidity_cap_pct": 0.05,
    },
    "dex_new_launch": {
        "alpha": 1.50,
        "beta": 1.15,
        "base_failure_prob": 0.20,
        "liquidity_cap_pct": 0.03,
    },
}

# Route hop multiplier (each additional hop adds impact)
ROUTE_HOP_MULTIPLIER = {1: 1.0, 2: 1.15, 3: 1.35}


def simulate_fill(
    *,
    side: str,
    token_bucket: str,
    requested_notional_usd: float,
    arrival_mid_price_usd: float,
    pool_fee_bps: int,
    buy_tax_bps: int = 0,
    sell_tax_bps: int = 0,
    chain_fee_usd: float = 0.0,
    priority_fee_usd: float = 0.0,
    exit_liquidity_usd: float | None = None,
    reserve_quote_usd: float | None = None,
    reserve_token_units: float | None = None,
    route_hops: int = 1,
    security_flags: dict | None = None,
    stressed: bool = False,
) -> dict:
    """Simulate a realistic fill for a paper trade.

    Returns a dict with: status, arrival_price, executed_price, filled_qty,
    impact_bps, fees, costs, failure_probability, reject_reason.
    """
    flags = security_flags or {}
    params = BUCKET_PARAMS.get(token_bucket, BUCKET_PARAMS["microcap_listed"])

    # --- Hard rejects ---
    if flags.get("honeypot"):
        return _reject("Honeypot flag detected")

    if exit_liquidity_usd is not None and exit_liquidity_usd <= 0:
        return _reject("Zero exit liquidity")

    if exit_liquidity_usd is not None:
        liq_cap = exit_liquidity_usd * params["liquidity_cap_pct"]
        if requested_notional_usd > liq_cap:
            return _reject(
                f"Size ${requested_notional_usd:.0f} exceeds liquidity cap "
                f"${liq_cap:.0f} ({params['liquidity_cap_pct']:.0%} of ${exit_liquidity_usd:.0f})"
            )

    if arrival_mid_price_usd <= 0:
        return _reject("Invalid arrival price")

    # --- Compute venue fee ---
    venue_fee_rate = pool_fee_bps / 10_000
    venue_fee_usd = requested_notional_usd * venue_fee_rate

    # --- Compute tax ---
    tax_bps = buy_tax_bps if side == "buy" else sell_tax_bps
    tax_usd = requested_notional_usd * tax_bps / 10_000

    # --- Compute gas ---
    gas_usd = chain_fee_usd + priority_fee_usd
    if stressed:
        gas_usd *= 1.5

    # --- Price impact ---
    route_mult = ROUTE_HOP_MULTIPLIER.get(route_hops, 1.35)

    if (
        reserve_quote_usd is not None
        and reserve_token_units is not None
        and reserve_quote_usd > 0
        and reserve_token_units > 0
    ):
        # CPMM formula
        impact_bps = _cpmm_impact(
            notional=requested_notional_usd,
            reserve_quote=reserve_quote_usd,
            reserve_token=reserve_token_units,
            fee_rate=venue_fee_rate,
            mid_price=arrival_mid_price_usd,
            route_mult=route_mult,
        )
    elif exit_liquidity_usd and exit_liquidity_usd > 0:
        # Proxy model by bucket
        ratio = requested_notional_usd / exit_liquidity_usd
        impact_bps = params["alpha"] * (ratio ** params["beta"]) * 10_000 * route_mult
    else:
        # Fallback: generous estimate
        impact_bps = params["alpha"] * 0.01 * 10_000 * route_mult

    if stressed:
        impact_bps *= 1.5

    # --- Executed price ---
    impact_frac = impact_bps / 10_000
    if side == "buy":
        executed_price = arrival_mid_price_usd * (1 + impact_frac)
    else:
        executed_price = arrival_mid_price_usd * (1 - impact_frac)

    # --- Filled quantity ---
    net_notional = requested_notional_usd - venue_fee_usd - tax_usd - gas_usd
    if net_notional <= 0:
        return _reject("Costs exceed notional")

    filled_qty = net_notional / executed_price if executed_price > 0 else 0

    # --- Failure probability ---
    failure_prob = params["base_failure_prob"]
    if flags.get("mint_authority_enabled"):
        failure_prob += 0.05
    if flags.get("freeze_authority_enabled"):
        failure_prob += 0.05
    if route_hops > 1:
        failure_prob += 0.02 * (route_hops - 1)
    if stressed:
        failure_prob = min(failure_prob * 1.5, 0.95)
    failure_prob = min(failure_prob, 0.95)

    # --- Total cost ---
    slippage_bps = impact_bps
    total_cost_usd = venue_fee_usd + tax_usd + gas_usd + (requested_notional_usd * impact_frac)

    return {
        "status": "filled",
        "arrival_price_usd": arrival_mid_price_usd,
        "executed_price_usd": round(executed_price, 10),
        "filled_qty": round(filled_qty, 10),
        "filled_notional_usd": round(net_notional, 4),
        "impact_bps": round(impact_bps, 2),
        "slippage_bps": round(slippage_bps, 2),
        "venue_fee_usd": round(venue_fee_usd, 4),
        "tax_usd": round(tax_usd, 4),
        "gas_usd": round(gas_usd, 4),
        "total_cost_usd": round(total_cost_usd, 4),
        "failure_probability": round(failure_prob, 4),
        "reject_reason": "",
    }


def _reject(reason: str) -> dict:
    return {
        "status": "rejected",
        "arrival_price_usd": 0,
        "executed_price_usd": 0,
        "filled_qty": 0,
        "filled_notional_usd": 0,
        "impact_bps": 0,
        "slippage_bps": 0,
        "venue_fee_usd": 0,
        "tax_usd": 0,
        "gas_usd": 0,
        "total_cost_usd": 0,
        "failure_probability": 1.0,
        "reject_reason": reason,
    }


def _cpmm_impact(
    *,
    notional: float,
    reserve_quote: float,
    reserve_token: float,
    fee_rate: float,
    mid_price: float,
    route_mult: float,
) -> float:
    """Compute price impact using constant-product market maker formula."""
    q_eff = notional * (1 - fee_rate)
    t_out = reserve_token - (reserve_quote * reserve_token) / (reserve_quote + q_eff)
    if t_out <= 0:
        return 10_000.0  # 100% impact — extreme case

    exec_price = notional / t_out
    if mid_price <= 0:
        return 10_000.0

    impact_bps = (exec_price / mid_price - 1) * 10_000 * route_mult
    return max(0, impact_bps)
