"""Prepare BTC Google Trends dataset with lag features for walk-forward backtest.

Reads the weekly (monthly) research dataset from altdata-web-signals and produces
a backtest-ready parquet with original pct_change features, lag-1/lag-2 versions,
and the fear_ratio contextual feature.

Output: forecasting-backtest/data/btc_trends_monthly.parquet
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

# --- paths ------------------------------------------------------------------
WORKSPACE = Path(__file__).resolve().parent.parent.parent  # marketlab root
SOURCE_PARQUET = WORKSPACE / "altdata-web-signals" / "data" / "datasets" / "BTC-USD" / "btc_weekly_signals.parquet"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_PATH = OUTPUT_DIR / "btc_trends_monthly.parquet"

# --- feature definitions -----------------------------------------------------
BASE_FEATURES = [
    "signal_trends_bitcoin_pct_change",
    "signal_trends_buy_bitcoin_pct_change",
    "signal_trends_bitcoin_crash_pct_change",
    "signal_trends_crypto_pct_change",
]

CONTEXTUAL_FEATURES = [
    "signal_trends_fear_ratio",
]


def main() -> None:
    if not SOURCE_PARQUET.exists():
        print(f"ERROR: source dataset not found: {SOURCE_PARQUET}", file=sys.stderr)
        sys.exit(1)

    df = pl.read_parquet(SOURCE_PARQUET)
    print(f"Loaded source: {df.shape[0]} rows, {df.shape[1]} cols")

    # Keep only rows with Trends coverage (all base features non-null after lag)
    keep_cols = ["ts_utc", "close", "returns_1w"] + BASE_FEATURES + CONTEXTUAL_FEATURES
    available = [c for c in keep_cols if c in df.columns]
    df = df.select(available).sort("ts_utc")

    # Build lag features (lag1 = shift(1), lag2 = shift(2))
    lag_exprs = []
    lag_cols: list[str] = []
    for feat in BASE_FEATURES:
        if feat not in df.columns:
            continue
        for lag in (1, 2):
            col_name = f"{feat}_lag{lag}"
            lag_cols.append(col_name)
            lag_exprs.append(pl.col(feat).shift(lag).alias(col_name))

    df = df.with_columns(lag_exprs)

    # Drop the first 2 rows (NaN from lags) — they cannot be used for training
    df = df.slice(2)

    # Rename target for forecasting-backtest compatibility
    # The pipeline expects a configurable target column; we keep returns_1w
    all_feature_cols = BASE_FEATURES + lag_cols + CONTEXTUAL_FEATURES
    all_feature_cols = [c for c in all_feature_cols if c in df.columns]

    final_cols = ["ts_utc", "close", "returns_1w"] + all_feature_cols
    final_cols = [c for c in final_cols if c in df.columns]
    df = df.select(final_cols)

    # Drop rows with null in any feature (should only be first rows from lags)
    df = df.drop_nulls(subset=all_feature_cols)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.write_parquet(OUTPUT_PATH)
    print(f"Written: {OUTPUT_PATH}")
    print(f"  Rows: {df.shape[0]}")
    print(f"  Cols: {df.shape[1]}")
    print(f"  Features: {all_feature_cols}")
    print(f"  Date range: {df['ts_utc'].min()} → {df['ts_utc'].max()}")


if __name__ == "__main__":
    main()
