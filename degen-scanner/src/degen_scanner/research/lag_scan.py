"""Cross-correlation lag scan for degen features vs targets."""
from __future__ import annotations

import polars as pl
from scipy import stats


def run_lag_scan(
    features: pl.DataFrame,
    targets: pl.DataFrame,
    feature_cols: list[str],
    target_cols: list[str],
    lags: list[int] | None = None,
) -> pl.DataFrame:
    """Run cross-correlation between features and targets at specified lags.

    Args:
        features: DataFrame with ts_utc, asset_uid, and feature columns.
        targets: DataFrame with ts_utc, asset_uid, and target columns.
        feature_cols: Feature column names to analyze.
        target_cols: Target column names (e.g., returns_1h, returns_4h).
        lags: Lag values in hours. Default: [1, 2, 4, 8, 24].

    Returns:
        DataFrame with columns: feature, target, lag, correlation, p_value, n.
    """
    if lags is None:
        lags = [1, 2, 4, 8, 24]

    # Join features and targets
    merged = features.join(targets, on=["ts_utc", "asset_uid"], how="inner")

    rows = []
    for feat_col in feature_cols:
        if feat_col not in merged.columns:
            continue
        for tgt_col in target_cols:
            if tgt_col not in merged.columns:
                continue
            for lag in lags:
                # Shift feature by lag (feature leads target)
                shifted = merged.sort(["asset_uid", "ts_utc"]).with_columns(
                    pl.col(feat_col).shift(lag).over("asset_uid").alias("_feat_lagged")
                )
                # Drop nulls
                valid = shifted.drop_nulls(subset=["_feat_lagged", tgt_col])
                n = len(valid)
                if n < 30:
                    continue

                x = valid["_feat_lagged"].to_numpy()
                y = valid[tgt_col].to_numpy()
                corr, pval = stats.pearsonr(x, y)

                rows.append({
                    "feature": feat_col,
                    "target": tgt_col,
                    "lag": lag,
                    "correlation": round(corr, 6),
                    "p_value": round(pval, 6),
                    "n": n,
                })

    return pl.DataFrame(rows)
