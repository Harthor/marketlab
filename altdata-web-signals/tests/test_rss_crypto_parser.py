"""Tests for RSS crypto fetcher (parse + aggregate + transforms + FinBERT sentiment)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from altdata_web_signals.fetchers.rss_crypto import (
    add_rss_crypto_transforms,
    aggregate_crypto_entries,
    parse_crypto_feed,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _make_mock_pipeline() -> MagicMock:
    """Mock FinBERT pipeline returning deterministic results."""
    mock = MagicMock()

    def side_effect(texts: list[str], batch_size: int = 32) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for text in texts:
            lower = text.lower()
            if "surge" in lower or "grows" in lower or "adoption" in lower:
                results.append({"label": "positive", "score": 0.85})
            elif "concern" in lower or "crash" in lower or "ban" in lower:
                results.append({"label": "negative", "score": 0.78})
            else:
                results.append({"label": "neutral", "score": 0.60})
        return results

    mock.side_effect = side_effect
    return mock


def test_parse_crypto_feed_extracts_entries() -> None:
    payload = (FIXTURES / "rss_crypto_sample.xml").read_text()
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, 23, 59, 59, tzinfo=UTC)

    entries = parse_crypto_feed(payload, start=start, end=end)

    assert len(entries) == 5
    # Check BTC detection
    btc_entries = [e for e in entries if e["has_btc"]]
    assert len(btc_entries) == 3  # "Bitcoin surges...", "BTC mining...", "Bitcoin adoption..."

    # Each entry has required keys (no sentiment key — FinBERT runs at aggregation)
    for entry in entries:
        assert "date" in entry
        assert "title" in entry
        assert "has_btc" in entry
        assert "sentiment" not in entry  # VADER removed


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_aggregate_crypto_entries_produces_correct_columns(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    payload = (FIXTURES / "rss_crypto_sample.xml").read_text()
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_crypto_feed(payload, start=start, end=end)
    df = aggregate_crypto_entries(entries, start=start, end=end)

    assert "ts_utc" in df.columns
    assert "signal_rss_crypto_article_count" in df.columns
    assert "signal_rss_crypto_btc_mention_count" in df.columns
    assert "signal_rss_crypto_title_sentiment" in df.columns

    # FinBERT columns
    assert "signal_rss_crypto_sentiment_finbert_mean" in df.columns
    assert "signal_rss_crypto_sentiment_finbert_std" in df.columns
    assert "signal_rss_crypto_positive_ratio" in df.columns
    assert "signal_rss_crypto_negative_ratio" in df.columns
    assert "signal_rss_crypto_neg_minus_pos" in df.columns
    assert "signal_rss_crypto_sentiment_defined" in df.columns

    # 3 days: Jan 10, 11, 12
    assert df.shape[0] == 3

    # Sorted ascending
    ts_list = df["ts_utc"].to_list()
    assert ts_list == sorted(ts_list)

    # Jan 10: 2 articles, 1 BTC mention
    row0 = df.row(0, named=True)
    assert row0["signal_rss_crypto_article_count"] == 2
    assert row0["signal_rss_crypto_btc_mention_count"] == 1


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_aggregate_empty_entries_returns_zero_filled(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    start = datetime(2022, 1, 1, tzinfo=UTC)
    end = datetime(2022, 1, 3, tzinfo=UTC)

    df = aggregate_crypto_entries([], start=start, end=end)

    assert df.shape[0] == 3
    assert all(v == 0 for v in df["signal_rss_crypto_article_count"].to_list())
    assert all(v == 0 for v in df["signal_rss_crypto_btc_mention_count"].to_list())
    # Fix 3: sentiment is NaN (not 0) when no articles
    assert all(v is None for v in df["signal_rss_crypto_title_sentiment"].to_list())
    # sentiment_defined flag = 0 for days without articles
    assert all(v == 0 for v in df["signal_rss_crypto_sentiment_defined"].to_list())


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_rss_crypto_transforms_columns_exist(mock_load: MagicMock) -> None:
    """Verify all derived columns are present after transforms."""
    mock_load.return_value = _make_mock_pipeline()

    payload = (FIXTURES / "rss_crypto_sample.xml").read_text()
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_crypto_feed(payload, start=start, end=end)
    df = aggregate_crypto_entries(entries, start=start, end=end)
    df = add_rss_crypto_transforms(df)

    expected = [
        "signal_rss_crypto_article_count_delta",
        "signal_rss_crypto_article_count_zscore_7d",
        "signal_rss_crypto_article_count_delta_log1p",
        "signal_rss_crypto_sentiment_delta",
        "signal_rss_crypto_btc_mention_delta",
        "signal_rss_crypto_btc_mention_count_delta_log1p",
        "signal_rss_crypto_neg_sentiment_flag",
        "signal_rss_crypto_sentiment_defined",
        "asof_utc",
    ]
    for col in expected:
        assert col in df.columns, f"Missing column: {col}"

    # Row count unchanged
    assert df.shape[0] == 3


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_rss_crypto_neg_sentiment_flag_values(mock_load: MagicMock) -> None:
    """neg_sentiment_flag should be 0 or 1."""
    mock_load.return_value = _make_mock_pipeline()

    payload = (FIXTURES / "rss_crypto_sample.xml").read_text()
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_crypto_feed(payload, start=start, end=end)
    df = aggregate_crypto_entries(entries, start=start, end=end)
    df = add_rss_crypto_transforms(df)

    flags = df["signal_rss_crypto_neg_sentiment_flag"].to_list()
    assert all(v in (0, 1) for v in flags)


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_rss_crypto_sentiment_nan_when_no_articles(mock_load: MagicMock) -> None:
    """Sentiment should be NaN when article_count = 0."""
    mock_load.return_value = _make_mock_pipeline()

    start = datetime(2022, 1, 1, tzinfo=UTC)
    end = datetime(2022, 1, 3, tzinfo=UTC)

    df = aggregate_crypto_entries([], start=start, end=end)
    df = add_rss_crypto_transforms(df)

    # All days have 0 articles → sentiment should be null
    sentiments = df["signal_rss_crypto_title_sentiment"].to_list()
    assert all(v is None for v in sentiments)
    # sentiment_defined should be 0 everywhere
    defined = df["signal_rss_crypto_sentiment_defined"].to_list()
    assert all(v == 0 for v in defined)
    # neg_sentiment_flag should be 0 (not flagged) when sentiment is null
    flags = df["signal_rss_crypto_neg_sentiment_flag"].to_list()
    assert all(v == 0 for v in flags)


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_rss_crypto_asof_utc_is_next_day(mock_load: MagicMock) -> None:
    """asof_utc should be ts_utc + 1 day."""
    mock_load.return_value = _make_mock_pipeline()

    payload = (FIXTURES / "rss_crypto_sample.xml").read_text()
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_crypto_feed(payload, start=start, end=end)
    df = aggregate_crypto_entries(entries, start=start, end=end)
    df = add_rss_crypto_transforms(df)

    for i in range(df.shape[0]):
        assert df["asof_utc"][i] == df["ts_utc"][i] + timedelta(days=1)


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_rss_crypto_finbert_columns_have_values(mock_load: MagicMock) -> None:
    """FinBERT columns should have non-null values when articles exist."""
    mock_load.return_value = _make_mock_pipeline()

    payload = (FIXTURES / "rss_crypto_sample.xml").read_text()
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 11, 23, 59, 59, tzinfo=UTC)

    entries = parse_crypto_feed(payload, start=start, end=end)
    df = aggregate_crypto_entries(entries, start=start, end=end)

    # Jan 10: 2 articles, Jan 11: 2 articles → finbert columns should be non-null
    for col in ["signal_rss_crypto_sentiment_finbert_mean", "signal_rss_crypto_sentiment_finbert_std"]:
        vals = df[col].to_list()
        assert all(v is not None for v in vals), f"{col} has None values"

    # Ratios should be between 0 and 1
    for col in ["signal_rss_crypto_positive_ratio", "signal_rss_crypto_negative_ratio"]:
        vals = df[col].to_list()
        assert all(0.0 <= v <= 1.0 for v in vals), f"{col} out of range"
