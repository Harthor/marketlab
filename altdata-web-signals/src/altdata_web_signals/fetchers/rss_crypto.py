"""RSS crypto media fetcher with VADER sentiment analysis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import feedparser
import polars as pl
from dateutil import parser as date_parser

from ..http import ApiClient
from ..storage import write_signal_frame

# Default crypto RSS feeds
DEFAULT_CRYPTO_FEEDS: list[str] = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/",
    "https://www.theblock.co/rss.xml",
]


def _parse_entry_time(entry: dict[str, Any]) -> datetime | None:
    for key in ("published", "updated", "created", "pubDate"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = date_parser.parse(raw)
        except Exception:
            continue
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return None


def _vader_score(text: str) -> float:
    """Return VADER compound sentiment score for *text*."""
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    analyzer = SentimentIntensityAnalyzer()
    return float(analyzer.polarity_scores(text)["compound"])


def parse_crypto_feed(
    feed_payload: str,
    *,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Parse a single RSS feed into a list of entry dicts.

    Each dict has keys: ``date``, ``title``, ``has_btc``, ``sentiment``.
    """
    parsed = feedparser.parse(feed_payload)
    entries: list[dict[str, Any]] = []

    for entry in parsed.entries:
        published = _parse_entry_time(entry)
        if published is None:
            continue
        if published < start or published > end:
            continue

        title = str(entry.get("title", "") or "")
        day = published.replace(hour=0, minute=0, second=0, microsecond=0)
        has_btc = "bitcoin" in title.lower() or "btc" in title.lower()
        sentiment = _vader_score(title) if title.strip() else 0.0

        entries.append({
            "date": day,
            "title": title,
            "has_btc": has_btc,
            "sentiment": sentiment,
        })

    return entries


def aggregate_crypto_entries(
    all_entries: list[dict[str, Any]],
    *,
    start: datetime,
    end: datetime,
) -> pl.DataFrame:
    """Aggregate parsed entries into a daily DataFrame with 3 signal columns.

    Columns:
    - ts_utc (Datetime UTC)
    - signal_rss_crypto_article_count (Int64)
    - signal_rss_crypto_btc_mention_count (Int64)
    - signal_rss_crypto_title_sentiment (Float64, daily mean VADER compound)
    """
    total_days = int((end.date() - start.date()).days) + 1
    day_range = [
        start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=i)
        for i in range(total_days)
    ]

    article_counts: dict[datetime, int] = {d: 0 for d in day_range}
    btc_counts: dict[datetime, int] = {d: 0 for d in day_range}
    sentiment_sums: dict[datetime, float] = {d: 0.0 for d in day_range}
    sentiment_n: dict[datetime, int] = {d: 0 for d in day_range}

    for entry in all_entries:
        day = entry["date"]
        if day not in article_counts:
            continue
        article_counts[day] += 1
        if entry["has_btc"]:
            btc_counts[day] += 1
        sentiment_sums[day] += entry["sentiment"]
        sentiment_n[day] += 1

    rows_ts: list[datetime] = []
    rows_articles: list[int] = []
    rows_btc: list[int] = []
    rows_sentiment: list[float] = []

    for day in sorted(day_range):
        rows_ts.append(day)
        rows_articles.append(article_counts[day])
        rows_btc.append(btc_counts[day])
        n = sentiment_n[day]
        rows_sentiment.append(sentiment_sums[day] / n if n > 0 else 0.0)

    return pl.DataFrame({
        "ts_utc": rows_ts,
        "signal_rss_crypto_article_count": rows_articles,
        "signal_rss_crypto_btc_mention_count": rows_btc,
        "signal_rss_crypto_title_sentiment": rows_sentiment,
    })


def fetch_rss_crypto_signals(
    *,
    feeds: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    signals_root: str | Path = "data/signals",
    freq: str = "1d",
    cache_dir: str | Path = ".cache/altdata-web-signals",
) -> list[Path]:
    """Fetch crypto RSS feeds, compute sentiment, and write signal parquets.

    Writes three signal files:
    - rss_crypto/article_count/{freq}.parquet
    - rss_crypto/btc_mention_count/{freq}.parquet
    - rss_crypto/title_sentiment/{freq}.parquet
    """
    feed_urls = feeds or DEFAULT_CRYPTO_FEEDS
    end_dt = (
        datetime.fromisoformat(end).replace(tzinfo=UTC)
        if end
        else datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    )
    start_dt = (
        datetime.fromisoformat(start).replace(tzinfo=UTC)
        if start
        else end_dt - timedelta(days=365)
    )
    end_dt = end_dt + timedelta(days=1) - timedelta(microseconds=1)

    client = ApiClient(cache_dir=cache_dir)
    all_entries: list[dict[str, Any]] = []

    for feed_url in feed_urls:
        try:
            payload = client.get_text(feed_url)
        except Exception:
            continue
        entries = parse_crypto_feed(payload, start=start_dt, end=end_dt)
        all_entries.extend(entries)

    df = aggregate_crypto_entries(all_entries, start=start_dt, end=end_dt)

    outputs: list[Path] = []
    for col, topic in [
        ("signal_rss_crypto_article_count", "article_count"),
        ("signal_rss_crypto_btc_mention_count", "btc_mention_count"),
        ("signal_rss_crypto_title_sentiment", "title_sentiment"),
    ]:
        frame = df.select(["ts_utc", col])
        outputs.append(
            write_signal_frame(
                frame=frame,
                signals_root=signals_root,
                source="rss_crypto",
                topic=topic,
                freq=freq,
            )
        )

    return outputs
