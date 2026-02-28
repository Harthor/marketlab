"""Tests for fetchers with mocked HTTP responses."""
from __future__ import annotations

import httpx
import pytest

from degen_scanner.fetchers.base import BaseFetcher, RateLimitError
from degen_scanner.fetchers.birdeye import BirdeyeFetcher
from degen_scanner.fetchers.coingecko import CoinGeckoFetcher
from degen_scanner.fetchers.dexscreener import DexScreenerFetcher
from degen_scanner.fetchers.geckoterminal import GeckoTerminalFetcher
from degen_scanner.fetchers.jupiter import JupiterFetcher
from degen_scanner.fetchers.reddit import RedditFetcher

# ---------------------------------------------------------------------------
# BaseFetcher tests
# ---------------------------------------------------------------------------


class TestBaseFetcher:
    @pytest.mark.asyncio
    async def test_cache_hit(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/test", json={"ok": True})
        fetcher = BaseFetcher(base_url="https://example.com", cache_ttl_seconds=300)
        r1 = await fetcher.get("/test")
        r2 = await fetcher.get("/test")
        assert r1 == r2
        # Only one HTTP call should have been made (second is cached)
        assert len(httpx_mock.get_requests()) == 1
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/rate", status_code=429)
        fetcher = BaseFetcher(base_url="https://example.com", cache_ttl_seconds=0)
        with pytest.raises(RateLimitError):
            await fetcher.get_raw("/rate")
        await fetcher.close()


# ---------------------------------------------------------------------------
# DexScreener tests
# ---------------------------------------------------------------------------


class TestDexScreenerFetcher:
    @pytest.mark.asyncio
    async def test_get_latest_boosts(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.dexscreener.com/token-boosts/latest/v1",
            json=[
                {"chainId": "solana", "tokenAddress": "ABC123", "amount": 500},
                {"chainId": "base", "tokenAddress": "DEF456", "amount": 200},
            ],
        )
        fetcher = DexScreenerFetcher()
        boosts = await fetcher.get_latest_boosts()
        assert len(boosts) == 2
        assert boosts[0]["chainId"] == "solana"
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_tokens_batch(self, httpx_mock):
        httpx_mock.add_response(
            url=httpx.URL("https://api.dexscreener.com/tokens/v1/ADDR1,ADDR2"),
            json=[
                {"baseToken": {"symbol": "TOK1", "address": "ADDR1"}, "pairAddress": "P1"},
                {"baseToken": {"symbol": "TOK2", "address": "ADDR2"}, "pairAddress": "P2"},
            ],
        )
        fetcher = DexScreenerFetcher()
        pairs = await fetcher.get_tokens_batch(["ADDR1", "ADDR2"])
        assert len(pairs) == 2
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_search_pairs(self, httpx_mock):
        httpx_mock.add_response(
            url=httpx.URL("https://api.dexscreener.com/latest/dex/search?q=PEPE"),
            json={"pairs": [{"baseToken": {"symbol": "PEPE"}}]},
        )
        fetcher = DexScreenerFetcher()
        pairs = await fetcher.search_pairs("PEPE")
        assert len(pairs) == 1
        await fetcher.close()


# ---------------------------------------------------------------------------
# GeckoTerminal tests
# ---------------------------------------------------------------------------


class TestGeckoTerminalFetcher:
    @pytest.mark.asyncio
    async def test_get_trending_pools(self, httpx_mock):
        httpx_mock.add_response(
            url=httpx.URL("https://api.geckoterminal.com/api/v2/networks/solana/trending_pools"),
            json={
                "data": [
                    {
                        "attributes": {
                            "name": "Pool1",
                            "base_token": {"address": "X", "symbol": "TOK"},
                        }
                    }
                ]
            },
        )
        fetcher = GeckoTerminalFetcher()
        pools = await fetcher.get_trending_pools("solana")
        assert len(pools) == 1
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_pool_ohlcv(self, httpx_mock):
        httpx_mock.add_response(
            json={
                "data": {"attributes": {"ohlcv_list": [[1700000000, 1.0, 1.1, 0.9, 1.05, 50000]]}}
            },
        )
        fetcher = GeckoTerminalFetcher()
        bars = await fetcher.get_pool_ohlcv("solana", "pool123")
        assert len(bars) == 1
        assert bars[0][0] == 1700000000
        await fetcher.close()


# ---------------------------------------------------------------------------
# Birdeye tests
# ---------------------------------------------------------------------------


class TestBirdeyeFetcher:
    @pytest.mark.asyncio
    async def test_get_trending(self, httpx_mock):
        httpx_mock.add_response(
            json={"data": {"tokens": [
                {"address": "SOL123", "symbol": "WIF", "price": 1.5, "v24hUSD": 5000000},
            ]}},
        )
        fetcher = BirdeyeFetcher()
        trending = await fetcher.get_trending("solana")
        assert len(trending) == 1
        assert trending[0]["symbol"] == "WIF"
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_token_security(self, httpx_mock):
        httpx_mock.add_response(
            json={"data": {"isToken2022": False, "isMintable": False}},
        )
        fetcher = BirdeyeFetcher()
        sec = await fetcher.get_token_security("SOL123")
        assert "isToken2022" in sec
        await fetcher.close()


# ---------------------------------------------------------------------------
# Reddit tests
# ---------------------------------------------------------------------------


class TestRedditFetcher:
    @pytest.mark.asyncio
    async def test_search_mentions(self, httpx_mock):
        httpx_mock.add_response(
            json={"data": {"children": [
                {
                    "data": {
                        "title": "PEPE to the moon!",
                        "author": "degen1",
                        "ups": 42,
                        "created_utc": 1700000000,
                        "num_comments": 5,
                    }
                },
                {
                    "data": {
                        "title": "Is PEPE dead?",
                        "author": "degen2",
                        "ups": 10,
                        "created_utc": 1700000100,
                        "num_comments": 2,
                    }
                },
            ]}},
        )
        fetcher = RedditFetcher()
        result = await fetcher.search_mentions("PEPE", subreddits=["CryptoMoonShots"])
        assert result["post_count"] == 2
        assert result["unique_authors"] == 2
        assert result["total_upvotes"] == 52
        await fetcher.close()


# ---------------------------------------------------------------------------
# CoinGecko tests
# ---------------------------------------------------------------------------


class TestCoinGeckoFetcher:
    @pytest.mark.asyncio
    async def test_get_category_coins(self, httpx_mock):
        httpx_mock.add_response(
            json=[{"id": "pepe", "symbol": "pepe", "current_price": 0.00001}],
        )
        fetcher = CoinGeckoFetcher()
        coins = await fetcher.get_category_coins("meme-token")
        assert len(coins) == 1
        await fetcher.close()


# ---------------------------------------------------------------------------
# Jupiter tests
# ---------------------------------------------------------------------------


class TestJupiterFetcher:
    @pytest.mark.asyncio
    async def test_get_prices(self, httpx_mock):
        httpx_mock.add_response(
            json={"data": {"SOL123": {"id": "SOL123", "price": "1.5"}}},
        )
        fetcher = JupiterFetcher()
        prices = await fetcher.get_prices(["SOL123"])
        assert "SOL123" in prices
        await fetcher.close()
