from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import polars as pl

from altdata_web_signals.fetchers.wikipedia import parse_wikipedia_payload


def test_parse_wikipedia_payload_builds_daily_signal_series() -> None:
    fixture = json.loads(Path("tests/fixtures/wikipedia_sample.json").read_text(encoding="utf-8"))
    frame = parse_wikipedia_payload(
        payload=fixture,
        topic="Bitcoin",
        start=datetime(2022, 1, 1, tzinfo=timezone.utc).date(),
        end=datetime(2022, 1, 3, tzinfo=timezone.utc).date(),
    )

    assert frame.shape == (3, 2)
    assert frame.columns == ["ts_utc", "signal_wiki_bitcoin"]
    assert frame.filter(pl.col("signal_wiki_bitcoin") > 0).height == 2
