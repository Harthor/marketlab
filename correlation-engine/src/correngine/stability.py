"""Composite stability score (0–100) for each feature.

Weights:
  strength          25%  — based on |pearson correlation|
  consistency       20%  — 1 - CV of rolling correlations
  regimeRobustness  20%  — min/max ratio between regime correlations
  significance      15%  — based on p-value (Benjamini-Hochberg)
  sampleSufficiency 10%  — N / 180, capped at 1.0
  directionality    10%  — based on Granger p-value (forward direction)
"""
from __future__ import annotations

import numpy as np
import polars as pl


def _score_strength(abs_corr: float) -> float:
    """Map |correlation| → [0, 100].  0.0→0, 0.5+→100."""
    if not np.isfinite(abs_corr):
        return 0.0
    return float(min(100.0, abs_corr / 0.5 * 100.0))


def _score_consistency(cv: float) -> float:
    """Map coefficient of variation → [0, 100].  Low CV = high score."""
    if not np.isfinite(cv) or cv < 0:
        return 0.0
    return float(max(0.0, min(100.0, (1.0 - cv) * 100.0)))


def _score_regime_robustness(regime_corrs: list[float]) -> float:
    """min/max ratio of absolute regime correlations → [0, 100]."""
    valid = [abs(c) for c in regime_corrs if np.isfinite(c)]
    if len(valid) < 2:
        return 0.0
    max_val = max(valid)
    min_val = min(valid)
    if max_val == 0:
        return 0.0
    return float(min_val / max_val * 100.0)


def _score_significance(p_value: float) -> float:
    """Map p-value → [0, 100].  p=0 → 100, p=0.10 → 0."""
    if not np.isfinite(p_value):
        return 0.0
    if p_value >= 0.10:
        return 0.0
    return float(max(0.0, (1.0 - p_value / 0.10) * 100.0))


def _score_sample(n: int, target: int = 180) -> float:
    """N/target, capped at 100."""
    if n <= 0:
        return 0.0
    return float(min(100.0, n / target * 100.0))


def _score_directionality(granger_p: float) -> float:
    """Map Granger p-value → [0, 100]. p<0.01→100, p>0.10→0."""
    if not np.isfinite(granger_p):
        return 0.0
    if granger_p >= 0.10:
        return 0.0
    if granger_p <= 0.01:
        return 100.0
    return float((0.10 - granger_p) / (0.10 - 0.01) * 100.0)


WEIGHTS = {
    "strength": 0.25,
    "consistency": 0.20,
    "regimeRobustness": 0.20,
    "significance": 0.15,
    "sampleSufficiency": 0.10,
    "directionality": 0.10,
}


def compute_stability_score(
    corr_df: pl.DataFrame,
    rolling_df: pl.DataFrame,
    regime_df: pl.DataFrame | None,
    granger_df: pl.DataFrame | None,
    *,
    n_target: int = 180,
) -> pl.DataFrame:
    """Return per-feature stability scores with component breakdown.

    Parameters
    ----------
    corr_df : pl.DataFrame
        Must have columns: feature, pearson, pearson_p (or pearson_p_bh), n_obs.
    rolling_df : pl.DataFrame
        Must have columns: feature, correlation (rolling values).
    regime_df : pl.DataFrame | None
        Must have columns: feature, regime, correlation.
    granger_df : pl.DataFrame | None
        Must have columns: feature, p_value_forward.
    n_target : int
        Target sample size for sample sufficiency (default 180).

    Returns
    -------
    pl.DataFrame with columns:
        feature, total, strength, consistency, regimeRobustness,
        significance, sampleSufficiency, directionality
    """
    # Index helpers
    p_col = "pearson_p_bh" if "pearson_p_bh" in corr_df.columns else "pearson_p"
    corr_map: dict[str, dict[str, float]] = {}
    for row in corr_df.iter_rows(named=True):
        f = row["feature"]
        corr_map[f] = {
            "abs_corr": abs(row.get("pearson", 0.0) or 0.0),
            "p_value": row.get(p_col, 1.0) or 1.0,
            "n_obs": row.get("n_obs", 0) or 0,
        }

    # Rolling CV per feature
    rolling_cv: dict[str, float] = {}
    if not rolling_df.is_empty() and "feature" in rolling_df.columns:
        for f in rolling_df["feature"].unique().to_list():
            subset = rolling_df.filter(pl.col("feature") == f)["correlation"].to_numpy()
            finite = subset[np.isfinite(subset)]
            if finite.size > 1 and np.mean(np.abs(finite)) > 1e-9:
                rolling_cv[f] = float(np.std(finite) / (np.mean(np.abs(finite)) + 1e-12))
            else:
                rolling_cv[f] = 1.0

    # Regime correlations per feature
    regime_map: dict[str, list[float]] = {}
    if regime_df is not None and not regime_df.is_empty():
        for row in regime_df.iter_rows(named=True):
            f = row["feature"]
            c = row.get("correlation", np.nan)
            if np.isfinite(c):
                regime_map.setdefault(f, []).append(c)

    # Granger p-values per feature
    granger_map: dict[str, float] = {}
    if granger_df is not None and not granger_df.is_empty():
        for row in granger_df.iter_rows(named=True):
            granger_map[row["feature"]] = row.get("p_value_forward", np.nan) or np.nan

    features = list(corr_map.keys())
    rows: list[dict[str, object]] = []
    for f in features:
        info = corr_map[f]
        s_strength = _score_strength(info["abs_corr"])
        s_consistency = _score_consistency(rolling_cv.get(f, 1.0))
        s_regime = _score_regime_robustness(regime_map.get(f, []))
        s_sig = _score_significance(info["p_value"])
        s_sample = _score_sample(int(info["n_obs"]), n_target)
        s_dir = _score_directionality(granger_map.get(f, np.nan))

        total = (
            WEIGHTS["strength"] * s_strength
            + WEIGHTS["consistency"] * s_consistency
            + WEIGHTS["regimeRobustness"] * s_regime
            + WEIGHTS["significance"] * s_sig
            + WEIGHTS["sampleSufficiency"] * s_sample
            + WEIGHTS["directionality"] * s_dir
        )

        rows.append(
            {
                "feature": f,
                "total": round(total, 1),
                "strength": round(s_strength, 1),
                "consistency": round(s_consistency, 1),
                "regimeRobustness": round(s_regime, 1),
                "significance": round(s_sig, 1),
                "sampleSufficiency": round(s_sample, 1),
                "directionality": round(s_dir, 1),
            }
        )

    if not rows:
        return pl.DataFrame(
            {
                "feature": [],
                "total": [],
                "strength": [],
                "consistency": [],
                "regimeRobustness": [],
                "significance": [],
                "sampleSufficiency": [],
                "directionality": [],
            }
        )
    return pl.DataFrame(rows)
