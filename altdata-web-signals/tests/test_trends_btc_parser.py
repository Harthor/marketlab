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
        assert "period_start_utc" in df.columns
        assert "period_end_utc" in df.columns
        assert df.shape[0] == 5
        # Sorted ascending
        ts_list = df["ts_utc"].to_list()
        assert ts_list == sorted(ts_list)
        # ts_utc should equal period_end_utc (re-anchored)
        assert df["ts_utc"].to_list() == df["period_end_utc"].to_list()


def test_parse_trends_payload_signal_column_names() -> None:
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    frames = parse_trends_payload(raw)

    assert "signal_trends_bitcoin" in frames["bitcoin"].columns
    assert "signal_trends_buy_bitcoin" in frames["buy bitcoin"].columns
    assert "signal_trends_bitcoin_crash" in frames["bitcoin crash"].columns
    assert "signal_trends_crypto" in frames["crypto"].columns


def test_parse_trends_payload_date_filter() -> None:
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    # ts_utc is now period_end (+6 days from raw date)
    # Raw dates: 01-02,09,16,23,30 → period_end: 01-08,15,22,29,02-05
    start = datetime(2022, 1, 14, tzinfo=UTC)
    end = datetime(2022, 1, 30, tzinfo=UTC)
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


def test_trends_transforms_asof_utc() -> None:
    """asof_utc should be ts_utc + 1 day on all keyword frames."""
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    frames = parse_trends_payload(raw)
    frames = add_trends_transforms(frames)

    from datetime import timedelta

    for kw in ["bitcoin", "buy bitcoin", "bitcoin crash", "crypto", "__fear_ratio"]:
        df = frames[kw]
        assert "asof_utc" in df.columns, f"Missing asof_utc in '{kw}'"
        for i in range(df.shape[0]):
            assert df["asof_utc"][i] == df["ts_utc"][i] + timedelta(days=1)


def test_trends_period_bounds_consistent() -> None:
    """period_end = period_start + 6 days, ts_utc = period_end."""
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    frames = parse_trends_payload(raw)

    from datetime import timedelta

    for df in frames.values():
        for i in range(df.shape[0]):
            start = df["period_start_utc"][i]
            end = df["period_end_utc"][i]
            assert end == start + timedelta(days=6)
            assert df["ts_utc"][i] == end


def test_trends_fear_ratio_has_period_columns() -> None:
    """fear_ratio frame should also carry period metadata."""
    raw = json.loads((FIXTURES / "trends_btc_sample.json").read_text())
    frames = parse_trends_payload(raw)
    frames = add_trends_transforms(frames)

    fr_df = frames["__fear_ratio"]
    assert "period_start_utc" in fr_df.columns
    assert "period_end_utc" in fr_df.columns
    assert "asof_utc" in fr_df.columns
