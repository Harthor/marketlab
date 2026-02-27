from pathlib import Path

import numpy as np
import polars as pl
import pandas as pd

from correngine.config import RunConfig
from correngine.runner import run_correlation


def test_engine_detects_known_3_day_lag(tmp_path: Path) -> None:
    rng = np.random.default_rng(42)
    n = 600
    timestamps = pl.Series("ts_utc", pd.date_range("2020-01-01", periods=n, freq="1d"))
    base_signal = rng.normal(0.0, 1.0, size=n)
    feature_lead3 = base_signal

    noise = rng.normal(0.0, 1.0, size=n)
    returns = np.empty(n, dtype=float)
    returns[:3] = rng.normal(0.0, 1.0, size=3)
    returns[3:] = 0.85 * feature_lead3[:-3] + 0.08 * noise[3:]
    feature_noise = rng.normal(0.0, 1.0, size=n)
    feature_lag3 = np.empty(n, dtype=float)
    feature_lag3[:3] = rng.normal(0.0, 1.0, size=3)
    feature_lag3[3:] = 0.85 * returns[:-3] + 0.08 * rng.normal(0.0, 1.0, size=n - 3)

    df = pl.DataFrame(
        {
            "ts_utc": timestamps,
            "returns_1d": returns,
            "feature_lead3": feature_lead3,
            "feature_noise": feature_noise,
            "feature_lag3": feature_lag3,
        }
    )
    data_path = tmp_path / "synthetic.parquet"
    df.write_parquet(data_path)

    cfg = RunConfig(
        dataset=str(data_path),
        target="returns_1d",
        timestamp="ts_utc",
        max_lag=10,
        windows=(5, 10),
        seed=123,
        bootstrap=0,
        top=20,
        output_root=str(tmp_path / "reports"),
    )

    result = run_correlation(cfg)
    feature_row = result.lag_summary.filter(pl.col("feature") == "feature_lead3").to_dicts()[0]
    assert int(feature_row["best_lag"]) == 3
    assert abs(float(feature_row["best_corr"])) > 0.75
    assert feature_row["lead_lag"] == "feature_leads"
    noise_row = result.lag_summary.filter(pl.col("feature") == "feature_noise").to_dicts()[0]
    assert abs(float(noise_row["best_corr"])) < abs(float(feature_row["best_corr"]))

    lag3_row = result.lag_summary.filter(pl.col("feature") == "feature_lag3").to_dicts()[0]
    assert int(lag3_row["best_lag"]) == -3
    assert lag3_row["lead_lag"] == "target_leads"
    assert abs(float(lag3_row["best_corr"])) > 0.75
