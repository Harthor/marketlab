"""RSS crypto media fetcher with FinBERT sentiment analysis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import feedparser
import polars as pl
from dateutil import parser as date_parser

from ..http import ApiClient
from ..storage import write_signal_frame
from ..transforms import add_asof_utc, add_delta, add_delta_log1p, add_zscore_rolling

# 10 crypto RSS feeds (5 original + 5 new)
DEFAULT_CRYPTO_FEEDS: list[str] = [
    # Original 5
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/",
    "https://www.theblock.co/rss.xml",
    # New 5
    "https://blockworks.co/feed",
    "https://thedefiant.io/feed",
    "https://unchainedcrypto.com/feed/",
    "https://cryptoslate.com/feed/",
    "https://www.newsbtc.com/feed/",
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


def parse_crypto_feed(
    feed_payload: str,
    *,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Parse a single RSS feed into a list of entry dicts.

    Each dict has keys: ``date``, ``title``, ``has_btc``.
    Sentiment is computed in batch at aggregation time (FinBERT).
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

        entries.append({
            "date": day,
            "title": title,
            "has_btc": has_btc,
        })

    return entries


def aggregate_crypto_entries(
    all_entries: list[dict[str, Any]],
    *,
    start: datetime,
    end: datetime,
) -> pl.DataFrame:
    """Aggregate parsed entries into a daily DataFrame.

    Columns:
    - ts_utc (Datetime UTC)
    - signal_rss_crypto_article_count (Int64)
    - signal_rss_crypto_btc_mention_count (Int64)
    - signal_rss_crypto_title_sentiment (Float64, FinBERT mean — backward compat)
    - signal_rss_crypto_sentiment_finbert_mean (Float64)
    - signal_rss_crypto_sentiment_finbert_std (Float64)
    - signal_rss_crypto_positive_ratio (Float64)
    - signal_rss_crypto_negative_ratio (Float64)
    - signal_rss_crypto_neg_minus_pos (Float64)
    - signal_rss_crypto_sentiment_defined (Int8)
    """
    from ..sentiment import finbert_batch_stats

    total_days = int((end.date() - start.date()).days) + 1
    day_range = [
        start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=i)
        for i in range(total_days)
    ]

    # Group entries by day
    day_entries: dict[datetime, list[dict[str, Any]]] = {d: [] for d in day_range}
    for entry in all_entries:
        day = entry["date"]
        if day in day_entries:
            day_entries[day].append(entry)

    rows: list[dict[str, Any]] = []
    for day in sorted(day_range):
        entries = day_entries[day]
        article_count = len(entries)
        btc_count = sum(1 for e in entries if e["has_btc"])

        titles = [e["title"] for e in entries if e["title"].strip()]
        stats = finbert_batch_stats(titles)

        rows.append({
            "ts_utc": day,
            "signal_rss_crypto_article_count": article_count,
            "signal_rss_crypto_btc_mention_count": btc_count,
            "signal_rss_crypto_title_sentiment": stats["mean"],
            "signal_rss_crypto_sentiment_finbert_mean": stats["mean"],
            "signal_rss_crypto_sentiment_finbert_std": stats["std"],
            "signal_rss_crypto_positive_ratio": stats["positive_ratio"],
            "signal_rss_crypto_negative_ratio": stats["negative_ratio"],
            "signal_rss_crypto_neg_minus_pos": stats["neg_minus_pos"],
        })

    schema = {
        "ts_utc": pl.Datetime("us", "UTC"),
        "signal_rss_crypto_article_count": pl.Int64,
        "signal_rss_crypto_btc_mention_count": pl.Int64,
        "signal_rss_crypto_title_sentiment": pl.Float64,
        "signal_rss_crypto_sentiment_finbert_mean": pl.Float64,
        "signal_rss_crypto_sentiment_finbert_std": pl.Float64,
        "signal_rss_crypto_positive_ratio": pl.Float64,
        "signal_rss_crypto_negative_ratio": pl.Float64,
        "signal_rss_crypto_neg_minus_pos": pl.Float64,
    }
    df = pl.DataFrame(rows, schema=schema)

    # Definedness flag: 1 when we have actual sentiment data
    df = df.with_columns(
        (pl.col("signal_rss_crypto_article_count") > 0)
        .cast(pl.Int8)
        .alias("signal_rss_crypto_sentiment_defined"),
    )

    return df


def add_rss_crypto_transforms(df: pl.DataFrame) -> pl.DataFrame:
    """Add stationarity transforms to RSS crypto DataFrame.

    New columns:
    - signal_rss_crypto_article_count_delta
    - signal_rss_crypto_article_count_zscore_7d
    - signal_rss_crypto_article_count_delta_log1p (+ _log1p intermediate)
    - signal_rss_crypto_sentiment_delta (from title_sentiment)
    - signal_rss_crypto_btc_mention_delta (from btc_mention_count)
    - signal_rss_crypto_btc_mention_count_delta_log1p (+ _log1p intermediate)
    - signal_rss_crypto_neg_sentiment_flag (1 if sentiment < -0.2)
    - asof_utc (ts_utc + 1 day)
    """
    df = add_delta(df, "signal_rss_crypto_article_count")
    df = add_zscore_rolling(df, "signal_rss_crypto_article_count", window=7)
    df = add_delta_log1p(df, "signal_rss_crypto_article_count")

    df = add_delta(df, "signal_rss_crypto_title_sentiment")
    # Rename to match spec: sentiment_delta (not title_sentiment_delta)
    if "signal_rss_crypto_title_sentiment_delta" in df.columns:
        df = df.rename({"signal_rss_crypto_title_sentiment_delta": "signal_rss_crypto_sentiment_delta"})

    df = add_delta(df, "signal_rss_crypto_btc_mention_count")
    # Rename: btc_mention_delta
    if "signal_rss_crypto_btc_mention_count_delta" in df.columns:
        df = df.rename({"signal_rss_crypto_btc_mention_count_delta": "signal_rss_crypto_btc_mention_delta"})
    df = add_delta_log1p(df, "signal_rss_crypto_btc_mention_count")

    # Negative sentiment flag (null sentiment → 0, not flagged)
    df = df.with_columns(
        pl.when(
            pl.col("signal_rss_crypto_title_sentiment").is_not_null()
            & (pl.col("signal_rss_crypto_title_sentiment") < -0.2)
        )
        .then(1)
        .otherwise(0)
        .alias("signal_rss_crypto_neg_sentiment_flag")
    )

    # asof_utc: day T data available at T+1 00:00 UTC
    df = add_asof_utc(df)

    return df


def fetch_rss_crypto_signals(
    *,
    feeds: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    signals_root: str | Path = "data/signals",
    freq: str = "1d",
    cache_dir: str | Path = ".cache/altdata-web-signals",
) -> list[Path]:
    """Fetch crypto RSS feeds, compute FinBERT sentiment, write signal parquets."""
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
    df = add_rss_crypto_transforms(df)

    meta_cols = [c for c in ["ts_utc", "asof_utc"] if c in df.columns]
    outputs: list[Path] = []
    for col in [c for c in df.columns if c.startswith("signal_rss_crypto_")]:
        topic = col.removeprefix("signal_rss_crypto_")
        frame = df.select(meta_cols + [col])
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
