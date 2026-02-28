"""Tests for Reddit fetcher (parse + aggregate + transforms)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from altdata_web_signals.fetchers.reddit import (
    add_reddit_transforms,
    aggregate_reddit_entries,
    parse_reddit_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _make_mock_pipeline() -> MagicMock:
    """Mock FinBERT pipeline returning deterministic results."""
    mock = MagicMock()

    def side_effect(texts: list[str], batch_size: int = 32) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for text in texts:
            lower = text.lower()
            if "surge" in lower or "hit" in lower or "grow" in lower:
                results.append({"label": "positive", "score": 0.85})
            elif "crash" in lower or "ban" in lower or "concern" in lower or "uncertainty" in lower:
                results.append({"label": "negative", "score": 0.78})
            else:
                results.append({"label": "neutral", "score": 0.60})
        return results

    mock.side_effect = side_effect
    return mock


def test_parse_reddit_payload_extracts_entries() -> None:
    raw = json.loads((FIXTURES / "reddit_sample.json").read_text())
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, 23, 59, 59, tzinfo=UTC)

    entries = parse_reddit_payload(raw, start=start, end=end)

    assert len(entries) == 5
    # Check BTC detection
    btc_entries = [e for e in entries if e["has_btc"]]
    assert len(btc_entries) == 3  # "Bitcoin hits...", "BTC whale...", "Bitcoin mining..."

    for entry in entries:
        assert "date" in entry
        assert "title" in entry
        assert "score" in entry
        assert "num_comments" in entry
        assert "has_btc" in entry


def test_parse_reddit_payload_date_filter() -> None:
    raw = json.loads((FIXTURES / "reddit_sample.json").read_text())
    # Only Jan 10 entries (first two posts: timestamps 1641808800, 1641812400)
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 10, 23, 59, 59, tzinfo=UTC)

    entries = parse_reddit_payload(raw, start=start, end=end)
    assert len(entries) == 2


def test_parse_reddit_payload_empty() -> None:
    payload: dict[str, Any] = {"data": {"children": []}}
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_reddit_payload(payload, start=start, end=end)
    assert entries == []


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_aggregate_reddit_entries_columns(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    raw = json.loads((FIXTURES / "reddit_sample.json").read_text())
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_reddit_payload(raw, start=start, end=end)
    df = aggregate_reddit_entries(entries, start=start, end=end)

    expected_cols = [
        "ts_utc",
        "signal_reddit_post_count",
        "signal_reddit_comment_count",
        "signal_reddit_score_mean",
        "signal_reddit_score_sum",
        "signal_reddit_title_sentiment",
        "signal_reddit_btc_mention_count",
        "signal_reddit_sentiment_finbert_mean",
        "signal_reddit_sentiment_finbert_std",
        "signal_reddit_positive_ratio",
        "signal_reddit_negative_ratio",
        "signal_reddit_neg_minus_pos",
        "signal_reddit_sentiment_defined",
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing column: {col}"

    # 3 days: Jan 10, 11, 12
    assert df.shape[0] == 3


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_aggregate_reddit_entries_day_counts(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    raw = json.loads((FIXTURES / "reddit_sample.json").read_text())
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, 23, 59, 59, tzinfo=UTC)

    entries = parse_reddit_payload(raw, start=start, end=end)
    df = aggregate_reddit_entries(entries, start=start, end=end)

    # Jan 10: 2 posts, Jan 11: 2 posts, Jan 12: 1 post
    counts = df["signal_reddit_post_count"].to_list()
    assert counts == [2, 2, 1]

    # Jan 10: comments = 340 + 150 = 490
    assert df["signal_reddit_comment_count"][0] == 490


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_aggregate_reddit_entries_score_aggregation(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    raw = json.loads((FIXTURES / "reddit_sample.json").read_text())
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_reddit_payload(raw, start=start, end=end)
    df = aggregate_reddit_entries(entries, start=start, end=end)

    # Jan 10: scores 1520 + 890 = 2410
    assert df["signal_reddit_score_sum"][0] == 2410
    assert abs(df["signal_reddit_score_mean"][0] - 1205.0) < 1e-6


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_aggregate_empty_reddit_entries(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    start = datetime(2022, 1, 1, tzinfo=UTC)
    end = datetime(2022, 1, 3, tzinfo=UTC)

    df = aggregate_reddit_entries([], start=start, end=end)

    assert df.shape[0] == 3
    assert all(v == 0 for v in df["signal_reddit_post_count"].to_list())
    assert all(v is None for v in df["signal_reddit_title_sentiment"].to_list())
    assert all(v == 0 for v in df["signal_reddit_sentiment_defined"].to_list())


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_reddit_transforms_columns_exist(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    raw = json.loads((FIXTURES / "reddit_sample.json").read_text())
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_reddit_payload(raw, start=start, end=end)
    df = aggregate_reddit_entries(entries, start=start, end=end)
    df = add_reddit_transforms(df)

    expected = [
        "signal_reddit_post_count_delta",
        "signal_reddit_post_count_zscore_7d",
        "signal_reddit_post_count_delta_log1p",
        "signal_reddit_comment_count_delta_log1p",
        "signal_reddit_score_sum_delta_log1p",
        "signal_reddit_sentiment_delta",
        "signal_reddit_btc_mention_delta",
        "signal_reddit_neg_sentiment_flag",
        "asof_utc",
    ]
    for col in expected:
        assert col in df.columns, f"Missing column: {col}"


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_reddit_asof_utc_is_next_day(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    raw = json.loads((FIXTURES / "reddit_sample.json").read_text())
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_reddit_payload(raw, start=start, end=end)
    df = aggregate_reddit_entries(entries, start=start, end=end)
    df = add_reddit_transforms(df)

    for i in range(df.shape[0]):
        assert df["asof_utc"][i] == df["ts_utc"][i] + timedelta(days=1)


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_reddit_neg_sentiment_flag_values(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    raw = json.loads((FIXTURES / "reddit_sample.json").read_text())
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 12, tzinfo=UTC)

    entries = parse_reddit_payload(raw, start=start, end=end)
    df = aggregate_reddit_entries(entries, start=start, end=end)
    df = add_reddit_transforms(df)

    flags = df["signal_reddit_neg_sentiment_flag"].to_list()
    assert all(v in (0, 1) for v in flags)
