#!/usr/bin/env python3
"""Smoke run helper for correlation-engine.

Genera un reporte consumible por dashboard en `reports/<run_id>/` con:
- tables/*.parquet
- plots/*.png
- summary.json (schema_version=1.0, kind=correlation, status=complete)

Si las dependencias completas del motor no están instaladas en el entorno (polars,
scipy, sklearn, matplotlib, marketlab-core), ejecuta un fallback determinístico
con pandas/numpy para no bloquear validación local.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import argparse
import base64
import json
import math
import sys
import warnings
from typing import Any
import shutil

import numpy as np
import pandas as pd


try:
    import polars as pl  # type: ignore
except Exception:  # pragma: no cover - fallback mode
    pl = None

try:
    from marketlab_core.contracts import TIMESTAMP_COL
except Exception:
    TIMESTAMP_COL = "ts_utc"
    warnings.warn("marketlab-core.contracts unavailable; using fallback timestamp default ts_utc")


README_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)


def _parse_windows(raw: str) -> tuple[int, ...]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        raise ValueError("windows no puede quedar vacío")
    values = []
    for item in parts:
        value = int(item)
        if value <= 0:
            raise ValueError("window inválido: debe ser > 0")
        values.append(value)
    return tuple(sorted(set(values)))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dataset_hash(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _ensure_unique_run_dir(output_root: Path, run_id: str) -> tuple[str, Path]:
    run_dir = output_root / run_id
    if not run_dir.exists():
        return run_id, run_dir

    suffix = 1
    while True:
        candidate = f"{run_id}_{suffix:02d}"
        candidate_dir = output_root / candidate
        if not candidate_dir.exists():
            return candidate, candidate_dir
        suffix += 1


def _make_run_id(dataset_hash: str, max_lag: int, target: str, seed: int) -> str:
    now = datetime.utcnow()
    token = now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond // 1000:03d}Z"
    return f"{token}_{target[:16]}_{max_lag}lag_{dataset_hash[:8]}_seed{seed}"


def _safe_float(value: Any) -> float | None:
    if value is None or value != value:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None or value != value:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def sanitize_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_for_json(v) for key, v in value.items()}
    if isinstance(value, tuple):
        return [sanitize_for_json(v) for v in value]
    if isinstance(value, list):
        return [sanitize_for_json(v) for v in list(value)]
    if isinstance(value, np.ndarray):
        return [sanitize_for_json(v) for v in value.tolist()]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, str) or value is None:
        return value
    return value


def _write_summary_json(path: Path, payload: Any) -> None:
    sanitized = sanitize_for_json(payload)
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(sanitized, handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except ValueError as error:
        if not isinstance(sanitized, dict):
            raise
        warnings = sanitized.get("warnings")
        if not isinstance(warnings, list):
            warnings = []
        else:
            warnings = list(warnings)
        warnings.append(f"json_serialization_warning:{type(error).__name__}:{error}")
        sanitized["status"] = "partial"
        sanitized["warnings"] = warnings
        sanitized["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(sanitized, handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _coalesce_n(row: dict[str, Any]) -> int | None:
    if row.get("n_effective") is not None:
        value = row["n_effective"]
    else:
        value = row.get("n_obs")
    n = _safe_int(value)
    if n is None or n <= 0:
        return None
    return n


def _top_feature_rows(rows: list[dict[str, Any]], score_key: str, *, top: int, abs_score: bool, min_effective: int, include_best_lag: bool = False) -> list[dict[str, Any]]:
    if not rows:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(row.copy())

    if abs_score:
        for row in out:
            row["_metric"] = abs(_safe_float(row.get(score_key)) or 0.0)
    else:
        for row in out:
            row["_metric"] = _safe_float(row.get(score_key))

    def _keep(row: dict[str, Any]) -> bool:
        value = _coalesce_n(row)
        if value is None:
            return False
        return value >= min_effective

    selected = [row for row in out if _keep(row)]
    selected.sort(
        key=lambda r: (-(abs(r["_metric"]) if isinstance(r["_metric"], float) and math.isfinite(r["_metric"]) else 0.0), str(r.get("feature", "")))
    )
    output: list[dict[str, Any]] = []
    for row in selected[:top]:
        payload = {
            "feature": row.get("feature"),
            score_key: _safe_float(row.get(score_key)),
            "n_effective": _coalesce_n(row),
        }
        if "p_value" in row:
            payload["p_value"] = _safe_float(row.get("p_value"))
        if include_best_lag and "best_lag" in row:
            payload["best_lag"] = _safe_int(row.get("best_lag"))
        output.append(payload)
    return output


def _write_placeholder_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(README_PNG)


def _safe_corr(x: np.ndarray, y: np.ndarray) -> float:
    if x.size < 3:
        return float("nan")
    if np.allclose(x, x[0]) or np.allclose(y, y[0]):
        return float("nan")
    corr = np.corrcoef(x, y)[0, 1]
    if np.isfinite(corr):
        return float(corr)
    return float("nan")


def _safe_spearman_corr(x: np.ndarray, y: np.ndarray) -> float:
    if x.size < 3:
        return float("nan")
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if np.std(x) == 0.0 or np.std(y) == 0.0:
        return float("nan")
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    corr = np.corrcoef(rx, ry)[0, 1]
    if np.isfinite(corr):
        return float(corr)
    return float("nan")


def _build_tables_and_plots_fallback(
    df: pd.DataFrame,
    *,
    timestamp: str,
    target: str,
    max_lag: int,
    windows: tuple[int, ...],
    top: int,
    min_effective_obs: int,
    output_root: Path,
    config: dict[str, Any],
    config_hash: str,
    run_id: str,
    dataset_path: Path,
    dataset_hash: str,
    seed: int,
) -> Path:
    final_run_dir = output_root / run_id
    if final_run_dir.exists():
        raise FileExistsError(f"run_dir ya existe y debería ser único: {final_run_dir}")

    staging_root = output_root / f".{run_id}.staging_root"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_dir = staging_root / ".staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    staging_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = staging_dir / "tables"
    plots_dir = staging_dir / "plots"
    tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    running_summary = {
        "run_id": run_id,
        "schema_version": "1.0",
        "kind": "correlation",
        "status": "running",
        "created_at_utc": _now_iso(),
        "dataset_path": str(dataset_path.resolve()),
        "dataset_hash": dataset_hash,
        "dataset_rows": int(df.shape[0]),
        "config_file": None,
        "config": config,
        "config_hash": config_hash,
        "seed": int(seed),
        "top_features": {"pearson": [], "spearman": [], "mi": [], "best_lag": []},
        "artifacts": [],
    }
    _write_summary_json(staging_dir / "summary.json", running_summary)

    if df.shape[0] < min_effective_obs:
        skipped_summary = {
            "run_id": run_id,
            "schema_version": "1.0",
            "kind": "correlation",
            "status": "skipped",
            "created_at_utc": _now_iso(),
            "created_utc": _now_iso(),
            "dataset_path": str(dataset_path.resolve()),
            "dataset_hash": dataset_hash,
            "dataset_rows": int(df.shape[0]),
            "config_file": None,
            "config": config,
            "config_hash": config_hash,
            "seed": int(seed),
            "top_features": {
                "pearson": [],
                "spearman": [],
                "mi": [],
                "best_lag": [],
                "pearson_abs": [],
                "spearman_abs": [],
                "mutual_information": [],
                "distance_correlation": [],
            },
            "artifacts": [],
            "warnings": [
                "insufficient_data: dataset_rows < min_effective_obs",
                f"dataset_rows={df.shape[0]}",
                f"min_effective_obs={min_effective_obs}",
            ],
            "errors": ["insufficient_data"],
            "completed_at_utc": _now_iso(),
        }
        _write_summary_json(staging_dir / "summary.json", skipped_summary)
        (staging_dir / "README.md").write_text(
            "# Correlation Smoke Report\n\n"
            f"- run_id: {run_id}\n"
            f"- schema_version: 1.0\n"
            f"- kind: correlation\n"
            f"- status: skipped\n"
            f"- dataset: {dataset_path}\n",
            encoding="utf-8",
        )
        staging_dir.rename(final_run_dir)
        if staging_root.exists():
            shutil.rmtree(staging_root)
        return final_run_dir

    feature_names = [c for c in df.columns if c != target and c != timestamp and pd.api.types.is_numeric_dtype(df[c])]
    if timestamp in df.columns:
        df[timestamp] = pd.to_datetime(df[timestamp], utc=True, errors="coerce")

    y = df[target].to_numpy(dtype=float)

    rows_corr: list[dict[str, Any]] = []
    rows_mi: list[dict[str, Any]] = []
    for feature in feature_names:
        x = df[feature].to_numpy(dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        n_obs = int(mask.sum())
        if n_obs < 3:
            rows_corr.append(
                {"feature": feature, "pearson": np.nan, "pearson_p": np.nan, "spearman": np.nan, "spearman_p": np.nan, "n_obs": n_obs, "n_effective": n_obs}
            )
            rows_mi.append({"feature": feature, "mutual_information": np.nan, "n_obs": n_obs, "n_effective": n_obs})
            continue
        xv = x[mask]
        yv = y[mask]
        corr = _safe_corr(xv, yv)
        sp = _safe_spearman_corr(xv, yv)
        rows_corr.append(
            {
                "feature": feature,
                "pearson": _safe_float(corr),
                "pearson_p": np.nan,
                "spearman": _safe_float(float(sp)) if sp is not None else np.nan,
                "spearman_p": np.nan,
                "n_obs": n_obs,
                "n_effective": n_obs,
            }
        )
        rows_mi.append({"feature": feature, "mutual_information": np.nan, "n_obs": n_obs, "n_effective": n_obs})

    correlation_df = pd.DataFrame(rows_corr)
    mi_df = pd.DataFrame(rows_mi)

    lag_rows: list[dict[str, Any]] = []
    lag_summary: list[dict[str, Any]] = []
    for feature in feature_names:
        x = df[feature].to_numpy(dtype=float)
        best_abs = -1.0
        summary = {
            "feature": feature,
            "best_lag": np.nan,
            "best_corr": np.nan,
            "best_abs_corr": np.nan,
            "best_p": np.nan,
            "n_obs": np.nan,
            "n_effective": np.nan,
            "lead_lag": "undefined",
        }
        for lag in range(-max_lag, max_lag + 1):
            if lag > 0:
                x_lag = x[:-lag]
                y_lag = y[lag:]
            elif lag < 0:
                x_lag = x[-lag:]
                y_lag = y[:lag]
            else:
                x_lag = x
                y_lag = y
            mask = np.isfinite(x_lag) & np.isfinite(y_lag)
            n_obs = int(mask.sum())
            corr = np.nan
            if n_obs >= 3:
                corr = _safe_corr(x_lag[mask], y_lag[mask])
            lag_rows.append(
                {
                    "feature": feature,
                    "lag": int(lag),
                    "corr": _safe_float(corr),
                    "correlation": _safe_float(corr),
                    "abs_correlation": _safe_float(abs(corr)) if corr is not None and corr == corr else np.nan,
                    "p_value": np.nan,
                    "n_obs": n_obs,
                    "n_effective": n_obs,
                }
            )
            if corr is not None and corr == corr and abs(corr) > best_abs:
                best_abs = abs(corr)
                summary.update(
                    {
                        "best_lag": int(lag),
                        "best_corr": _safe_float(corr),
                        "best_abs_corr": _safe_float(abs(corr)),
                        "best_p": np.nan,
                        "n_obs": n_obs,
                        "n_effective": n_obs,
                        "lead_lag": "feature_leads" if lag > 0 else "target_leads" if lag < 0 else "synchronous",
                    }
                )
        lag_summary.append(summary)

    lag_df = pd.DataFrame(lag_rows)
    lag_summary_df = pd.DataFrame(lag_summary)

    rolling_rows: list[dict[str, Any]] = []
    for feature in feature_names:
        for window in windows:
            pair = pd.DataFrame({timestamp: df[timestamp], target: y, feature: df[feature].to_numpy(dtype=float)})
            corr = pair[target].rolling(window, min_periods=window).corr(pair[feature]).to_numpy()
            for ts_value, value in zip(pair[timestamp].to_list(), corr, strict=False):
                if value is None or (isinstance(value, float) and not math.isfinite(value)):
                    continue
                rolling_rows.append(
                    {
                        "timestamp": ts_value,
                        "feature": feature,
                        "window": int(window),
                        "correlation": _safe_float(value),
                    }
                )
    rolling_df = pd.DataFrame(rolling_rows)

    feature_summary_rows: list[dict[str, Any]] = []
    for row in rows_corr:
        feature_summary_rows.append(
            {
                "feature": row.get("feature"),
                "metric": "pearson",
                "score": _safe_float(row.get("pearson")),
                "p_value": _safe_float(row.get("pearson_p")),
                "n_effective": _coalesce_n(row),
                "best_lag": None,
            }
        )
        feature_summary_rows.append(
            {
                "feature": row.get("feature"),
                "metric": "spearman",
                "score": _safe_float(row.get("spearman")),
                "p_value": _safe_float(row.get("spearman_p")),
                "n_effective": _coalesce_n(row),
                "best_lag": None,
            }
        )
    for row in lag_summary:
        feature_summary_rows.append(
            {
                "feature": row.get("feature"),
                "metric": "best_lag",
                "score": _safe_float(row.get("best_corr")),
                "p_value": _safe_float(row.get("best_p")),
                "n_effective": _coalesce_n(row),
                "best_lag": _safe_int(row.get("best_lag")),
            }
        )
    for row in mi_df.to_dict(orient="records"):
        feature_summary_rows.append(
            {
                "feature": row.get("feature"),
                "metric": "mutual_information",
                "score": _safe_float(row.get("mutual_information")),
                "p_value": None,
                "n_effective": _coalesce_n(row),
                "best_lag": None,
            }
        )

    feature_summary_df = pd.DataFrame(feature_summary_rows)

    correlation_df.to_parquet(tables_dir / "correlations.parquet")
    lag_df.to_parquet(tables_dir / "lag.parquet")
    lag_df.to_parquet(tables_dir / "lag_profile.parquet")
    lag_summary_df.to_parquet(tables_dir / "lag_summary.parquet")
    rolling_df.to_parquet(tables_dir / "rolling_corr.parquet")
    mi_df.to_parquet(tables_dir / "mi.parquet")
    feature_summary_df.to_parquet(tables_dir / "feature_summary.parquet")

    _write_placeholder_png(plots_dir / "rolling_corr.png")
    _write_placeholder_png(plots_dir / "lag_profiles.png")

    top_rows = rows_corr
    top_features = {
        "pearson": _top_feature_rows(top_rows, "pearson", top=top, abs_score=True, min_effective=min_effective_obs),
        "spearman": _top_feature_rows(top_rows, "spearman", top=top, abs_score=True, min_effective=min_effective_obs),
        "mi": _top_feature_rows(mi_df.to_dict(orient="records"), "mutual_information", top=top, abs_score=False, min_effective=min_effective_obs),
        "best_lag": _top_feature_rows(
            lag_summary_df.to_dict(orient="records"),
            "best_abs_corr",
            top=top,
            abs_score=True,
            min_effective=min_effective_obs,
            include_best_lag=True,
        ),
    }
    warnings: list[str] = []
    for row in top_rows:
        n_eff = _coalesce_n(row)
        if n_eff is not None and n_eff < min_effective_obs:
            warnings.append(f"feature={row.get('feature')}|n_effective:{n_eff}<{min_effective_obs}")

    artifacts = [
        {"type": "table", "name": "feature_summary", "path": "tables/feature_summary.parquet"},
        {"type": "table", "name": "correlations", "path": "tables/correlations.parquet"},
        {"type": "table", "name": "rolling_corr", "path": "tables/rolling_corr.parquet"},
        {"type": "table", "name": "lag", "path": "tables/lag.parquet"},
        {"type": "table", "name": "lag_profile", "path": "tables/lag_profile.parquet"},
        {"type": "table", "name": "lag_summary", "path": "tables/lag_summary.parquet"},
        {"type": "table", "name": "mutual_information", "path": "tables/mi.parquet"},
        {"type": "plot", "name": "rolling_corr", "path": "plots/rolling_corr.png"},
        {"type": "plot", "name": "lag_profiles", "path": "plots/lag_profiles.png"},
        {"type": "readme", "name": "run_readme", "path": "README.md"},
        {"type": "manifest", "name": "summary", "path": "summary.json"},
    ]

    summary = {
        "run_id": run_id,
        "schema_version": "1.0",
        "kind": "correlation",
        "status": "complete",
        "created_at_utc": _now_iso(),
        "created_utc": _now_iso(),
        "dataset_path": str(dataset_path.resolve()),
        "dataset_hash": dataset_hash,
        "dataset_rows": int(df.shape[0]),
        "config_file": None,
        "config": config,
        "config_hash": config_hash,
        "seed": int(seed),
        "top_features": top_features,
        "artifacts": artifacts,
        "warnings": warnings,
        "completed_at_utc": _now_iso(),
        "feature_summary_preview": feature_summary_df.sort_values("feature").head(min(40, len(feature_summary_df))).to_dict(orient="records"),
    }

    (staging_dir / "README.md").write_text(
        "# Correlation Smoke Report\n\n"
        f"- run_id: {run_id}\n"
        f"- schema_version: 1.0\n"
        f"- kind: correlation\n"
        f"- dataset: {dataset_path}\n"
        f"- status: complete\n",
        encoding="utf-8",
    )
    _write_summary_json(staging_dir / "summary.json", summary)

    for artifact in artifacts:
        relative = Path(artifact["path"])
        if not (staging_dir / relative).exists():
            raise FileNotFoundError(f"artifact inexistente en staging: {relative}")

    staging_dir.rename(final_run_dir)
    if staging_root.exists():
        shutil.rmtree(staging_root)
    return final_run_dir


def _build_synthetic_dataset(root: Path) -> Path:
    rng = np.random.default_rng(7)
    n = 600
    signal_noise = rng.normal(0.0, 1.0, size=n)
    signal_web = rng.normal(0.0, 1.0, size=n)
    feature = 0.5 * signal_web + 0.1 * rng.normal(0.0, 1.0, size=n)
    returns = np.empty(n, dtype=float)
    returns[:3] = rng.normal(0.0, 0.2, size=3)
    returns[3:] = 0.9 * feature[:-3] + 0.05 * signal_noise[3:]
    signal_macro = rng.normal(0.0, 1.0, size=n).cumsum() * 0.05 + rng.normal(0.0, 0.1, size=n)
    signal_sentiment = rng.normal(0.0, 1.0, size=n)
    close = np.empty(n, dtype=float)
    close[0] = 100.0
    close[1:] = 100.0 + np.cumsum(returns[:-1])
    df = pd.DataFrame(
        {
            "ts_utc": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
            "close": close,
            "signal_web": signal_web,
            "signal_macro": signal_macro,
            "signal_sentiment": signal_sentiment,
            "returns_1d": returns,
        }
    )
    path = root / "reports" / "run_smoke_dataset.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return path


def _run_fallback(dataset_path: Path, *, target: str, timestamp: str, max_lag: int, windows: tuple[int, ...], top: int, seed: int, output_root: Path) -> Path:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset no encontrado: {dataset_path}")

    df = pd.read_parquet(dataset_path)
    if timestamp not in df.columns:
        raise ValueError(f"No existe la columna de tiempo '{timestamp}'")
    if target not in df.columns:
        if target == "returns_1d" and "close" in df.columns:
            prev = df["close"].shift(1)
            df[target] = (df["close"] / prev - 1.0).where(prev.notna() & (prev != 0), np.nan)
        else:
            raise ValueError(f"No existe la columna target '{target}' en el dataset")

    dataset_hash = _dataset_hash(dataset_path)
    run_id = _make_run_id(dataset_hash, max_lag=max_lag, target=target, seed=seed)
    run_id, run_dir = _ensure_unique_run_dir(output_root, run_id)
    config = {
        "dataset": str(dataset_path.resolve()),
        "target": target,
        "timestamp": timestamp,
        "max_lag": max_lag,
        "windows": list(windows),
        "seed": seed,
        "bootstrap": 0,
        "top": top,
        "distance_corr": False,
        "output_root": str(output_root.resolve()),
        "cache_root": None,
        "min_effective_obs": 10,
    }
    config_text = json.dumps(config, sort_keys=True, default=str, ensure_ascii=False)
    config_hash = sha256(config_text.encode("utf-8")).hexdigest()

    return _build_tables_and_plots_fallback(
        df=df,
        timestamp=timestamp,
        target=target,
        max_lag=max_lag,
        windows=windows,
        top=top,
        min_effective_obs=10,
        output_root=output_root,
        config=config,
        config_hash=config_hash,
        run_id=run_id,
        dataset_path=dataset_path,
        dataset_hash=dataset_hash,
        seed=seed,
    )


def _run_engine(dataset_path: Path, *, target: str, timestamp: str, max_lag: int, windows: tuple[int, ...], top: int, seed: int, output_root: Path) -> Path:
    from correngine.config import RunConfig
    from correngine.runner import run_correlation

    cfg = RunConfig(
        dataset=str(dataset_path),
        target=target,
        timestamp=timestamp,
        max_lag=max_lag,
        windows=windows,
        seed=seed,
        bootstrap=0,
        top=top,
        distance_corr=False,
        output_root=str(output_root),
    )
    result = run_correlation(cfg)
    return result.run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Run smoke correlation report")
    parser.add_argument(
        "dataset",
        nargs="?",
        default=None,
        help="Ruta al dataset. Si se omite, genera uno sintético.",
    )
    parser.add_argument("--target", default="returns_1d")
    parser.add_argument("--timestamp", default=TIMESTAMP_COL)
    parser.add_argument("--max-lag", dest="max_lag", type=int, default=5)
    parser.add_argument("--windows", default="10,20,40")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--output-root", default="reports")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    output_root = root / args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    if args.dataset:
        dataset_path = Path(args.dataset).expanduser()
        if not dataset_path.is_absolute():
            dataset_path = (Path.cwd() / args.dataset).resolve()
    else:
        dataset_path = _build_synthetic_dataset(root)

    windows = _parse_windows(args.windows)

    try:
        if pl is not None:
            run_dir = _run_engine(
                dataset_path=dataset_path,
                target=args.target,
                timestamp=args.timestamp,
                max_lag=args.max_lag,
                windows=windows,
                top=args.top,
                seed=args.seed,
                output_root=output_root,
            )
        else:
            raise ModuleNotFoundError("polars no disponible")
    except Exception as error:
        if isinstance(error, ModuleNotFoundError):
            run_dir = _run_fallback(
                dataset_path=dataset_path,
                target=args.target,
                timestamp=args.timestamp,
                max_lag=args.max_lag,
                windows=windows,
                top=args.top,
                seed=args.seed,
                output_root=output_root,
            )
        else:
            raise

    print(f"run_dir={run_dir}")
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        print(f"summary={summary_path}")
        print(f"status={summary.get('status')}")
        print("artifacts=", json.dumps(summary.get("artifacts", []), ensure_ascii=False))
        return 0
    print(f"warn=no summary found: {summary_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
