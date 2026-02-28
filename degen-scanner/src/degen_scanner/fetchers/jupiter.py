"""Jupiter API fetcher for Solana token verification and prices.

Docs: https://dev.jup.ag/
"""
from __future__ import annotations

from typing import Any

from .base import BaseFetcher


class JupiterFetcher(BaseFetcher):
    """Fetcher for Jupiter API (Solana only)."""

    def __init__(self, cache_ttl_seconds: int = 120):
        super().__init__(
            base_url="",  # Multiple base URLs
            cache_ttl_seconds=cache_ttl_seconds,
        )

    async def get_token_list(self, tags: str = "verified") -> list[dict[str, Any]]:
        """GET https://tokens.jup.ag/tokens?tags={tags}

        Returns verified Solana tokens.
        """
        data = await self.get(f"https://tokens.jup.ag/tokens?tags={tags}")
        return data if isinstance(data, list) else []

    async def get_prices(self, token_addresses: list[str]) -> dict[str, Any]:
        """GET https://api.jup.ag/price/v2?ids={comma_separated}

        Up to 50 tokens per request.
        Returns {address: {id, price, ...}}.
        """
        if not token_addresses:
            return {}
        joined = ",".join(token_addresses[:50])
        data = await self.get(f"https://api.jup.ag/price/v2?ids={joined}")
        return data.get("data", {}) if isinstance(data, dict) else {}

    async def is_verified(self, token_address: str) -> bool:
        """Check if a token is in Jupiter's verified list."""
        tokens = await self.get_token_list()
        return any(t.get("address") == token_address for t in tokens)
