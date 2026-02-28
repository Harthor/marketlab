"""Reddit Data API fetcher for social velocity signals.

Rate limit: 100 QPM per OAuth client.
Subreddits: CryptoMoonShots, SatoshiStreetBets, altcoin, memecoin.
"""
from __future__ import annotations

import logging
from typing import Any

from .base import BaseFetcher

logger = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = [
    "CryptoMoonShots",
    "SatoshiStreetBets",
    "altcoin",
    "memecoin",
]


class RedditFetcher(BaseFetcher):
    """Fetcher for Reddit public JSON API."""

    def __init__(self, cache_ttl_seconds: int = 120):
        super().__init__(
            base_url="https://www.reddit.com",
            cache_ttl_seconds=cache_ttl_seconds,
            default_headers={"User-Agent": "MarketLab-DegenScanner/0.1"},
        )

    async def search_mentions(
        self,
        symbol: str,
        subreddits: list[str] | None = None,
        time_filter: str = "hour",
        limit: int = 25,
    ) -> dict[str, Any]:
        """Search for mentions of a token symbol across subreddits.

        Returns aggregated stats:
            post_count, unique_authors, total_upvotes, posts sample.
        """
        subs = subreddits or DEFAULT_SUBREDDITS
        all_posts: list[dict[str, Any]] = []
        authors: set[str] = set()
        total_ups = 0

        for sub in subs:
            try:
                data = await self.get(
                    f"/r/{sub}/search.json",
                    params={
                        "q": symbol,
                        "restrict_sr": "on",
                        "sort": "new",
                        "t": time_filter,
                        "limit": limit,
                    },
                )
                posts = data.get("data", {}).get("children", [])
                for post in posts:
                    pd = post.get("data", {})
                    all_posts.append({
                        "subreddit": sub,
                        "title": pd.get("title", ""),
                        "author": pd.get("author", ""),
                        "ups": pd.get("ups", 0),
                        "created_utc": pd.get("created_utc", 0),
                        "num_comments": pd.get("num_comments", 0),
                    })
                    authors.add(pd.get("author", ""))
                    total_ups += pd.get("ups", 0)
            except Exception:
                logger.warning("Reddit search failed for %s in r/%s", symbol, sub)

        return {
            "symbol": symbol,
            "post_count": len(all_posts),
            "unique_authors": len(authors),
            "total_upvotes": total_ups,
            "subreddits_searched": subs,
            "time_filter": time_filter,
        }
