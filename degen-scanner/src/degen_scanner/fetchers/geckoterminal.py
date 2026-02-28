"""GeckoTerminal API fetcher.

Docs: https://apiguide.geckoterminal.com/
Rate limit: 30 calls/min. Cache 1 min.
"""
from __future__ import annotations

from typing import Any

from .base import BaseFetcher


class GeckoTerminalFetcher(BaseFetcher):
    """Fetcher for GeckoTerminal free API (v2)."""

    def __init__(self, cache_ttl_seconds: int = 60):
        super().__init__(
            base_url="https://api.geckoterminal.com/api/v2",
            cache_ttl_seconds=cache_ttl_seconds,
            default_headers={"Accept": "application/json"},
        )

    async def get_token_pools(
        self, network: str, token_address: str
    ) -> list[dict[str, Any]]:
        """GET /networks/{network}/tokens/{address}/pools"""
        data = await self.get(f"/networks/{network}/tokens/{token_address}/pools")
        return data.get("data", []) if isinstance(data, dict) else []

    async def get_pool_ohlcv(
        self,
        network: str,
        pool_address: str,
        timeframe: str = "hour",
        aggregate: int = 1,
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        """GET /networks/{network}/pools/{address}/ohlcv/{timeframe}

        timeframe: "minute", "hour", "day"
        """
        data = await self.get(
            f"/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}",
            params={"aggregate": aggregate, "limit": limit},
        )
        if isinstance(data, dict):
            attrs = data.get("data", {}).get("attributes", {})
            return attrs.get("ohlcv_list", [])
        return []

    async def get_trending_pools(self, network: str) -> list[dict[str, Any]]:
        """GET /networks/{network}/trending_pools"""
        data = await self.get(f"/networks/{network}/trending_pools")
        return data.get("data", []) if isinstance(data, dict) else []

    async def get_new_pools(self, network: str) -> list[dict[str, Any]]:
        """GET /networks/{network}/new_pools"""
        data = await self.get(f"/networks/{network}/new_pools")
        return data.get("data", []) if isinstance(data, dict) else []

    async def get_token_info(
        self, network: str, token_address: str
    ) -> dict[str, Any]:
        """GET /networks/{network}/tokens/{address}"""
        data = await self.get(f"/networks/{network}/tokens/{token_address}")
        return data.get("data", {}) if isinstance(data, dict) else {}
