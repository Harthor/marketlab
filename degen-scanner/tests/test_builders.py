"""Tests for builders: market bars, features, targets."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl

from degen_scanner.builders.features import build_feature_table
from degen_scanner.builders.targets import build_targets


def _make_bars(n_hours: int = 48, n_assets: int = 2) -> pl.DataFrame:
    """Create synthetic market bars for testing."""
    rows = []
    base_time = datetime(2026, 2, 1, tzinfo=UTC)
    symbols = [f"solana:Token{i}" for i in range(n_assets)]

    for asset in symbols:
        for h in range(n_hours):
            ts = base_time + timedelta(hours=h)
            price = 1.0 + h * 0.01 + (hash(asset) % 10) * 0.001
            rows.append({
                "ts_utc": ts,
                "asset_uid": asset,
                "open": price * 0.99,
                "high": price * 1.02,
                "low": price * 0.97,
                "close": price,
                "volume_usd": 100_000 + h * 1000,
            })

    return pl.DataFrame(rows)


class TestBuildTargets:
    def test_default_horizons(self):
        bars = _make_bars(n_hours=48, n_assets=2)
        targets = build_targets(bars)
        assert "returns_1h" in targets.columns
        assert "returns_4h" in targets.columns
        assert "returns_24h" in targets.columns
        assert len(targets) == len(bars)

    def test_custom_horizons(self):
        bars = _make_bars()
        targets = build_targets(bars, horizons=[1, 2])
        assert "returns_1h" in targets.columns
        assert "returns_2h" in targets.columns
        assert "returns_24h" not in targets.columns

    def test_forward_looking(self):
        bars = _make_bars(n_hours=10, n_assets=1)
        targets = build_targets(bars, horizons=[1])
        # Last row should have null returns_1h (no future data)
        last_row = targets.filter(pl.col("asset_uid") == "solana:Token0").sort("ts_utc").tail(1)
        assert last_row["returns_1h"][0] is None

    def test_empty_input(self):
        empty = pl.DataFrame(schema={
            "ts_utc": pl.Datetime("us", "UTC"),
            "asset_uid": pl.Utf8,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume_usd": pl.Float64,
        })
        targets = build_targets(empty)
        assert targets.is_empty()


class TestBuildFeatures:
    def test_price_derived_features(self):
        bars = _make_bars(n_hours=48, n_assets=2)
        features = build_feature_table(bars)
        assert "log_return_1h" in features.columns
        assert "vol_accel_1h" in features.columns
        assert "range_pct_1h" in features.columns
        assert len(features) == len(bars)

    def test_empty_bars(self):
        empty = pl.DataFrame(schema={
            "ts_utc": pl.Datetime("us", "UTC"),
            "asset_uid": pl.Utf8,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume_usd": pl.Float64,
        })
        features = build_feature_table(empty)
        assert features.is_empty()
