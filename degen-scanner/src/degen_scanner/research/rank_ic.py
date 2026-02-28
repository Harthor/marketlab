"""Cross-sectional Information Coefficient (rank IC)."""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy import stats


def run_cross_sectional_ic(
    features: pl.DataFrame,
    targets: pl.DataFrame,
    feature_cols: list[str],
    target_cols: list[str] | None = None,
) -> pl.DataFrame:
    """Compute rank IC between features and targets at each time step.

    At each hour:
    - Rank tokens by feature value
    - Compute Spearman correlation with forward returns

    Args:
        features: DataFrame with ts_utc, asset_uid, and feature columns.
        targets: DataFrame with ts_utc, asset_uid, and target columns.
        feature_cols: Feature columns to rank.
        target_cols: Target columns. Default: returns_1h, returns_4h.

    Returns:
        DataFrame with: feature, target, ic_mean, ic_std, ic_ir, n_periods.
    """
    if target_cols is None:
        target_cols = ["returns_1h", "returns_4h"]

    merged = features.join(targets, on=["ts_utc", "asset_uid"], how="inner")
    timestamps = merged["ts_utc"].unique().sort()

    rows = []
    for feat_col in feature_cols:
        if feat_col not in merged.columns:
            continue
        for tgt_col in target_cols:
            if tgt_col not in merged.columns:
                continue

            ics = []
            for ts in timestamps:
                cross_section = merged.filter(pl.col("ts_utc") == ts).drop_nulls(
                    subset=[feat_col, tgt_col]
                )
                if len(cross_section) < 5:
                    continue
                x = cross_section[feat_col].to_numpy()
                y = cross_section[tgt_col].to_numpy()
                corr, _ = stats.spearmanr(x, y)
                if np.isfinite(corr):
                    ics.append(corr)

            if len(ics) < 5:
                continue

            ic_arr = np.array(ics)
            rows.append({
                "feature": feat_col,
                "target": tgt_col,
                "ic_mean": round(float(np.mean(ic_arr)), 6),
                "ic_std": round(float(np.std(ic_arr)), 6),
                "ic_ir": round(
                    float(np.mean(ic_arr) / np.std(ic_arr)) if np.std(ic_arr) > 0 else 0,
                    6,
                ),
                "n_periods": len(ics),
            })

    return pl.DataFrame(rows)
