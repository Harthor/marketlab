from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from altdata_web_signals.fetchers.rss import parse_rss_counts


def test_parse_rss_counts_keyword_counts_per_day() -> None:
    xml = Path("tests/fixtures/rss_sample.xml").read_text(encoding="utf-8")
    frames = parse_rss_counts(
        feed_payload=xml,
        keywords=["bitcoin", "apple", "nvidia"],
        start=datetime(2021, 1, 1, tzinfo=UTC),
        end=datetime(2021, 1, 3, tzinfo=UTC),
    )

    assert set(frames) == {"bitcoin", "apple", "nvidia"}
    assert frames["bitcoin"]["signal_rss_bitcoin"].to_list() == [1, 0, 0]
    assert frames["apple"]["signal_rss_apple"].to_list() == [0, 1, 0]
    assert frames["nvidia"]["signal_rss_nvidia"].to_list() == [0, 1, 0]
