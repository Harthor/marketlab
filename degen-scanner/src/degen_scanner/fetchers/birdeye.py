"""Birdeye API fetcher.

Docs: https://docs.birdeye.so/
Standard free tier: 1 rps, 30k CUs total.
"""
from __future__ import annotations

from typing import Any

from .base import BaseFetcher


class BirdeyeFetcher(BaseFetcher):
    """Fetcher for Birdeye API (free Standard tier)."""

    def __init__(self, api_key: str = "", cache_ttl_seconds: int = 300):
        headers = {"Accept": "application/json"}
        if api_key:
            headers["X-API-KEY"] = api_key
        super().__init__(
            base_url="https://public-api.birdeye.so",
            cache_ttl_seconds=cache_ttl_seconds,
            default_headers=headers,
        )

    def _chain_header(self, chain: str) -> dict[str, str]:
        return {"x-chain": chain}

    async def get_trending(self, chain: str = "solana") -> list[dict[str, Any]]:
        """GET /defi/token_trending"""
        data = await self.get(
            "/defi/token_trending",
            headers=self._chain_header(chain),
        )
        if isinstance(data, dict):
            return data.get("data", {}).get("tokens", [])
        return []

    async def get_token_security(
        self, address: str, chain: str = "solana"
    ) -> dict[str, Any]:
        """GET /defi/token_security?address={address}"""
        data = await self.get(
            "/defi/token_security",
            params={"address": address},
            headers=self._chain_header(chain),
        )
        return data.get("data", {}) if isinstance(data, dict) else {}

    async def get_holders(
        self, address: str, chain: str = "solana"
    ) -> dict[str, Any]:
        """GET /defi/v3/token/holder?address={address}"""
        data = await self.get(
            "/defi/v3/token/holder",
            params={"address": address},
            headers=self._chain_header(chain),
        )
        return data.get("data", {}) if isinstance(data, dict) else {}

    async def get_holder_distribution(
        self, address: str, chain: str = "solana"
    ) -> dict[str, Any]:
        """GET /holder/v1/distribution?address={address}"""
        data = await self.get(
            "/holder/v1/distribution",
            params={"address": address},
            headers=self._chain_header(chain),
        )
        return data.get("data", {}) if isinstance(data, dict) else {}

    async def get_new_listings(self, chain: str = "solana") -> list[dict[str, Any]]:
        """GET /defi/v3/token/list/scroll — new listings sorted by creation."""
        data = await self.get(
            "/defi/v3/token/list/scroll",
            params={"sort_by": "creation_time", "sort_type": "desc", "limit": 50},
            headers=self._chain_header(chain),
        )
        if isinstance(data, dict):
            return data.get("data", {}).get("tokens", [])
        return []
