"""Build hourly feature table for degen research."""
from __future__ import annotations

import polars as pl


def build_feature_table(
    market_bars: pl.DataFrame,
    social_features: pl.DataFrame | None = None,
    holder_features: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Combine market bars with social and holder features into a single feature table.

    All inputs should have ts_utc and asset_uid columns.
    Market bars provide: price-derived features (returns, vol accel, etc.)
    Social features provide: reddit mentions, trending rank, etc.
    Holder features provide: concentration, security, etc.
    """
    if market_bars.is_empty():
        return market_bars

    # Price-derived features
    features = market_bars.sort(["asset_uid", "ts_utc"]).with_columns([
        # Log return
        (pl.col("close") / pl.col("close").shift(1).over("asset_uid")).log().alias("log_return_1h"),
        # Volume acceleration: vol / rolling mean 24h
        (
            pl.col("volume_usd")
            / pl.col("volume_usd").rolling_mean(window_size=24).over("asset_uid")
        ).alias("vol_accel_1h"),
        # Price range / close (volatility proxy)
        ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("range_pct_1h"),
    ])

    # Join social features if available
    if social_features is not None and not social_features.is_empty():
        features = features.join(
            social_features,
            on=["ts_utc", "asset_uid"],
            how="left",
        )

    # Join holder features if available
    if holder_features is not None and not holder_features.is_empty():
        features = features.join(
            holder_features,
            on=["ts_utc", "asset_uid"],
            how="left",
        )

    return features
