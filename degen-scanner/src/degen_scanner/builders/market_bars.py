"""Build OHLCV 1h bars per asset from GeckoTerminal."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import polars as pl

from ..fetchers.geckoterminal import GeckoTerminalFetcher

logger = logging.getLogger(__name__)


async def fetch_hourly_bars(
    fetcher: GeckoTerminalFetcher,
    network: str,
    pool_address: str,
    limit: int = 24,
) -> pl.DataFrame:
    """Fetch 1h OHLCV bars for a pool and return as a Polars DataFrame.

    GeckoTerminal OHLCV format: [timestamp, open, high, low, close, volume]
    """
    raw = await fetcher.get_pool_ohlcv(
        network=network,
        pool_address=pool_address,
        timeframe="hour",
        aggregate=1,
        limit=limit,
    )

    if not raw:
        return pl.DataFrame(schema={
            "ts_utc": pl.Datetime("us", "UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume_usd": pl.Float64,
        })

    rows = []
    for bar in raw:
        if not isinstance(bar, list) or len(bar) < 6:
            continue
        ts = datetime.fromtimestamp(bar[0], tz=UTC)
        rows.append({
            "ts_utc": ts,
            "open": float(bar[1]),
            "high": float(bar[2]),
            "low": float(bar[3]),
            "close": float(bar[4]),
            "volume_usd": float(bar[5]),
        })

    return pl.DataFrame(rows).sort("ts_utc")


def build_market_bars_table(
    bars_by_asset: dict[str, pl.DataFrame],
) -> pl.DataFrame:
    """Combine per-asset bar DataFrames into a single long-format table."""
    frames = []
    for asset_uid, df in bars_by_asset.items():
        if df.is_empty():
            continue
        frames.append(df.with_columns(pl.lit(asset_uid).alias("asset_uid")))

    if not frames:
        return pl.DataFrame(schema={
            "ts_utc": pl.Datetime("us", "UTC"),
            "asset_uid": pl.Utf8,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume_usd": pl.Float64,
        })

    return pl.concat(frames).sort(["asset_uid", "ts_utc"])
