"""Hard filters and anti-rug checks for the degen universe."""
from __future__ import annotations

from typing import Any

from .models import AssetCandidate


def _get_cat_config(policy: dict[str, Any], category: str) -> dict[str, Any]:
    return policy.get("categories", {}).get(category, {})


def passes_hard_filters(
    asset: AssetCandidate,
    category: str,
    policy: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Check if an asset passes hard inclusion filters for a category.

    Returns (passes, list_of_failure_reasons).
    """
    cat = _get_cat_config(policy, category)
    if not cat:
        return False, [f"unknown_category:{category}"]

    failures: list[str] = []

    # Volume checks
    min_daily_vol = cat.get("min_daily_volume_usd")
    if min_daily_vol and (asset.volume_24h_usd or 0) < min_daily_vol:
        failures.append(f"volume_24h_below_{min_daily_vol}")

    min_hourly_vol = cat.get("min_hourly_volume_usd")
    if min_hourly_vol and (asset.volume_1h_usd or 0) < min_hourly_vol:
        failures.append(f"volume_1h_below_{min_hourly_vol}")

    # Liquidity check
    min_liq = cat.get("min_liquidity_usd")
    if min_liq and (asset.liquidity_usd or 0) < min_liq:
        failures.append(f"liquidity_below_{min_liq}")

    # Market cap checks
    min_mcap = cat.get("min_market_cap_usd")
    if min_mcap and asset.market_cap_usd is not None and asset.market_cap_usd < min_mcap:
        failures.append(f"mcap_below_{min_mcap}")

    max_mcap = cat.get("max_market_cap_usd")
    if max_mcap and asset.market_cap_usd is not None and asset.market_cap_usd > max_mcap:
        failures.append(f"mcap_above_{max_mcap}")

    # Age checks
    min_age_days = cat.get("min_age_days")
    if min_age_days and (asset.age_hours or 0) < min_age_days * 24:
        failures.append(f"age_below_{min_age_days}d")

    min_age_hours = cat.get("min_age_hours")
    if min_age_hours and (asset.age_hours or 0) < min_age_hours:
        failures.append(f"age_below_{min_age_hours}h")

    max_age_days = cat.get("max_age_days")
    if max_age_days and asset.age_hours is not None and asset.age_hours > max_age_days * 24:
        failures.append(f"age_above_{max_age_days}d")

    # Holder concentration
    max_top10 = cat.get("max_top10_holders_pct_ex_lp")
    if (
        max_top10
        and asset.top10_holders_pct_ex_lp is not None
        and asset.top10_holders_pct_ex_lp > max_top10
    ):
        failures.append(f"top10_holders_above_{max_top10}")

    max_single = cat.get("max_single_holder_pct_ex_lp")
    if (
        max_single
        and asset.single_max_holder_pct_ex_lp is not None
        and asset.single_max_holder_pct_ex_lp > max_single
    ):
        failures.append(f"single_holder_above_{max_single}")

    return len(failures) == 0, failures


def passes_anti_rug(
    asset: AssetCandidate,
    policy: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Check anti-rug rules based on chain type."""
    chain = asset.chain
    anti_rug = policy.get("anti_rug", {})

    # Determine chain-type config
    rules = anti_rug.get("solana", {}) if chain == "solana" else anti_rug.get("evm", {})

    failures: list[str] = []

    # Solana-specific
    if chain == "solana":
        if (
            rules.get("mint_authority_must_be_disabled")
            and asset.mint_authority_disabled is False
        ):
            failures.append("mint_authority_enabled")
        if (
            rules.get("freeze_authority_must_be_disabled")
            and asset.freeze_authority_disabled is False
        ):
            failures.append("freeze_authority_enabled")
        max_creator = rules.get("creator_wallet_pct_max")
        if (
            max_creator
            and asset.creator_wallet_pct is not None
            and asset.creator_wallet_pct > max_creator
        ):
            failures.append(f"creator_wallet_{asset.creator_wallet_pct}%")
        min_lp = rules.get("lp_liquidity_usd_min")
        if min_lp and (asset.liquidity_usd or 0) < min_lp:
            failures.append(f"lp_liquidity_below_{min_lp}")

    # EVM-specific
    else:
        if (
            rules.get("contract_verified_required")
            and asset.contract_verified is False
        ):
            failures.append("contract_not_verified")

    # Common: check security flags for known bad patterns
    severe = {"honeypot", "mint_enabled", "freeze_enabled", "blacklistable"}
    for flag in asset.security_flags:
        if flag in severe:
            failures.append(f"security_flag:{flag}")

    return len(failures) == 0, failures


def apply_exclusion_rules(asset: AssetCandidate) -> tuple[bool, list[str]]:
    """Apply hard exclusion rules that override everything else."""
    failures: list[str] = []

    # Zero or near-zero liquidity
    if (asset.liquidity_usd or 0) < 1000:
        failures.append("near_zero_liquidity")

    # Honeypot flag
    if "honeypot" in asset.security_flags:
        failures.append("honeypot_detected")

    return len(failures) == 0, failures
