"""CoinGecko API fetcher for metadata and categories.

Docs: https://docs.coingecko.com/
Demo tier: ~30 calls/min, 10k calls/month.
"""
from __future__ import annotations

from typing import Any

from .base import BaseFetcher

DEGEN_CATEGORIES = [
    "meme-token",
    "base-meme-coins",
    "solana-meme-coins",
    "ai-big-data",
    "real-world-assets-rwa",
    "decentralized-finance-defi",
]


class CoinGeckoFetcher(BaseFetcher):
    """Fetcher for CoinGecko Demo API."""

    def __init__(self, api_key: str = "", cache_ttl_seconds: int = 600):
        headers: dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["x-cg-demo-api-key"] = api_key
        super().__init__(
            base_url="https://api.coingecko.com/api/v3",
            cache_ttl_seconds=cache_ttl_seconds,
            default_headers=headers,
        )

    async def get_coin_info(self, coin_id: str) -> dict[str, Any]:
        """GET /coins/{id} — full coin data."""
        return await self.get(
            f"/coins/{coin_id}",
            params={"localization": "false", "tickers": "false", "community_data": "false"},
        )

    async def get_category_coins(
        self,
        category_id: str,
        per_page: int = 50,
    ) -> list[dict[str, Any]]:
        """GET /coins/markets — coins in a specific category."""
        data = await self.get(
            "/coins/markets",
            params={
                "vs_currency": "usd",
                "category": category_id,
                "order": "volume_desc",
                "per_page": per_page,
                "page": 1,
            },
        )
        return data if isinstance(data, list) else []

    async def get_categories(self) -> list[dict[str, Any]]:
        """GET /coins/categories — list all categories."""
        data = await self.get("/coins/categories")
        return data if isinstance(data, list) else []

    async def search(self, query: str) -> dict[str, Any]:
        """GET /search — search for coins."""
        return await self.get("/search", params={"query": query})
