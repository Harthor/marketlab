"""DexScreener API fetcher.

Docs: https://docs.dexscreener.com/api/reference
Rate limits: 300 rpm general, 60 rpm for boost/profile endpoints.
"""
from __future__ import annotations

from typing import Any

from .base import BaseFetcher


class DexScreenerFetcher(BaseFetcher):
    """Fetcher for DexScreener free API."""

    def __init__(self, cache_ttl_seconds: int = 30):
        super().__init__(
            base_url="https://api.dexscreener.com",
            cache_ttl_seconds=cache_ttl_seconds,
        )

    async def get_token_pairs(self, chain: str, token_address: str) -> list[dict[str, Any]]:
        """GET /token-pairs/v1/{chainId}/{tokenAddress}

        Returns pairs for a specific token on a chain.
        """
        data = await self.get(f"/token-pairs/v1/{chain}/{token_address}")
        return data if isinstance(data, list) else data.get("pairs", [])

    async def get_tokens_batch(self, token_addresses: list[str]) -> list[dict[str, Any]]:
        """GET /tokens/v1/{tokenAddresses}

        Batch lookup — up to 30 comma-separated addresses.
        Returns pair data for each token.
        """
        if not token_addresses:
            return []
        joined = ",".join(token_addresses[:30])
        data = await self.get(f"/tokens/v1/{joined}")
        return data if isinstance(data, list) else data.get("pairs", [])

    async def get_latest_boosts(self) -> list[dict[str, Any]]:
        """GET /token-boosts/latest/v1

        Rate limit: 60 rpm.
        """
        data = await self.get("/token-boosts/latest/v1")
        return data if isinstance(data, list) else []

    async def get_top_boosts(self) -> list[dict[str, Any]]:
        """GET /token-boosts/top/v1

        Rate limit: 60 rpm.
        """
        data = await self.get("/token-boosts/top/v1")
        return data if isinstance(data, list) else []

    async def get_community_takeovers(self) -> list[dict[str, Any]]:
        """GET /community-takeovers/latest/v1"""
        data = await self.get("/community-takeovers/latest/v1")
        return data if isinstance(data, list) else []

    async def search_pairs(self, query: str) -> list[dict[str, Any]]:
        """GET /latest/dex/search?q={query}

        Search for pairs by token name/symbol/address.
        """
        data = await self.get("/latest/dex/search", params={"q": query})
        return data.get("pairs", []) if isinstance(data, dict) else []
