"""Discovery: fetch token candidates from multiple sources."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ..fetchers.birdeye import BirdeyeFetcher
from ..fetchers.dexscreener import DexScreenerFetcher
from ..fetchers.geckoterminal import GeckoTerminalFetcher
from .models import AssetCandidate

logger = logging.getLogger(__name__)


def _hours_since(iso_str: str | None) -> float | None:
    """Parse an ISO timestamp and return hours since then."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = datetime.now(UTC) - dt
        return max(delta.total_seconds() / 3600, 0)
    except (ValueError, TypeError):
        return None


async def discover_from_dexscreener(
    chains: list[str],
    fetcher: DexScreenerFetcher,
) -> list[AssetCandidate]:
    """Discover tokens from DexScreener boosts + trending."""
    candidates: list[AssetCandidate] = []

    # 1. Latest boosts
    boosts = await fetcher.get_latest_boosts()
    boosted_addresses: set[str] = set()
    for item in boosts:
        chain = item.get("chainId", "")
        if chain not in chains:
            continue
        address = item.get("tokenAddress", "")
        if not address:
            continue
        uid = f"{chain}:{address}"
        boosted_addresses.add(uid)

    # 2. Top boosts
    top_boosts = await fetcher.get_top_boosts()
    top_boosted: set[str] = set()
    for item in top_boosts:
        chain = item.get("chainId", "")
        address = item.get("tokenAddress", "")
        if chain in chains and address:
            top_boosted.add(f"{chain}:{address}")
            boosted_addresses.add(f"{chain}:{address}")

    # 3. Fetch pair data for boosted tokens (batch by chain)
    by_chain: dict[str, list[str]] = {}
    for uid in boosted_addresses:
        ch, addr = uid.split(":", 1)
        by_chain.setdefault(ch, []).append(addr)

    for chain_id, addresses in by_chain.items():
        # DexScreener allows up to 30 addresses per batch
        for i in range(0, len(addresses), 30):
            batch = addresses[i : i + 30]
            pairs = await fetcher.get_tokens_batch(batch)
            for pair in pairs:
                addr = pair.get("baseToken", {}).get("address", "")
                uid = f"{chain_id}:{addr}"
                flags = []
                if uid in boosted_addresses:
                    flags.append("dexscreener_boosted")
                if uid in top_boosted:
                    flags.append("dexscreener_top_boost")

                candidates.append(
                    AssetCandidate(
                        asset_uid=uid,
                        symbol=pair.get("baseToken", {}).get("symbol", "???"),
                        name=pair.get("baseToken", {}).get("name", ""),
                        chain=chain_id,
                        token_address=addr,
                        source="dexscreener",
                        market_cap_usd=pair.get("marketCap"),
                        fdv_usd=pair.get("fdv"),
                        liquidity_usd=(pair.get("liquidity") or {}).get("usd"),
                        volume_24h_usd=(pair.get("volume") or {}).get("h24"),
                        volume_1h_usd=(pair.get("volume") or {}).get("h1"),
                        price_usd=_safe_float(pair.get("priceUsd")),
                        pool_address=pair.get("pairAddress"),
                        dex_id=pair.get("dexId"),
                        quote_token=pair.get("quoteToken", {}).get("symbol"),
                        age_hours=_hours_since(pair.get("pairCreatedAt")),
                        attention_flags=flags,
                    )
                )

    logger.info("DexScreener discovery: %d candidates from %d chains", len(candidates), len(chains))
    return candidates


async def discover_from_geckoterminal(
    chains: list[str],
    fetcher: GeckoTerminalFetcher,
    chain_config: dict[str, Any],
) -> list[AssetCandidate]:
    """Discover tokens from GeckoTerminal trending + new pools."""
    candidates: list[AssetCandidate] = []

    for chain in chains:
        network = chain_config.get(chain, {}).get("gecko_network", chain)

        # Trending pools
        trending = await fetcher.get_trending_pools(network)
        for pool in trending:
            attrs = pool.get("attributes", {})
            base = (attrs.get("base_token") or {})
            addr = base.get("address", "")
            if not addr:
                continue
            candidates.append(
                AssetCandidate(
                    asset_uid=f"{chain}:{addr}",
                    symbol=base.get("symbol", "???"),
                    name=attrs.get("name", ""),
                    chain=chain,
                    token_address=addr,
                    source="geckoterminal",
                    volume_24h_usd=_safe_float(attrs.get("volume_usd", {}).get("h24")),
                    liquidity_usd=_safe_float(attrs.get("reserve_in_usd")),
                    pool_address=attrs.get("address"),
                    attention_flags=["geckoterminal_trending"],
                )
            )

        # New pools
        new_pools = await fetcher.get_new_pools(network)
        for pool in new_pools:
            attrs = pool.get("attributes", {})
            base = (attrs.get("base_token") or {})
            addr = base.get("address", "")
            if not addr:
                continue
            uid = f"{chain}:{addr}"
            # Skip if already in candidates
            if any(c.asset_uid == uid for c in candidates):
                continue
            candidates.append(
                AssetCandidate(
                    asset_uid=uid,
                    symbol=base.get("symbol", "???"),
                    name=attrs.get("name", ""),
                    chain=chain,
                    token_address=addr,
                    source="geckoterminal",
                    volume_24h_usd=_safe_float(attrs.get("volume_usd", {}).get("h24")),
                    liquidity_usd=_safe_float(attrs.get("reserve_in_usd")),
                    pool_address=attrs.get("address"),
                    attention_flags=["new_pool"],
                )
            )

    logger.info("GeckoTerminal discovery: %d candidates", len(candidates))
    return candidates


async def discover_from_birdeye(
    fetcher: BirdeyeFetcher,
    chain: str = "solana",
) -> list[AssetCandidate]:
    """Discover tokens from Birdeye trending."""
    candidates: list[AssetCandidate] = []
    trending = await fetcher.get_trending(chain)

    for i, token in enumerate(trending):
        addr = token.get("address", "")
        if not addr:
            continue
        flags = ["birdeye_trending"]
        if i < 10:
            flags.append("birdeye_trending_top10")

        candidates.append(
            AssetCandidate(
                asset_uid=f"{chain}:{addr}",
                symbol=token.get("symbol", "???"),
                name=token.get("name", ""),
                chain=chain,
                token_address=addr,
                source="birdeye",
                price_usd=token.get("price"),
                volume_24h_usd=token.get("v24hUSD"),
                liquidity_usd=token.get("liquidity"),
                market_cap_usd=token.get("mc"),
                attention_flags=flags,
            )
        )

    logger.info("Birdeye discovery (%s): %d candidates", chain, len(candidates))
    return candidates


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return f if f == f else None  # NaN check
    except (ValueError, TypeError):
        return None
