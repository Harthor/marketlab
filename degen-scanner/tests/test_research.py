"""Tests for research: lag scan, event study, rank IC."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl

from degen_scanner.research.event_study import run_event_study


def _make_features_and_targets(n: int = 100) -> tuple[pl.DataFrame, pl.DataFrame]:
    base = datetime(2026, 2, 1, tzinfo=UTC)
    assets = ["solana:T1", "solana:T2"]

    feat_rows = []
    tgt_rows = []
    for asset in assets:
        for i in range(n):
            ts = base + timedelta(hours=i)
            signal = 1.0 if i % 10 == 0 else 0.0  # spike every 10 hours
            feat_rows.append({
                "ts_utc": ts,
                "asset_uid": asset,
                "signal_spike": signal,
                "volume_accel": 1.0 + (i % 5) * 0.5,
            })
            tgt_rows.append({
                "ts_utc": ts,
                "asset_uid": asset,
                "returns_1h": 0.02 if signal > 0 else -0.001,
                "returns_4h": 0.05 if signal > 0 else 0.001,
            })

    return pl.DataFrame(feat_rows), pl.DataFrame(tgt_rows)


class TestEventStudy:
    def test_positive_signal_uplift(self):
        features, targets = _make_features_and_targets()
        result = run_event_study(
            features, targets,
            trigger_col="signal_spike",
            trigger_threshold=0.5,
            trigger_op="gt",
        )
        assert result["event_count"] > 0
        # Signal rows have returns_1h=0.02, control has -0.001
        assert result["returns_1h_mean"] > result["returns_1h_control_mean"]
        assert result["returns_1h_uplift_pp"] > 0

    def test_no_events(self):
        features, targets = _make_features_and_targets()
        result = run_event_study(
            features, targets,
            trigger_col="signal_spike",
            trigger_threshold=999,  # nothing triggers
            trigger_op="gt",
        )
        assert result["event_count"] == 0

    def test_missing_column(self):
        features, targets = _make_features_and_targets()
        result = run_event_study(
            features, targets,
            trigger_col="nonexistent",
            trigger_threshold=0.5,
        )
        assert result["event_count"] == 0
        assert "error" in result
