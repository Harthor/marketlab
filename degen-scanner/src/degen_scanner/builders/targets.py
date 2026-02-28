"""Build return targets for degen research."""
from __future__ import annotations

import polars as pl


def build_targets(
    market_bars: pl.DataFrame,
    horizons: list[int] | None = None,
) -> pl.DataFrame:
    """Build forward-looking return targets from market bars.

    Args:
        market_bars: DataFrame with ts_utc, asset_uid, close columns.
        horizons: List of forward periods in hours. Default: [1, 4, 24].

    Returns:
        DataFrame with ts_utc, asset_uid, and returns_{N}h columns.
    """
    if horizons is None:
        horizons = [1, 4, 24]

    if market_bars.is_empty():
        schema = {"ts_utc": pl.Datetime("us", "UTC"), "asset_uid": pl.Utf8}
        for h in horizons:
            schema[f"returns_{h}h"] = pl.Float64
        return pl.DataFrame(schema=schema)

    df = market_bars.sort(["asset_uid", "ts_utc"]).select(["ts_utc", "asset_uid", "close"])

    for h in horizons:
        df = df.with_columns(
            (
                pl.col("close").shift(-h).over("asset_uid") / pl.col("close") - 1.0
            ).alias(f"returns_{h}h")
        )

    return df.drop("close")
