from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl

from marketlab_core.timeseries import align


def test_random_timestamp_alignment_has_expected_grid_size() -> None:
    rng = np.random.default_rng(42)
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    offsets_a = sorted(rng.integers(0, 3600, size=200))
    offsets_b = sorted(rng.integers(0, 3600, size=120))

    a = pl.DataFrame(
        {
            "timestamp": [base + timedelta(seconds=int(v)) for v in offsets_a],
            "value": rng.standard_normal(len(offsets_a)),
        }
    )
    b = pl.DataFrame(
        {
            "timestamp": [base + timedelta(seconds=int(v)) for v in offsets_b],
            "value": rng.standard_normal(len(offsets_b)),
        }
    )

    out = align([a, b], how="outer", freq="1m", method="ffill")
    expected_size = 60
    assert out.height == expected_size
    assert out["timestamp"].is_sorted()
