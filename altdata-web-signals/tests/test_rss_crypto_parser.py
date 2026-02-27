"""Tests for RSS crypto fetcher (parse + aggregate + transforms + VADER sentiment)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from altdata_web_signals.fetchers.rss_crypto import (
    add_rss_crypto_transforms,
    aggregate_crypto_entries,
    parse_crypto_feed,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_crypto_feed_extracts_entries() -> None:
    payload = (FIXTURES / "rss_crypto_sample.xml").read_text()
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, 23, 59, 59, tzinfo=UTC)

    entries = parse_crypto_feed(payload, start=start, end=end)

    assert len(entries) == 5
    # Check BTC detection
    btc_entries = [e for e in entries if e["has_btc"]]
    assert len(btc_entries) == 3  # "Bitcoin surges...", "BTC mining...", "Bitcoin adoption..."

    # Each entry has required keys
    for entry in entries:
        assert "date" in entry
        assert "title" in entry
        assert "has_btc" in entry
        assert "sentiment" in entry
        assert isinstance(entry["sentiment"], float)
        assert -1.0 <= entry["sentiment"] <= 1.0


def test_aggregate_crypto_entries_produces_correct_columns() -> None:
    payload = (FIXTURES / "rss_crypto_sample.xml").read_text()
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_crypto_feed(payload, start=start, end=end)
    df = aggregate_crypto_entries(entries, start=start, end=end)

    assert "ts_utc" in df.columns
    assert "signal_rss_crypto_article_count" in df.columns
    assert "signal_rss_crypto_btc_mention_count" in df.columns
    assert "signal_rss_crypto_title_sentiment" in df.columns

    # 3 days: Jan 10, 11, 12
    assert df.shape[0] == 3

    # Sorted ascending
    ts_list = df["ts_utc"].to_list()
    assert ts_list == sorted(ts_list)

    # Jan 10: 2 articles, 1 BTC mention
    row0 = df.row(0, named=True)
    assert row0["signal_rss_crypto_article_count"] == 2
    assert row0["signal_rss_crypto_btc_mention_count"] == 1


def test_aggregate_empty_entries_returns_zero_filled() -> None:
    start = datetime(2022, 1, 1, tzinfo=UTC)
    end = datetime(2022, 1, 3, tzinfo=UTC)

    df = aggregate_crypto_entries([], start=start, end=end)

    assert df.shape[0] == 3
    assert all(v == 0 for v in df["signal_rss_crypto_article_count"].to_list())
    assert all(v == 0 for v in df["signal_rss_crypto_btc_mention_count"].to_list())
    assert all(v == 0.0 for v in df["signal_rss_crypto_title_sentiment"].to_list())


def test_rss_crypto_transforms_columns_exist() -> None:
    """Verify all derived columns are present after transforms."""
    payload = (FIXTURES / "rss_crypto_sample.xml").read_text()
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_crypto_feed(payload, start=start, end=end)
    df = aggregate_crypto_entries(entries, start=start, end=end)
    df = add_rss_crypto_transforms(df)

    expected = [
        "signal_rss_crypto_article_count_delta",
        "signal_rss_crypto_article_count_zscore_7d",
        "signal_rss_crypto_sentiment_delta",
        "signal_rss_crypto_btc_mention_delta",
        "signal_rss_crypto_neg_sentiment_flag",
    ]
    for col in expected:
        assert col in df.columns, f"Missing column: {col}"

    # Row count unchanged
    assert df.shape[0] == 3


def test_rss_crypto_neg_sentiment_flag_values() -> None:
    """neg_sentiment_flag should be 0 or 1."""
    payload = (FIXTURES / "rss_crypto_sample.xml").read_text()
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_crypto_feed(payload, start=start, end=end)
    df = aggregate_crypto_entries(entries, start=start, end=end)
    df = add_rss_crypto_transforms(df)

    flags = df["signal_rss_crypto_neg_sentiment_flag"].to_list()
    assert all(v in (0, 1) for v in flags)
