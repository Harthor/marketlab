"""Quality checks specific to degen data."""
from __future__ import annotations

import polars as pl


def check_market_bars_quality(df: pl.DataFrame) -> dict[str, float]:
    """Run quality checks on market bars DataFrame."""
    if df.is_empty():
        return {"row_count": 0, "completeness": 0.0}

    n = len(df)
    return {
        "row_count": n,
        "null_close_pct": df["close"].null_count() / n * 100,
        "null_volume_pct": df["volume_usd"].null_count() / n * 100,
        "zero_volume_pct": (df["volume_usd"] == 0).sum() / n * 100,
        "unique_assets": df["asset_uid"].n_unique() if "asset_uid" in df.columns else 1,
        "completeness": (1 - df.null_count().sum_horizontal().item() / (n * len(df.columns))) * 100,
    }


def check_watchlist_quality(watchlist_data: dict) -> dict[str, float | int]:
    """Run quality checks on a watchlist snapshot."""
    tokens = watchlist_data.get("tokens", [])
    if not tokens:
        return {"token_count": 0, "quality_score": 0}

    n = len(tokens)
    has_liquidity = sum(1 for t in tokens if t.get("liquidity_usd"))
    has_volume = sum(1 for t in tokens if t.get("volume_24h_usd"))
    has_holders = sum(1 for t in tokens if t.get("holder_count"))
    has_score = sum(1 for t in tokens if t.get("universe_score", 0) > 0)

    return {
        "token_count": n,
        "pct_with_liquidity": has_liquidity / n * 100,
        "pct_with_volume": has_volume / n * 100,
        "pct_with_holders": has_holders / n * 100,
        "pct_with_score": has_score / n * 100,
        "quality_score": (has_liquidity + has_volume + has_holders + has_score) / (4 * n) * 100,
    }
