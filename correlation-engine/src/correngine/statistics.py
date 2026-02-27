from __future__ import annotations

from typing import Iterable

import numpy as np
import polars as pl
import pandas as pd
from scipy import stats
from sklearn.feature_selection import mutual_info_regression

try:
    import dcor as dcor_lib
except Exception:  # pragma: no cover
    dcor_lib = None


def benjamini_hochberg(p_values: Iterable[float]) -> np.ndarray:
    p = np.asarray(list(p_values), dtype=float)
    if p.size == 0:
        return p
    adjusted = np.full_like(p, np.nan, dtype=float)
    finite = np.isfinite(p)
    if not finite.any():
        return adjusted
    p_f = p[finite]
    m = p_f.size
    order = np.argsort(p_f)
    ranked = np.arange(1, m + 1)
    p_sorted = p_f[order]
    q_sorted = p_sorted * m / ranked
    q_sorted = np.minimum.accumulate(q_sorted[::-1])[::-1]
    adjusted_sorted = np.minimum(1.0, q_sorted)
    finite_idx = np.flatnonzero(finite)
    adjusted[finite_idx[order]] = adjusted_sorted
    return adjusted


def _pearson_corr_with_p(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    n = x.size
    if n < 3:
        return np.nan, np.nan
    x_std = x.std(ddof=1)
    y_std = y.std(ddof=1)
    if x_std == 0.0 or y_std == 0.0:
        return np.nan, np.nan
    r = float(np.corrcoef(x, y)[0, 1])
    if not np.isfinite(r):
        return np.nan, np.nan
    r = np.clip(r, -0.999999999999, 0.999999999999)
    t_stat = r * np.sqrt((n - 2) / (1 - r * r))
    p = float(2 * stats.t.sf(np.abs(t_stat), df=max(1, n - 2)))
    return r, p


def _spearman_corr_with_p(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if x.size < 3:
        return np.nan, np.nan
    try:
        corr, p = stats.spearmanr(x, y)
    except ValueError:
        return np.nan, np.nan
    if not np.isfinite(corr) or not np.isfinite(p):
        return np.nan, np.nan
    return float(corr), float(p)


def compute_correlations(data: pl.DataFrame, features: list[str], target: str, *, seed: int) -> pl.DataFrame:
    target_values = data[target].to_numpy()
    rows = []
    for feature in features:
        feature_values = data[feature].to_numpy()
        valid = np.isfinite(feature_values) & np.isfinite(target_values)
        n_obs = int(valid.sum())
        if n_obs < 3:
            rows.append(
                {
                    "feature": feature,
                    "pearson": np.nan,
                    "pearson_p": np.nan,
                    "spearman": np.nan,
                    "spearman_p": np.nan,
                    "n_obs": n_obs,
                    "n_effective": n_obs,
                }
            )
            continue
        x = feature_values[valid].astype(float)
        y = target_values[valid].astype(float)
        pearson_r, pearson_p = _pearson_corr_with_p(x, y)
        spearman_r, spearman_p = _spearman_corr_with_p(x, y)
        rows.append(
            {
                "feature": feature,
                "pearson": pearson_r,
                "pearson_p": pearson_p,
                "spearman": spearman_r,
                "spearman_p": spearman_p,
                "n_obs": n_obs,
                "n_effective": n_obs,
            }
        )
    return pl.DataFrame(rows)


def compute_rolling_correlations(
    data: pl.DataFrame,
    features: list[str],
    target: str,
    timestamp: str,
    windows: tuple[int, ...],
) -> pl.DataFrame:
    if not features:
        return pl.DataFrame({"timestamp": [], "feature": [], "window": [], "correlation": []})
    pdf = data.select([timestamp, target, *features]).to_pandas()
    ts = pl.Series(pdf[timestamp]).cast(pl.Datetime("us", time_zone="UTC")).to_list()
    y = pd.Series(pdf[target].to_numpy(dtype=float))
    rows = []
    for feature in features:
        x = pd.Series(pdf[feature].to_numpy(dtype=float))
        for window in windows:
            corr = y.rolling(window, min_periods=window).corr(x).to_numpy()
            for idx, value in enumerate(corr):
                if np.isfinite(value):
                    rows.append(
                        {
                            "timestamp": ts[idx],
                            "feature": feature,
                            "window": int(window),
                            "correlation": float(value),
                        }
                    )
    if not rows:
        return pl.DataFrame({"timestamp": [], "feature": [], "window": [], "correlation": []})
    return pl.DataFrame(rows)


def _lag_shift(x: np.ndarray, y: np.ndarray, lag: int) -> tuple[np.ndarray, np.ndarray]:
    if lag == 0:
        return x, y
    if lag > 0:
        return x[:-lag], y[lag:]
    return x[-lag:], y[:lag]


def compute_lag_analysis(data: pl.DataFrame, features: list[str], target: str, max_lag: int, *, seed: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    if max_lag < 0:
        raise ValueError("max_lag debe ser >= 0")
    target_values = np.asarray(data[target], dtype=float)
    lag_rows = []
    summary_rows = []
    lags = list(range(-max_lag, max_lag + 1))
    for feature in features:
        feature_values = np.asarray(data[feature], dtype=float)
        best_abs = -1.0
        best_row = {
            "feature": feature,
            "best_lag": np.nan,
            "best_corr": np.nan,
            "best_abs_corr": np.nan,
            "best_p": np.nan,
            "lead_lag": "undefined",
            "n_obs": np.nan,
            "n_effective": np.nan,
        }
        for lag in lags:
            x, y = _lag_shift(feature_values, target_values, lag)
            valid = np.isfinite(x) & np.isfinite(y)
            n_obs = int(valid.sum())
            if n_obs < 3:
                corr = np.nan
                p = np.nan
            else:
                corr, p = _pearson_corr_with_p(x[valid], y[valid])
            lag_rows.append(
                {
                    "feature": feature,
                    "lag": int(lag),
                    "correlation": corr,
                    "abs_correlation": np.nan if np.isnan(corr) else abs(corr),
                    "p_value": p,
                    "n_obs": n_obs,
                    "n_effective": n_obs,
                }
            )
            if np.isfinite(corr) and abs(corr) > best_abs:
                best_abs = abs(corr)
                best_row.update(
                    {
                        "best_lag": int(lag),
                        "best_corr": corr,
                        "best_abs_corr": abs(corr),
                        "best_p": p,
                        "n_obs": n_obs,
                        "n_effective": n_obs,
                        "lead_lag": "feature_leads" if lag > 0 else "target_leads" if lag < 0 else "synchronous",
                    }
                )
        summary_rows.append(best_row)
    return pl.DataFrame(lag_rows), pl.DataFrame(summary_rows)


def compute_bootstrap_ci(
    data: pl.DataFrame,
    features: list[str],
    target: str,
    *,
    n_boot: int,
    seed: int,
    alpha: float = 0.05,
) -> pl.DataFrame:
    if n_boot <= 1:
        return pl.DataFrame({"feature": [], "metric": [], "estimate": [], "lower": [], "upper": [], "n_boot": []})
    rng = np.random.default_rng(seed)
    target_values = np.asarray(data[target], dtype=float)
    rows = []
    for feature in features:
        x = np.asarray(data[feature], dtype=float)
        valid = np.isfinite(x) & np.isfinite(target_values)
        x = x[valid]
        y = target_values[valid]
        n = x.size
        if n < 3:
            rows.append(
                {
                    "feature": feature,
                    "metric": "pearson",
                    "estimate": np.nan,
                    "lower": np.nan,
                    "upper": np.nan,
                    "n_boot": int(n_boot),
                    "n_effective": int(n),
                }
            )
            continue
        idx = rng.integers(0, n, size=(n_boot, n))
        x_b = x[idx]
        y_b = y[idx]
        x_mu = x_b.mean(axis=1, keepdims=True)
        y_mu = y_b.mean(axis=1, keepdims=True)
        cov = np.sum((x_b - x_mu) * (y_b - y_mu), axis=1)
        den = np.sqrt(np.sum((x_b - x_mu) ** 2, axis=1) * np.sum((y_b - y_mu) ** 2, axis=1))
        corr = np.divide(cov, den, where=den != 0)
        corr = np.where(np.isfinite(corr), corr, np.nan)
        estimate = float(np.nanmean(corr))
        lo, hi = np.nanquantile(corr, [alpha / 2, 1 - alpha / 2])
        rows.append(
            {
                "feature": feature,
                "metric": "pearson",
                "estimate": estimate,
                "lower": float(lo),
                "upper": float(hi),
                "n_boot": int(n_boot),
                "n_effective": int(n),
            }
        )
    return pl.DataFrame(rows)


def compute_mutual_information(data: pl.DataFrame, features: list[str], target: str, *, seed: int) -> pl.DataFrame:
    target_values = np.asarray(data[target], dtype=float)
    rows = []
    for feature in features:
        feature_values = np.asarray(data[feature], dtype=float)
        valid = np.isfinite(feature_values) & np.isfinite(target_values)
        n_obs = int(valid.sum())
        if n_obs < 10:
            rows.append(
                {"feature": feature, "mutual_information": np.nan, "n_obs": n_obs, "n_effective": int(n_obs)}
            )
            continue
        x = feature_values[valid].reshape(-1, 1)
        y = target_values[valid]
        if np.nanstd(x) == 0 or np.nanstd(y) == 0:
            mi = np.nan
        else:
            mi = float(mutual_info_regression(x, y, random_state=seed, n_neighbors=3)[0])
        rows.append({"feature": feature, "mutual_information": mi, "n_obs": n_obs, "n_effective": int(n_obs)})
    return pl.DataFrame(rows)


def _distance_corr_naive(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)
    x = x - x.mean()
    y = y - y.mean()
    if x.size < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    a = np.abs(x[:, None] - x[None, :])
    b = np.abs(y[:, None] - y[None, :])
    a = a - a.mean(axis=0, keepdims=True) - a.mean(axis=1, keepdims=True) + a.mean()
    b = b - b.mean(axis=0, keepdims=True) - b.mean(axis=1, keepdims=True) + b.mean()
    dcov = np.sqrt(np.mean(a * b))
    dvar_x = np.sqrt(np.mean(a * a))
    dvar_y = np.sqrt(np.mean(b * b))
    if dvar_x == 0 or dvar_y == 0:
        return np.nan
    return float(dcov / (np.sqrt(dvar_x * dvar_y) + 1e-12))


def compute_distance_correlation(
    data: pl.DataFrame,
    features: list[str],
    target: str,
    *,
    seed: int,
    max_points: int = 2000,
) -> pl.DataFrame:
    target_values = np.asarray(data[target], dtype=float)
    rng = np.random.default_rng(seed)
    rows = []
    for feature in features:
        feature_values = np.asarray(data[feature], dtype=float)
        valid = np.isfinite(feature_values) & np.isfinite(target_values)
        x = feature_values[valid]
        y = target_values[valid]
        if x.size < 10:
            rows.append(
                {
                    "feature": feature,
                    "distance_correlation": np.nan,
                    "n_obs": int(x.size),
                    "n_effective": int(x.size),
                }
            )
            continue
        if x.size > max_points:
            idx = rng.choice(x.size, size=max_points, replace=False)
            x = x[idx]
            y = y[idx]
        if dcor_lib is not None:
            score = float(dcor_lib.distance_correlation(x, y))
        else:
            score = _distance_corr_naive(x, y)
        rows.append(
            {
                "feature": feature,
                "distance_correlation": score,
                "n_obs": int(x.size),
                "n_effective": int(x.size),
            }
        )
    return pl.DataFrame(rows)
