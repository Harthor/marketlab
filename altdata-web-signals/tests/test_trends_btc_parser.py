"""Tests for Google Trends BTC parser and transforms (offline, no pytrends needed)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from altdata_web_signals.fetchers.trends_btc import (
    add_trends_transforms,
    parse_trends_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_trends_payload_basic() -> None:
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    frames = parse_trends_payload(raw)

    assert len(frames) == 4
    for kw in ["bitcoin", "buy bitcoin", "bitcoin crash", "crypto"]:
        assert kw in frames
        df = frames[kw]
        assert "ts_utc" in df.columns
        assert df.shape[0] == 5
        # Sorted ascending
        ts_list = df["ts_utc"].to_list()
        assert ts_list == sorted(ts_list)


def test_parse_trends_payload_signal_column_names() -> None:
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    frames = parse_trends_payload(raw)

    assert "signal_trends_bitcoin" in frames["bitcoin"].columns
    assert "signal_trends_buy_bitcoin" in frames["buy bitcoin"].columns
    assert "signal_trends_bitcoin_crash" in frames["bitcoin crash"].columns
    assert "signal_trends_crypto" in frames["crypto"].columns


def test_parse_trends_payload_date_filter() -> None:
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    start = datetime(2022, 1, 10, tzinfo=UTC)
    end = datetime(2022, 1, 25, tzinfo=UTC)
    frames = parse_trends_payload(raw, start=start, end=end)

    for df in frames.values():
        ts_list = df["ts_utc"].to_list()
        for ts in ts_list:
            assert ts >= start
            assert ts <= end


def test_parse_trends_payload_values_in_range() -> None:
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    frames = parse_trends_payload(raw)

    for df in frames.values():
        signal_cols = [c for c in df.columns if c.startswith("signal_")]
        for col in signal_cols:
            values = df[col].to_list()
            assert all(0 <= v <= 100 for v in values)


def test_trends_transforms_delta_pct_columns() -> None:
    """Each keyword should get _delta and _pct_change columns."""
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    frames = parse_trends_payload(raw)
    frames = add_trends_transforms(frames)

    for kw in ["bitcoin", "buy bitcoin", "bitcoin crash", "crypto"]:
        df = frames[kw]
        signal_cols = [c for c in df.columns if c.startswith("signal_")]
        base_found = any(c.endswith("_delta") for c in signal_cols)
        pct_found = any(c.endswith("_pct_change") for c in signal_cols)
        assert base_found, f"Missing _delta column for '{kw}'"
        assert pct_found, f"Missing _pct_change column for '{kw}'"


def test_trends_transforms_fear_ratio() -> None:
    """fear_ratio = bitcoin_crash / (bitcoin + 1) should be computed."""
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    frames = parse_trends_payload(raw)
    frames = add_trends_transforms(frames)

    assert "__fear_ratio" in frames
    fr_df = frames["__fear_ratio"]
    assert "signal_trends_fear_ratio" in fr_df.columns
    assert fr_df.shape[0] == 5

    # fear_ratio should be non-negative
    values = fr_df["signal_trends_fear_ratio"].to_list()
    assert all(v >= 0 for v in values)


def test_trends_transforms_pct_change_winsorized() -> None:
    """pct_change should be winsorized to [-1, 1]."""
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    frames = parse_trends_payload(raw)
    frames = add_trends_transforms(frames)

    for kw in ["bitcoin", "buy bitcoin", "bitcoin crash", "crypto"]:
        df = frames[kw]
        pct_cols = [c for c in df.columns if c.endswith("_pct_change")]
        for col in pct_cols:
            vals = df[col].drop_nulls().to_list()
            assert all(-1.0 <= v <= 1.0 for v in vals)
