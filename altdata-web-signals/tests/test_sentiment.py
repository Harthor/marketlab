"""Tests for FinBERT sentiment analysis utilities."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


def _make_mock_pipeline() -> MagicMock:
    """Create a mock FinBERT pipeline that returns deterministic results."""
    mock = MagicMock()

    def side_effect(texts: list[str], batch_size: int = 32) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for text in texts:
            lower = text.lower()
            if "surge" in lower or "hit" in lower or "grow" in lower:
                results.append({"label": "positive", "score": 0.85})
            elif "crash" in lower or "ban" in lower or "concern" in lower:
                results.append({"label": "negative", "score": 0.78})
            else:
                results.append({"label": "neutral", "score": 0.60})
        return results

    mock.side_effect = side_effect
    return mock


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_get_finbert_sentiment_basic(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    from altdata_web_signals.sentiment import get_finbert_sentiment

    results = get_finbert_sentiment(["Bitcoin surges past 50k", "Market crashes hard"])
    assert len(results) == 2
    assert results[0]["label"] == "positive"
    assert results[1]["label"] == "negative"


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_get_finbert_sentiment_empty_input(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    from altdata_web_signals.sentiment import get_finbert_sentiment

    results = get_finbert_sentiment(["", "  ", "Bitcoin surges"])
    assert len(results) == 3
    # Empty/whitespace → neutral with score 0.0
    assert results[0] == {"label": "neutral", "score": 0.0}
    assert results[1] == {"label": "neutral", "score": 0.0}
    # Valid text → pipeline result
    assert results[2]["label"] == "positive"


def test_finbert_to_numeric_positive() -> None:
    from altdata_web_signals.sentiment import finbert_to_numeric

    assert finbert_to_numeric({"label": "positive", "score": 0.9}) == 0.9


def test_finbert_to_numeric_negative() -> None:
    from altdata_web_signals.sentiment import finbert_to_numeric

    assert finbert_to_numeric({"label": "negative", "score": 0.8}) == -0.8


def test_finbert_to_numeric_neutral() -> None:
    from altdata_web_signals.sentiment import finbert_to_numeric

    assert finbert_to_numeric({"label": "neutral", "score": 0.7}) == 0.0


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_finbert_batch_numeric(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    from altdata_web_signals.sentiment import finbert_batch_numeric

    scores = finbert_batch_numeric(["Bitcoin surges", "Market crashes", "Just a normal day"])
    assert len(scores) == 3
    assert scores[0] > 0  # positive
    assert scores[1] < 0  # negative
    assert scores[2] == 0.0  # neutral


@patch("altdata_web_signals.sentiment._load_pipeline")
def test_finbert_batch_stats_with_texts(mock_load: MagicMock) -> None:
    mock_load.return_value = _make_mock_pipeline()

    from altdata_web_signals.sentiment import finbert_batch_stats

    stats = finbert_batch_stats(["Bitcoin surges", "Market crashes", "Normal day"])
    assert stats["mean"] is not None
    assert stats["std"] is not None
    assert stats["positive_ratio"] is not None
    assert stats["negative_ratio"] is not None
    assert stats["neg_minus_pos"] is not None

    # 1 positive, 1 negative, 1 neutral out of 3
    assert abs(stats["positive_ratio"] - 1 / 3) < 1e-6
    assert abs(stats["negative_ratio"] - 1 / 3) < 1e-6


def test_finbert_batch_stats_empty() -> None:
    from altdata_web_signals.sentiment import finbert_batch_stats

    stats = finbert_batch_stats([])
    assert stats["mean"] is None
    assert stats["std"] is None
    assert stats["positive_ratio"] is None
    assert stats["negative_ratio"] is None
    assert stats["neg_minus_pos"] is None


def test_finbert_batch_stats_whitespace_only() -> None:
    from altdata_web_signals.sentiment import finbert_batch_stats

    stats = finbert_batch_stats(["", "   ", "  "])
    assert stats["mean"] is None
    assert stats["std"] is None
