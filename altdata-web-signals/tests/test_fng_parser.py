"""Tests for Fear & Greed Index parser."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from altdata_web_signals.fetchers.fear_greed import parse_fng_payload

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_fng_payload_basic() -> None:
    raw = json.loads((FIXTURES / "fng_sample.json").read_text())
    df = parse_fng_payload(raw)

    assert df.shape[0] == 5
    assert "ts_utc" in df.columns
    assert "signal_fng_value" in df.columns
    assert "signal_fng_classification" in df.columns

    # Should be sorted ascending
    ts_list = df["ts_utc"].to_list()
    assert ts_list == sorted(ts_list)

    # Value range check
    values = df["signal_fng_value"].to_list()
    assert all(0 <= v <= 100 for v in values)


def test_parse_fng_payload_date_filter() -> None:
    raw = json.loads((FIXTURES / "fng_sample.json").read_text())
    start = datetime(2022, 1, 25, tzinfo=UTC)
    end = datetime(2022, 1, 27, tzinfo=UTC)
    df = parse_fng_payload(raw, start=start, end=end)

    assert df.shape[0] > 0
    ts_list = df["ts_utc"].to_list()
    for ts in ts_list:
        assert ts >= start
        assert ts <= end


def test_parse_fng_payload_empty_data_raises() -> None:
    try:
        parse_fng_payload({"data": []})
        raise AssertionError("Should have raised ValueError")  # noqa: TRY301
    except ValueError as exc:
        assert "no 'data' entries" in str(exc)


def test_parse_fng_payload_custom_prefix() -> None:
    raw = json.loads((FIXTURES / "fng_sample.json").read_text())
    df = parse_fng_payload(raw, signal_prefix="signal_custom")

    assert "signal_custom_value" in df.columns
    assert "signal_custom_classification" in df.columns
