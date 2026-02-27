from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import polars as pl
from marketlab_core.io import read_csv, read_parquet
from marketlab_core.timeseries import parse_timestamps

TS_ALIASES = ("ts", "timestamp")

DEFAULT_IMPUTATION_POLICY = "zero+coverage"
DEFAULT_IMPUTATION_CONFIG = {
    "strategy": DEFAULT_IMPUTATION_POLICY,
    "coverage_floor": 0.0,
    "max_fill_gap": 1,
}


def _as_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)) and not np.isnan(float(value)):
        return float(value)
    return default


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, np.integer, float)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def dataset_checksum(path: str | Path) -> str:
    target = Path(path)
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset(path: str | Path) -> pl.DataFrame:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"dataset not found: {target}")
    extension = target.suffix.lower()
    if extension in {".parquet", ".pq"}:
        return read_parquet(target)
    if extension in {".csv", ".txt", ".tsv"}:
        return read_csv(target)
    raise ValueError(f"unsupported dataset format: {target.suffix}")


def normalize_dataset(df: pl.DataFrame, target: str, timestamp_col: str | None = None) -> pl.DataFrame:
    if target not in df.columns:
        raise ValueError(f"target column missing: {target}")

    if timestamp_col:
        if timestamp_col not in df.columns:
            raise ValueError(f"missing timestamp column: expected '{timestamp_col}'")
        ts_col = timestamp_col
    else:
        ts_col = next((c for c in TS_ALIASES if c in df.columns), None)  # type: ignore[assignment]
    if ts_col is None:
        raise ValueError("missing timestamp column: expected 'ts' or 'timestamp'")

    if ts_col != "ts":
        df = df.rename({ts_col: "ts"})
    if df["ts"].dtype != pl.Datetime("us"):
        ts_values = parse_timestamps(df["ts"].to_list()).cast(pl.Datetime("us"))
        df = df.with_columns(ts_values.alias("ts"))

    return df.sort("ts")


def ensure_features(df: pl.DataFrame, target: str, features: Sequence[str] | None) -> list[str]:
    if features is not None and len(features) > 0:
        missing = [f for f in features if f not in df.columns]
        if missing:
            raise ValueError(f"features missing from dataset: {missing}")
        return list(features)

    numeric = {name: dtype for name, dtype in df.schema.items() if dtype.is_numeric()}
    feature_candidates = [c for c in numeric if c not in {"ts", target}]
    if not feature_candidates:
        raise ValueError("no numeric feature columns found")
    return feature_candidates


def frame_as_numpy(df: pl.DataFrame, feature_cols: list[str], target: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    working = df.select(["ts", target, *feature_cols]).drop_nulls(subset=[target, *feature_cols])
    y = working[target].to_numpy()
    x = working.select(feature_cols).to_numpy()
    ts = working["ts"].to_numpy()
    return x, y, ts


def apply_imputation(
    df: pl.DataFrame,
    *,
    feature_cols: list[str],
    target: str,
    policy: Mapping[str, object] | str | None = None,
) -> tuple[pl.DataFrame, dict[str, object]]:
    cfg = dict(DEFAULT_IMPUTATION_CONFIG)
    if isinstance(policy, Mapping):
        cfg.update(policy)
    elif isinstance(policy, str):
        cfg["strategy"] = policy

    strategy = str(cfg.get("strategy", DEFAULT_IMPUTATION_POLICY))
    coverage_floor = _as_float(cfg.get("coverage_floor", 0.0), 0.0)
    max_fill_gap = _as_int(cfg.get("max_fill_gap", 1), 1)

    if max_fill_gap < 0 or not np.isfinite(max_fill_gap):
        max_fill_gap = 1

    coverage_cols = [target, *feature_cols]
    if len(feature_cols) == 0:
        raise ValueError("no feature columns provided for imputation")

    if coverage_floor < 0.0 or coverage_floor > 1.0:
        raise ValueError("coverage_floor must be between 0 and 1")

    coverage_expr = (
        pl.sum_horizontal(*[pl.col(name).is_not_null().cast(pl.Float64) for name in coverage_cols])
        / float(len(coverage_cols))
    ).alias("coverage_ratio")

    with_coverage = df.select(["ts", target, *feature_cols]).with_columns(coverage_expr)
    coverage_ratio = np.asarray(with_coverage["coverage_ratio"], dtype=float)
    coverage_keep = coverage_ratio >= coverage_floor
    rows_total = int(with_coverage.height)
    rows_kept = int(coverage_keep.sum())
    rows_dropped = rows_total - rows_kept

    # Always keep rows with a valid target.
    coverage_keep = np.logical_and(coverage_keep, np.asarray(with_coverage[target].is_not_null()))

    filtered = with_coverage.filter(pl.Series("coverage_keep", coverage_keep))
    if filtered.is_empty():
        raise ValueError("no rows left after imputation/coverage filtering")

    imputed = filtered
    feature_exprs: list[pl.Expr] = []
    strategy_name = strategy.lower()
    for feature_name in feature_cols:
        if strategy_name.startswith("ffill"):
            feature_exprs.append(
                pl.when(pl.col(feature_name).is_not_null())
                .then(pl.col(feature_name))
                .otherwise(pl.col(feature_name).fill_null(strategy="forward", limit=max_fill_gap).fill_null(0.0))
                .alias(feature_name)
            )
        elif strategy_name.startswith("zero"):
            feature_exprs.append(pl.col(feature_name).fill_null(0.0).alias(feature_name))
        else:
            raise ValueError(f"unsupported imputation strategy: {strategy}")

    if feature_exprs:
        imputed = imputed.with_columns(feature_exprs)

    imputed = imputed.drop("coverage_ratio")
    remaining_nulls = imputed.select(feature_cols + [target]).null_count()
    null_series = remaining_nulls.row(0)
    if any(int(v) > 0 for v in null_series):
        imputed = imputed.drop_nulls(subset=feature_cols + [target])

    coverage_report = {
        "strategy": strategy_name,
        "coverage_floor": coverage_floor,
        "max_fill_gap": max_fill_gap,
        "rows": {
            "total": rows_total,
            "kept": rows_kept,
            "dropped": rows_dropped,
        },
        "coverage": {
            "min": float(np.nanmin(coverage_ratio)) if rows_total else 0.0,
            "max": float(np.nanmax(coverage_ratio)) if rows_total else 0.0,
            "mean": float(np.nanmean(coverage_ratio)) if rows_total else 0.0,
        },
    }
    rows_section = coverage_report["rows"]
    if not isinstance(rows_section, dict):
        raise RuntimeError("invalid coverage report structure")
    if np.isfinite(coverage_floor) and 0.0 <= coverage_floor <= 1.0:
        rows_section["kept_after_coverage"] = int(np.asarray(coverage_keep).sum())

    return imputed, coverage_report


def select_non_pred_columns(df: pl.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in {"ts", "returns_1d"}]
