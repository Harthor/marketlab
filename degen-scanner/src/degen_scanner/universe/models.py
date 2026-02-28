"""Data models for the degen universe."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Category(StrEnum):
    MEME_BLUECHIP = "meme_bluechip"
    MEME_EMERGING = "meme_emerging"
    NARRATIVE_HIGH_BETA = "narrative_high_beta"
    DEX_NEW_LAUNCH = "dex_new_launch"
    PRE_CEX_WATCH = "pre_cex_watch"
    DEAD_OR_TOXIC = "dead_or_toxic"
    UNCLASSIFIED = "unclassified"


class VenueProfile(StrEnum):
    CEX_MATURE = "cex_mature"
    DEX_MATURE = "dex_mature"
    DEX_NEW = "dex_new"
    MIXED = "mixed"


class AssetStatus(StrEnum):
    ACTIVE = "active"
    WATCH = "watch"
    REMOVED = "removed"
    DEAD = "dead"


class AssetCandidate(BaseModel):
    """Raw candidate from a discovery source, before filtering."""

    asset_uid: str  # "{chain}:{token_address}"
    symbol: str
    name: str = ""
    chain: str
    token_address: str
    source: str  # which discovery source found it

    # Market data (may be partial)
    market_cap_usd: float | None = None
    fdv_usd: float | None = None
    liquidity_usd: float | None = None
    volume_24h_usd: float | None = None
    volume_1h_usd: float | None = None
    price_usd: float | None = None

    # Pool info
    pool_address: str | None = None
    dex_id: str | None = None
    quote_token: str | None = None

    # On-chain
    age_hours: float | None = None
    holder_count: int | None = None
    top10_holders_pct_ex_lp: float | None = None
    single_max_holder_pct_ex_lp: float | None = None
    creator_wallet_pct: float | None = None

    # Security
    security_flags: list[str] = Field(default_factory=list)
    mint_authority_disabled: bool | None = None
    freeze_authority_disabled: bool | None = None
    contract_verified: bool | None = None

    # Attention
    attention_flags: list[str] = Field(default_factory=list)

    # Listed status
    listed_on_coingecko: bool | None = None
    coingecko_id: str | None = None
    listed_on_cex: bool | None = None

    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AssetEntry(BaseModel):
    """Scored, categorized asset in the watchlist."""

    asset_uid: str
    symbol: str
    name: str = ""
    chain: str
    token_address: str
    category: Category = Category.UNCLASSIFIED
    venue_profile: VenueProfile = VenueProfile.DEX_NEW
    status: AssetStatus = AssetStatus.ACTIVE

    # Pool
    primary_pool_address: str | None = None
    primary_dex_id: str | None = None
    quote_token: str | None = None
    pool_switch_count_7d: int = 0

    # Market
    market_cap_usd: float | None = None
    fdv_usd: float | None = None
    liquidity_usd: float | None = None
    volume_24h_usd: float | None = None
    volume_1h_usd: float | None = None
    price_usd: float | None = None

    # On-chain
    age_hours: float | None = None
    holder_count: int | None = None
    top10_holders_pct_ex_lp: float | None = None
    creator_wallet_pct: float | None = None

    # Security & attention
    security_flags: list[str] = Field(default_factory=list)
    attention_flags: list[str] = Field(default_factory=list)

    # Scores
    universe_score: float = 0.0
    social_score: float = 0.0
    onchain_score: float = 0.0
    risk_score: float = 0.0

    # Metadata
    include_reason: list[str] = Field(default_factory=list)
    listed_on_coingecko: bool | None = None
    coingecko_id: str | None = None

    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def risk_level(self) -> str:
        if self.risk_score >= 75:
            return "extreme"
        if self.risk_score >= 50:
            return "high"
        if self.risk_score >= 25:
            return "medium"
        return "low"


class WatchlistSnapshot(BaseModel):
    """A point-in-time snapshot of the degen watchlist."""

    snapshot_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    policy_version: int = 1
    chains: list[str] = Field(default_factory=list)
    total_candidates_scanned: int = 0
    total_after_filters: int = 0
    tokens: list[AssetEntry] = Field(default_factory=list)

    # Per-category counts
    category_counts: dict[str, int] = Field(default_factory=dict)

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize for the API endpoint."""
        return {
            "snapshot_id": self.snapshot_id,
            "generated_at": self.generated_at.isoformat(),
            "total_tokens": len(self.tokens),
            "category_counts": self.category_counts,
            "tokens": [t.model_dump(mode="json") for t in self.tokens],
        }
