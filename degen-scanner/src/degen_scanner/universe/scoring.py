"""Universe score computation for degen tokens."""
from __future__ import annotations

import math

from .models import AssetCandidate, AssetEntry


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def normalize_liquidity(liquidity_usd: float | None) -> float:
    """Score 0-100 based on liquidity. $100k=20, $500k=50, $2M=80, $10M+=100."""
    if not liquidity_usd or liquidity_usd <= 0:
        return 0.0
    log_val = math.log10(max(liquidity_usd, 1))
    # log10(100k)=5, log10(10M)=7 → map [5, 7] → [20, 100]
    return _clamp((log_val - 5) * 40 + 20)


def normalize_volume(volume_24h_usd: float | None) -> float:
    """Score 0-100 based on 24h volume. $50k=10, $500k=40, $5M=70, $50M+=100."""
    if not volume_24h_usd or volume_24h_usd <= 0:
        return 0.0
    log_val = math.log10(max(volume_24h_usd, 1))
    # log10(50k)~4.7, log10(50M)~7.7 → map [4.7, 7.7] → [10, 100]
    return _clamp((log_val - 4.7) * 30 + 10)


def normalize_attention(attention_flags: list[str]) -> float:
    """Score 0-100 based on attention signals."""
    if not attention_flags:
        return 0.0
    scores = {
        "dexscreener_boosted": 25,
        "dexscreener_top_boost": 35,
        "community_takeover": 30,
        "birdeye_trending": 30,
        "birdeye_trending_top10": 40,
        "reddit_spike": 20,
        "coingecko_trending": 25,
        "new_listing": 15,
    }
    total = sum(scores.get(f, 10) for f in attention_flags)
    return _clamp(total)


def normalize_quality(
    holder_count: int | None,
    top10_pct: float | None,
    security_flags: list[str],
) -> float:
    """Score 0-100 based on holder quality and security."""
    score = 50.0  # baseline

    # Holder count bonus
    if holder_count:
        if holder_count >= 10000:
            score += 20
        elif holder_count >= 1000:
            score += 10

    # Concentration penalty
    if top10_pct is not None:
        if top10_pct > 50:
            score -= 30
        elif top10_pct > 35:
            score -= 15
        elif top10_pct < 20:
            score += 10

    # Security flag penalties
    severe = {"honeypot", "mint_enabled", "freeze_enabled", "blacklistable"}
    for flag in security_flags:
        if flag in severe:
            score -= 25
        else:
            score -= 10

    return _clamp(score)


def normalize_age(age_hours: float | None) -> float:
    """Score 0-100 based on token age. Very new or very old penalized."""
    if age_hours is None or age_hours <= 0:
        return 0.0
    days = age_hours / 24
    if days < 1:
        return _clamp(days * 30)  # ramp up in first day
    if days < 7:
        return _clamp(30 + days * 5)
    if days < 90:
        return _clamp(60 + (days / 90) * 30)
    if days < 365:
        return 90.0
    # Old tokens slightly penalized (might be dead)
    return 70.0


def normalize_venue(listed_on_cex: bool | None, listed_on_coingecko: bool | None) -> float:
    """Score 0-100 based on listing venues."""
    score = 30.0  # DEX-only baseline
    if listed_on_coingecko:
        score += 30
    if listed_on_cex:
        score += 40
    return _clamp(score)


def compute_universe_score(asset: AssetCandidate | AssetEntry) -> float:
    """Compute the overall universe score (0-100) for an asset."""
    liq = normalize_liquidity(asset.liquidity_usd)
    vol = normalize_volume(asset.volume_24h_usd)
    att = normalize_attention(asset.attention_flags)
    qual = normalize_quality(
        getattr(asset, "holder_count", None),
        getattr(asset, "top10_holders_pct_ex_lp", None),
        getattr(asset, "security_flags", []),
    )
    age = normalize_age(asset.age_hours)
    venue = normalize_venue(
        getattr(asset, "listed_on_cex", None),
        getattr(asset, "listed_on_coingecko", None),
    )

    return round(
        0.30 * liq + 0.20 * vol + 0.15 * att + 0.15 * qual + 0.10 * age + 0.10 * venue,
        1,
    )


def compute_risk_score(asset: AssetCandidate | AssetEntry) -> float:
    """Compute risk score (0-100). Higher = more risky."""
    score = 30.0  # baseline risk for any degen token

    # Age risk
    age_hours = asset.age_hours or 0
    if age_hours < 24:
        score += 25
    elif age_hours < 72:
        score += 15
    elif age_hours < 168:
        score += 5

    # Concentration risk
    top10 = getattr(asset, "top10_holders_pct_ex_lp", None)
    if top10 is not None:
        if top10 > 50:
            score += 25
        elif top10 > 35:
            score += 15
        elif top10 > 25:
            score += 5

    # Liquidity risk
    liq = asset.liquidity_usd or 0
    if liq < 100_000:
        score += 20
    elif liq < 250_000:
        score += 10

    # Security risk
    severe = {"honeypot", "mint_enabled", "freeze_enabled", "blacklistable"}
    flags = getattr(asset, "security_flags", [])
    for flag in flags:
        if flag in severe:
            score += 20
        else:
            score += 5

    return _clamp(score)
