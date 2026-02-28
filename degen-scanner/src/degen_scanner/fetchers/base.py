"""Base fetcher with retry, rate limiting, and response caching."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when we hit a rate limit (429)."""


class BaseFetcher:
    """Base HTTP fetcher with in-memory cache, retry, and rate-limit awareness."""

    def __init__(
        self,
        base_url: str = "",
        cache_ttl_seconds: int = 60,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._default_headers = default_headers or {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers=self._default_headers,
            )
        return self._client

    def _cache_key(self, url: str, params: dict | None) -> str:
        parts = [url]
        if params:
            parts.append(str(sorted(params.items())))
        return "|".join(parts)

    def _get_cached(self, key: str) -> Any | None:
        if key in self._cache:
            ts, data = self._cache[key]
            if time.time() - ts < self.cache_ttl:
                return data
            del self._cache[key]
        return None

    def _set_cached(self, key: str, data: Any) -> None:
        self._cache[key] = (time.time(), data)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """GET request with cache, retry, and rate limit handling."""
        url = f"{self.base_url}{path}" if not path.startswith("http") else path
        cache_key = self._cache_key(url, params)

        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        client = await self._get_client()
        resp = await client.get(url, params=params, headers=headers)

        if resp.status_code == 429:
            logger.warning("Rate limited on %s, will retry", url)
            raise RateLimitError(f"429 on {url}")

        resp.raise_for_status()
        data = resp.json()
        self._set_cached(cache_key, data)
        return data

    async def get_raw(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """GET without cache — for endpoints where freshness matters."""
        url = f"{self.base_url}{path}" if not path.startswith("http") else path
        client = await self._get_client()
        resp = await client.get(url, params=params, headers=headers)
        if resp.status_code == 429:
            raise RateLimitError(f"429 on {url}")
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
