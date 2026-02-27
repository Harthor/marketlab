"""HTTP helpers with cache and backoff."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .core import make_cache


def cache_key(url: str, params: dict[str, Any] | None = None) -> str:
    payload = json.dumps({"url": url, "params": params or {}}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


@dataclass
class RateLimitConfig:
    min_interval_s: float = 1.0
    timeout_s: int = 30
    retries: int = 3
    backoff_base_s: float = 1.25
    backoff_cap_s: float = 20.0


class FetchError(RuntimeError):
    pass


class ApiClient:
    """Simple request client con cache + retry + sleep/backoff."""

    def __init__(self, cache_dir: str | Path | None = None, rate_limit: RateLimitConfig | None = None):
        self.cache = make_cache(cache_dir or Path(".cache") / "altdata-web-signals")
        self.rate_limit = rate_limit or RateLimitConfig()
        self._last_request_ts: float = 0.0
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "altdata-web-signals/0.1 (+https://example.local)"
            }
        )

    def _respect_rate_limit(self) -> None:
        wait = self.rate_limit.min_interval_s - (time.perf_counter() - self._last_request_ts)
        if wait > 0:
            time.sleep(wait)
        self._last_request_ts = time.perf_counter()

    def _request_with_backoff(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        params = kwargs.get("params")
        key = cache_key(url, params)
        cached = self.cache.get(key)
        if isinstance(cached, dict) and cached.get("ok"):
            response = requests.Response()
            response._content = cached["content"].encode("utf-8")
            response.status_code = int(cached.get("status_code", 200))
            response.url = url
            return response

        for attempt in range(1, self.rate_limit.retries + 1):
            self._respect_rate_limit()
            try:
                resp = self._session.request(method, url, timeout=self.rate_limit.timeout_s, **kwargs)
            except requests.RequestException as exc:
                if attempt >= self.rate_limit.retries:
                    raise FetchError(f"Network error calling {url}: {exc}") from exc
                time.sleep(min(self.rate_limit.backoff_cap_s, self.rate_limit.backoff_base_s * (2 ** (attempt - 1))))
                continue

            if 200 <= resp.status_code < 300:
                payload = {
                    "ok": True,
                    "status_code": int(resp.status_code),
                    "content": resp.text,
                }
                try:
                    self.cache.set(key, payload)
                except Exception:
                    pass
                return resp

            should_retry = resp.status_code >= 500 or resp.status_code == 429
            if not should_retry:
                raise FetchError(f"Request failed for {url}: status={resp.status_code}")

            time.sleep(min(self.rate_limit.backoff_cap_s, self.rate_limit.backoff_base_s * (2 ** (attempt - 1))))
            if attempt >= self.rate_limit.retries:
                break

        raise FetchError(f"Request failed for {url}: exhausted retries")

    def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        return self._request_with_backoff("GET", url, params=params).text

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._request_with_backoff("GET", url, params=params)
        try:
            data = resp.json()
        except ValueError as exc:
            raise FetchError(f"Invalid json from {url}: {exc}") from exc
        return data
