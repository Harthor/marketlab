"""Tests for Fear & Greed Index parser and transforms."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from altdata_web_signals.fetchers.fear_greed import add_fng_transforms, parse_fng_payload

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


def test_fng_transforms_columns_exist() -> None:
    """Verify all derived columns are present after transforms."""
    raw = json.loads((FIXTURES / "fng_sample.json").read_text())
    df = parse_fng_payload(raw)
    df = add_fng_transforms(df)

    expected = [
        "signal_fng_value_delta",
        "signal_fng_value_pct_change",
        "signal_fng_value_zscore_30d",
        "signal_fng_regime",
        "asof_utc",
    ]
    for col in expected:
        assert col in df.columns, f"Missing column: {col}"

    # Row count unchanged
    assert df.shape[0] == 5


def test_fng_transforms_regime_values() -> None:
    """Regime column should only contain valid bucket labels."""
    raw = json.loads((FIXTURES / "fng_sample.json").read_text())
    df = parse_fng_payload(raw)
    df = add_fng_transforms(df)

    valid = {"extreme_fear", "fear", "neutral", "greed", "extreme_greed"}
    regimes = set(df["signal_fng_regime"].to_list())
    assert regimes <= valid


def test_fng_transforms_pct_change_winsorized() -> None:
    """pct_change should be winsorized to [-1, 1]."""
    raw = json.loads((FIXTURES / "fng_sample.json").read_text())
    df = parse_fng_payload(raw)
    df = add_fng_transforms(df)

    pct = df["signal_fng_value_pct_change"].drop_nulls().to_list()
    assert all(-1.0 <= v <= 1.0 for v in pct)


def test_fng_transforms_first_row_null() -> None:
    """Delta and pct_change should be null for the first row."""
    raw = json.loads((FIXTURES / "fng_sample.json").read_text())
    df = parse_fng_payload(raw)
    df = add_fng_transforms(df)

    assert df["signal_fng_value_delta"][0] is None
    assert df["signal_fng_value_pct_change"][0] is None


def test_fng_asof_utc_is_next_day() -> None:
    """asof_utc should be ts_utc + 1 day."""
    raw = json.loads((FIXTURES / "fng_sample.json").read_text())
    df = parse_fng_payload(raw)
    df = add_fng_transforms(df)

    from datetime import timedelta

    for i in range(df.shape[0]):
        assert df["asof_utc"][i] == df["ts_utc"][i] + timedelta(days=1)


def test_fng_extreme_fear_flag() -> None:
    """is_extreme_fear should be 1 when value <= 25."""
    raw = json.loads((FIXTURES / "fng_sample.json").read_text())
    df = parse_fng_payload(raw)
    df = add_fng_transforms(df)

    assert "signal_fng_is_extreme_fear" in df.columns
    values = df["signal_fng_value"].to_list()
    flags = df["signal_fng_is_extreme_fear"].to_list()
    for val, flag in zip(values, flags, strict=True):
        expected = 1 if val <= 25 else 0
        assert flag == expected, f"value={val} expected is_extreme_fear={expected}, got {flag}"


def test_fng_extreme_greed_flag() -> None:
    """is_extreme_greed should be 1 when value >= 75."""
    raw = json.loads((FIXTURES / "fng_sample.json").read_text())
    df = parse_fng_payload(raw)
    df = add_fng_transforms(df)

    assert "signal_fng_is_extreme_greed" in df.columns
    values = df["signal_fng_value"].to_list()
    flags = df["signal_fng_is_extreme_greed"].to_list()
    for val, flag in zip(values, flags, strict=True):
        expected = 1 if val >= 75 else 0
        assert flag == expected, f"value={val} expected is_extreme_greed={expected}, got {flag}"


def test_fng_extremeness() -> None:
    """extremeness should be abs(value - 50)."""
    raw = json.loads((FIXTURES / "fng_sample.json").read_text())
    df = parse_fng_payload(raw)
    df = add_fng_transforms(df)

    assert "signal_fng_extremeness" in df.columns
    values = df["signal_fng_value"].to_list()
    extremeness = df["signal_fng_extremeness"].to_list()
    for val, ext in zip(values, extremeness, strict=True):
        expected = abs(float(val) - 50.0)
        assert abs(ext - expected) < 1e-6, f"value={val} expected extremeness={expected}, got {ext}"
