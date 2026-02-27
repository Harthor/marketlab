from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import traceback
from typing import Any

import numpy as np
import polars as pl
import pandas as pd

try:
    from marketlab_core import validate_manifest as marketlab_validate_manifest
    from marketlab_core import validate_artifacts_exist as marketlab_validate_artifacts_exist
except Exception:  # pragma: no cover
    marketlab_validate_manifest = None
    marketlab_validate_artifacts_exist = None

from .config import RunConfig
from .manifest import SCHEMA_VERSION, build_corr_manifest, write_corr_manifest_atomic
from .marketlab_bridge import align_frames, compute_returns_safe, get_cache, read_table, write_table
from .statistics import (
    benjamini_hochberg,
    compute_bootstrap_ci,
    compute_correlations,
    compute_distance_correlation,
    compute_lag_analysis,
    compute_mutual_information,
    compute_rolling_correlations,
)
from .plotting import plot_lag_profiles, plot_rolling_correlations


ROLLING_CORR_CSV_MAX_ROWS = 20000


@dataclass
class RunResult:
    run_id: str
    run_dir: Path
    summary: dict[str, Any]
    correlation_table: pl.DataFrame
    lag_table: pl.DataFrame
    lag_summary: pl.DataFrame
    rolling_table: pl.DataFrame
    mi_table: pl.DataFrame
    dcor_table: pl.DataFrame | None
    bootstrap_table: pl.DataFrame | None
    feature_summary_table: pl.DataFrame


def _is_nan(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (float, np.floating)):
        return not np.isfinite(value)
    try:
        return bool(pd.isna(value))
    except Exception:
        return False
    return False


def _safe_int(value: Any) -> int | None:
    if value is None or _is_nan(value):
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        as_float = float(value)
        if not np.isfinite(as_float):
            return None
        return int(as_float)
    except (TypeError, ValueError, OverflowError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None or _is_nan(value):
        return None
    try:
        as_float = float(value)
        if not np.isfinite(as_float):
            return None
        return as_float
    except (TypeError, ValueError, OverflowError):
        return None



def _contains_nonfinite_floats(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_nonfinite_floats(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_nonfinite_floats(v) for v in value)
    if isinstance(value, tuple):
        return any(_contains_nonfinite_floats(v) for v in value)
    if isinstance(value, np.ndarray):
        return any(_contains_nonfinite_floats(v) for v in value.tolist())
    if isinstance(value, (float, np.floating)):
        return not np.isfinite(value)
    if isinstance(value, (int, bool, str)) or value is None:
        return False
    return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dataset_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _config_hash(cfg: RunConfig) -> str:
    payload = cfg.as_dict()
    payload_text = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload_text.encode("utf-8")).hexdigest()


def _make_run_id(dataset_hash: str, cfg: RunConfig) -> str:
    now = datetime.utcnow()
    ts = now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond // 1000:03d}Z"
    target = cfg.target[:16]
    return f"{ts}_{target}_{cfg.max_lag}lag_{dataset_hash[:8]}"


def _coerce_timestamp_column(frame: pl.DataFrame, timestamp: str) -> pl.DataFrame:
    if timestamp not in frame.columns:
        raise ValueError(f"Falta columna timestamp '{timestamp}' en dataset")
    dtype = frame[timestamp].dtype
    if getattr(dtype, "is_temporal", lambda: False)():
        if getattr(frame[timestamp].dtype, "time_zone", None) is None:
            return frame.with_columns(pl.col(timestamp).dt.replace_time_zone("UTC"))
        return frame
    return frame.with_columns(pl.col(timestamp).cast(pl.Utf8, strict=False).str.strptime(pl.Datetime("us"), strict=False).dt.replace_time_zone("UTC"))


def _resolve_features(frame: pl.DataFrame, timestamp: str, target: str) -> list[str]:
    features: list[str] = []
    for name, dtype in frame.schema.items():
        if name in {timestamp, target}:
            continue
        if dtype.is_numeric():
            features.append(name)
    return sorted(features)


def _coalesce_effective_n(row: dict[str, Any]) -> int | None:
    n_effective = _safe_int(row.get("n_effective", row.get("n_obs")))
    if n_effective is None or n_effective <= 0:
        return None
    return n_effective


def _warning_if_low_n(row: dict[str, Any], min_n: int) -> str | None:
    n_effective = _coalesce_effective_n(row)
    if n_effective is None:
        return "low_n_effective:unknown"
    if n_effective < min_n:
        return f"low_n_effective:{n_effective}<{min_n}"
    return None


def _top_features(
    rows: pl.DataFrame,
    score_col: str,
    *,
    top: int,
    abs_score: bool = False,
    include_best_lag: bool = False,
    min_effective: int,
) -> list[dict[str, Any]]:
    if rows.is_empty():
        return []
    pdf = rows.to_pandas().copy()

    metric_col = score_col
    if abs_score:
        pdf["__metric"] = pdf[metric_col].abs()
    else:
        pdf["__metric"] = pdf[metric_col]

    if "n_effective" in pdf.columns:
        pdf["__n_effective"] = pdf["n_effective"]
    elif "n_obs" in pdf.columns:
        pdf["__n_effective"] = pdf["n_obs"]
    else:
        pdf["__n_effective"] = np.nan

    pdf.loc[pdf["__n_effective"].fillna(0) < min_effective, "__metric"] = np.nan

    if "__metric" in pdf.columns:
        pdf = pdf.sort_values("__metric", ascending=False, na_position="last", kind="mergesort")

    top_rows = pdf.head(top).to_dict(orient="records")
    out: list[dict[str, Any]] = []
    for row in top_rows:
        value = row.get(score_col)
        payload: dict[str, Any] = {
            "feature": row.get("feature"),
            score_col: _safe_float(value),
        }
        if "p_value" in row:
            payload["p_value"] = _safe_float(row.get("p_value"))
        if "p_value" not in row and f"{score_col}_p" in row:
            payload["p_value"] = _safe_float(row.get(f"{score_col}_p"))
        if include_best_lag and "best_lag" in row:
            payload["best_lag"] = _safe_int(row.get("best_lag"))
        payload["n_effective"] = _coalesce_effective_n(row)
        warning = _warning_if_low_n(row, min_effective)
        if warning is not None:
            payload["warning"] = warning
        out.append(payload)
    return out


def _top_lag_features(summary: pl.DataFrame, *, top: int, min_effective: int) -> list[dict[str, Any]]:
    if summary.is_empty():
        return []
    pdf = summary.to_pandas().copy()
    if "n_effective" in pdf.columns:
        pdf["__n_effective"] = pdf["n_effective"]
    else:
        pdf["__n_effective"] = pdf.get("n_obs", np.nan)
    pdf["__sort"] = pdf["best_abs_corr"].abs().where(pdf["__n_effective"].fillna(0) >= min_effective)
    pdf = pdf.sort_values("__sort", ascending=False, na_position="last", kind="mergesort")
    top_rows = pdf.head(top).to_dict(orient="records")
    out: list[dict[str, Any]] = []
    for row in top_rows:
        payload = {
            "feature": row.get("feature"),
            "best_lag": _safe_int(row.get("best_lag")),
            "best_corr": _safe_float(row.get("best_corr")),
            "best_abs_corr": _safe_float(row.get("best_abs_corr")),
            "best_p": _safe_float(row.get("best_p")),
            "lead_lag": row.get("lead_lag"),
            "n_effective": _coalesce_effective_n(row),
        }
        warning = _warning_if_low_n(row, min_effective)
        if warning is not None:
            payload["warning"] = warning
        out.append(payload)
    return out


def _old_style_top_features(summary: pl.DataFrame, *, top: int, min_effective: int) -> list[str]:
    if summary.is_empty():
        return []
    pdf = summary.to_pandas().copy()
    if "n_effective" in pdf.columns:
        mask = pdf["n_effective"].fillna(0).astype(float) >= min_effective
    else:
        mask = pd.Series(True, index=pdf.index)
    pdf = pdf[mask]
    if "best_abs_corr" not in pdf.columns or pdf.empty:
        return []
    pdf = pdf.sort_values("best_abs_corr", ascending=False, na_position="last", kind="mergesort")
    return pdf.head(top)["feature"].to_list()


def _build_feature_summary(
    correlation_table: pl.DataFrame,
    lag_summary: pl.DataFrame,
    mi_table: pl.DataFrame,
    dcor_table: pl.DataFrame | None,
    bootstrap_table: pl.DataFrame | None,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []

    for row in correlation_table.to_dicts():
        base = {"feature": row.get("feature"), "n_effective": _coalesce_effective_n(row)}
        rows.append(
            {
                **base,
                "metric": "pearson",
                "score": _safe_float(row.get("pearson")),
                "p_value": _safe_float(row.get("pearson_p")),
                "best_lag": None,
            }
        )
        rows.append(
            {
                **base,
                "metric": "spearman",
                "score": _safe_float(row.get("spearman")),
                "p_value": _safe_float(row.get("spearman_p")),
                "best_lag": None,
            }
        )

    for row in lag_summary.to_dicts():
        rows.append(
            {
                "feature": row.get("feature"),
                "metric": "best_lag",
                "score": _safe_float(row.get("best_corr")),
                "p_value": _safe_float(row.get("best_p")),
                "n_effective": _coalesce_effective_n(row),
                "best_lag": _safe_int(row.get("best_lag")),
            }
        )

    for row in mi_table.to_dicts():
        rows.append(
            {
                "feature": row.get("feature"),
                "metric": "mutual_information",
                "score": _safe_float(row.get("mutual_information")),
                "p_value": None,
                "n_effective": _coalesce_effective_n(row),
                "best_lag": None,
            }
        )

    if dcor_table is not None:
        for row in dcor_table.to_dicts():
            rows.append(
                {
                    "feature": row.get("feature"),
                    "metric": "distance_correlation",
                    "score": _safe_float(row.get("distance_correlation")),
                    "p_value": None,
                    "n_effective": _coalesce_effective_n(row),
                    "best_lag": None,
                }
            )

    if bootstrap_table is not None:
        for row in bootstrap_table.to_dicts():
            rows.append(
                {
                    "feature": row.get("feature"),
                    "metric": f"{row.get('metric')}_bootstrap",
                    "score": _safe_float(row.get("estimate")),
                    "p_value": None,
                    "n_effective": _safe_int(row.get("n_effective", row.get("n_obs", None))),
                    "best_lag": None,
                }
            )

    if not rows:
        return pl.DataFrame(
            {
                "feature": [],
                "metric": [],
                "score": [],
                "p_value": [],
                "n_effective": [],
                "best_lag": [],
            }
        )
    return pl.DataFrame(rows)


def _write_readme(
    path: Path,
    run_id: str,
    config: RunConfig,
    dataset_hash: str,
    dataset_path: Path,
    status: str,
    schema_version: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"""# Correlation Engine Run {run_id}\n\n"""
    text += "## Configuración\n\n"
    text += f"- run_id: `{run_id}`\n"
    text += f"- status: `{status}`\n"
    text += f"- schema_version: `{schema_version}`\n"
    text += f"- dataset: `{dataset_path}`\n"
    text += f"- dataset_hash: `{dataset_hash}`\n"
    text += f"- timestamp_col: `{config.timestamp}`\n"
    text += f"- target: `{config.target}`\n"
    text += f"- max_lag: `{config.max_lag}`\n"
    text += f"- windows: `{', '.join(map(str, config.windows))}`\n"
    text += f"- bootstrap: `{config.bootstrap}`\n"
    text += f"- seed: `{config.seed}`\n"
    text += f"- min_effective_obs: `{config.min_effective_obs}`\n"
    text += f"- Fecha UTC: {_now()}\n\n"
    text += "## Qué incluye este run\n\n"
    text += "- `summary.json`: contrato de manifest para lectura por dashboard.\n"
    text += "- `tables/feature_summary.parquet` y `tables/feature_summary.csv`: resumen plano de métricas por feature.\n"
    text += "- `tables/lag_profile.parquet` y `tables/lag_profile.csv` (si está disponible): perfil de lag feature/lag.\n"
    text += "- `tables/correlations.parquet` y `tables/correlations.csv`: Pearson/Spearman + p-values + BH correction.\n"
    text += "- `tables/top_correlations.parquet` y `tables/top_correlations.csv`: top correlations ordenadas por |corr|.\n"
    text += "- `tables/rolling_corr.parquet` y `tables/rolling_corr.csv`: rolling corr por ventanas.\n"
    text += "- `tables/lag.parquet` y `tables/lag.csv`: alias de lag_profile.\n"
    text += "- `tables/lag_summary.parquet` y `tables/lag_summary.csv`: resumen de best lag por feature.\n"
    text += "- `tables/mi.parquet` y `tables/mi.csv`: Mutual information.\n"
    text += "- `tables/distance_correlation.parquet` (si se habilita).\n"
    text += "- `tables/bootstrap_ci.parquet` (si bootstrap>0): intervalos de confianza.\n"
    text += "- `plots/rolling_corr.png`, `plots/lag_profiles.png`: visualizaciones.\n"
    text += "\n## Reproducibilidad\n\n"
    text += "- Se guardan dataset_hash, config y config_hash.\n"
    text += "- La corrida escribe summary con status (`running`, `complete`, `failed`).\n"
    path.write_text(text, encoding="utf-8")


def _collect_global_warnings(
    correlation_table: pl.DataFrame,
    lag_summary: pl.DataFrame,
    mi_table: pl.DataFrame,
    dcor_table: pl.DataFrame | None,
    bootstrap_table: pl.DataFrame | None,
    min_effective: int,
) -> list[str]:
    warnings: list[str] = []

    for row in correlation_table.to_dicts():
        warning = _warning_if_low_n(row, min_effective)
        if warning:
            warnings.append(f"feature={row.get('feature')}|pearson|{warning}")
    for row in lag_summary.to_dicts():
        warning = _warning_if_low_n(row, min_effective)
        if warning:
            warnings.append(f"feature={row.get('feature')}|best_lag|{warning}")
    for row in mi_table.to_dicts():
        warning = _warning_if_low_n(row, min_effective)
        if warning:
            warnings.append(f"feature={row.get('feature')}|mutual_information|{warning}")
    if dcor_table is not None:
        for row in dcor_table.to_dicts():
            warning = _warning_if_low_n(row, min_effective)
            if warning:
                warnings.append(f"feature={row.get('feature')}|distance_correlation|{warning}")
    if bootstrap_table is not None:
        for row in bootstrap_table.to_dicts():
            _n_eff = _safe_int(row.get("n_effective"))
            if "n_effective" in row and _n_eff is not None and _n_eff < min_effective:
                warnings.append(f"feature={row.get('feature')}|bootstrap|low_n_effective:{row.get('n_effective')}<{min_effective}")

    return sorted(set(warnings))


def _collect_artifact_paths(artifacts: list[dict[str, str]], run_dir: Path) -> None:
    for artifact in artifacts:
        relative = artifact.get("path", "")
        if not isinstance(relative, str) or not relative:
            raise ValueError("Artifact path inválido")
        if (run_dir / relative).exists() is False:
            raise FileNotFoundError(f"Artifact no encontrado: {relative}")


def _filter_existing_artifacts(
    artifacts: list[dict[str, Any]], run_dir: Path
) -> tuple[list[dict[str, Any]], list[str]]:
    existing: list[dict[str, Any]] = []
    missing: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            missing.append("<invalid-artifact>")
            continue
        relative = artifact.get("path", "")
        if not isinstance(relative, str) or not relative:
            missing.append("<invalid-path>")
            continue
        if (run_dir / relative).exists():
            existing.append(artifact)
        else:
            missing.append(relative)
    return existing, missing


def _validate_manifest(summary: dict[str, Any], run_dir: Path) -> None:
    required_keys = {
        "run_id",
        "schema_version",
        "kind",
        "status",
        "created_at_utc",
        "dataset_path",
        "dataset_hash",
        "dataset_rows",
        "config",
        "config_hash",
        "seed",
        "artifacts",
        "tables",
        "plots",
        "top_features",
    }
    missing = required_keys.difference(summary.keys())
    if missing:
        raise ValueError(f"Manifest missing required fields: {sorted(missing)}")
    if summary.get("kind") != "correlation":
        raise ValueError(f"Invalid manifest kind: {summary.get('kind')}")
    if summary.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Invalid schema_version: {summary.get('schema_version')}")

    if summary.get("status") == "complete" and _contains_nonfinite_floats(summary):
        raise ValueError("Manifest has non-finite float values")
    if summary.get("status") == "complete":
        if not isinstance(summary.get("tables"), list):
            raise ValueError("Manifest 'tables' must be a list for complete status")
        if not isinstance(summary.get("plots"), list):
            raise ValueError("Manifest 'plots' must be a list for complete status")
        top_features = summary.get("top_features")
        if not isinstance(top_features, dict):
            raise ValueError("Manifest 'top_features' must be a dict for complete status")

    if marketlab_validate_manifest is not None:
        if summary.get("status") != "skipped":
            try:
                marketlab_validate_manifest(summary)
            except TypeError:
                marketlab_validate_manifest(summary, run_dir)
    if marketlab_validate_artifacts_exist is not None and summary.get("status") == "complete":
        try:
            marketlab_validate_artifacts_exist(summary)
        except TypeError:
            marketlab_validate_artifacts_exist(summary, run_dir)


def _dataset_meta(
    run_id: str,
    dataset_path: Path,
    dataset_hash: str,
    dataset_rows: int,
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    now = created_at_utc or _now()
    return {
        "run_id": run_id,
        "dataset_path": str(dataset_path.resolve()),
        "dataset_hash": dataset_hash,
        "dataset_rows": int(dataset_rows),
        "created_at_utc": now,
        "created_utc": now,
    }


def _empty_top_features() -> dict[str, list[dict[str, Any]]]:
    return {
        "pearson": [],
        "spearman": [],
        "mi": [],
        "best_lag": [],
        "pearson_abs": [],
        "spearman_abs": [],
        "mutual_information": [],
        "distance_correlation": [],
    }


def _build_summary(
    cfg: RunConfig,
    run_id: str,
    dataset_path: Path,
    dataset_hash: str,
    dataset_rows: int,
    status: str,
    artifacts: list[dict[str, str]] | None,
    tables: list[str] | None,
    plots: list[str] | None,
    correlation_table: pl.DataFrame,
    lag_summary: pl.DataFrame,
    mi_table: pl.DataFrame,
    dcor_table: pl.DataFrame | None,
    feature_summary_table: pl.DataFrame,
    min_effective: int,
    warnings: list[str] | None,
    error: dict[str, Any] | None = None,
    completed_at_utc: str | None = None,
    *,
    run_created_at_utc: str | None = None,
    top_features_override: dict[str, Any] | None = None,
    feature_summary_preview: list[dict[str, Any]] | None = None,
    extra_fields: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    top_features = top_features_override or {
        "pearson": _top_features(
            correlation_table, "pearson", top=cfg.top, abs_score=True, min_effective=min_effective
        ),
        "spearman": _top_features(
            correlation_table, "spearman", top=cfg.top, abs_score=True, min_effective=min_effective
        ),
        "mi": _top_features(mi_table, "mutual_information", top=cfg.top, min_effective=min_effective),
        "best_lag": _top_lag_features(lag_summary, top=cfg.top, min_effective=min_effective),
        "pearson_abs": _top_features(
            correlation_table, "pearson", top=cfg.top, abs_score=True, min_effective=min_effective
        ),
        "spearman_abs": _top_features(
            correlation_table, "spearman", top=cfg.top, abs_score=True, min_effective=min_effective
        ),
        "mutual_information": _top_features(
            mi_table, "mutual_information", top=cfg.top, min_effective=min_effective
        ),
        "distance_correlation": _top_features(
            dcor_table, "distance_correlation", top=cfg.top, min_effective=min_effective
        )
        if dcor_table is not None
        else [],
    }
    preview = feature_summary_preview
    if preview is None:
        preview = []
        if not feature_summary_table.is_empty():
            preview = feature_summary_table.sort("feature").head(min(40, feature_summary_table.height)).to_dicts()

    return build_corr_manifest(
        result={"top_features": top_features, "feature_summary_preview": preview},
        config=cfg,
        dataset_meta=_dataset_meta(
            run_id=run_id,
            dataset_path=dataset_path,
            dataset_hash=dataset_hash,
            dataset_rows=dataset_rows,
            created_at_utc=run_created_at_utc,
        ),
        artifacts=artifacts,
        status=status,
        top_features=top_features,
        tables=tables,
        plots=plots,
        warnings=warnings,
        errors=errors,
        error=error,
        completed_at_utc=completed_at_utc,
        feature_summary_preview=preview,
        extra_fields=extra_fields,
    )


def _build_running_summary(
    cfg: RunConfig,
    run_id: str,
    dataset_path: Path,
    dataset_hash: str,
    dataset_rows: int,
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    created = created_at_utc or _now()
    return build_corr_manifest(
        result={"top_features": _empty_top_features()},
        config=cfg,
        dataset_meta=_dataset_meta(
            run_id=run_id,
            dataset_path=dataset_path,
            dataset_hash=dataset_hash,
            dataset_rows=dataset_rows,
            created_at_utc=created,
        ),
        artifacts=[],
        status="running",
        top_features=_empty_top_features(),
        tables=[],
        plots=[],
        warnings=["run in_progress"],
        extra_fields={"notes": ["run in_progress"]},
    )


def _build_skipped_summary(
    cfg: RunConfig,
    run_id: str,
    dataset_path: Path,
    dataset_hash: str,
    dataset_rows: int,
    *,
    created_at_utc: str | None = None,
    errors: list[str] | None = None,
    reason: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    now = created_at_utc or _now()
    return build_corr_manifest(
        result={"top_features": _empty_top_features()},
        config=cfg,
        dataset_meta=_dataset_meta(
            run_id=run_id,
            dataset_path=dataset_path,
            dataset_hash=dataset_hash,
            dataset_rows=dataset_rows,
            created_at_utc=now,
        ),
        status="skipped",
        artifacts=[],
        top_features=_empty_top_features(),
        tables=[],
        plots=[],
        warnings=warnings
        or [
            "insufficient_data: dataset_rows < min_effective_obs",
            f"dataset_rows={dataset_rows}",
            f"min_effective_obs={cfg.min_effective_obs}",
        ],
        errors=errors or ["insufficient_data"],
        completed_at_utc=now,
        extra_fields={"reason": reason} if reason is not None else None,
    )


def _build_failed_summary(
    cfg: RunConfig,
    run_id: str,
    dataset_path: Path,
    dataset_hash: str,
    dataset_rows: int,
    error: Exception,
    traceback_path: str | None,
    *,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    now = created_at_utc or _now()
    error_payload = {
        "type": type(error).__name__,
        "message": str(error),
    }
    if traceback_path is not None:
        error_payload["traceback_path"] = traceback_path
    return build_corr_manifest(
        result={"top_features": _empty_top_features()},
        config=cfg,
        dataset_meta=_dataset_meta(
            run_id=run_id,
            dataset_path=dataset_path,
            dataset_hash=dataset_hash,
            dataset_rows=dataset_rows,
            created_at_utc=now,
        ),
        status="failed",
        artifacts=[],
        top_features=_empty_top_features(),
        tables=[],
        plots=[],
        warnings=["run failed"],
        completed_at_utc=now,
        error=error_payload,
        extra_fields={"notes": ["run failed"]},
    )


def _stable_artifacts(run_root: Path, result: RunResult) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    seq: dict[tuple[str, str], int] = {}

    def _artifact_id(type_: str, name: str, path: str) -> str:
        key = (type_.lower(), name.lower())
        seq[key] = seq.get(key, 0) + 1
        return f"{type_.lower()}::{name.lower()}::{path}::{seq[key]}"

    def add(type_: str, name: str, path: Path) -> None:
        relative = str(path.relative_to(run_root).as_posix())
        artifacts.append({
            "type": type_,
            "name": name,
            "path": relative,
            "artifact_id": _artifact_id(type_, name, relative),
        })

    tables = run_root / "tables"
    add("table", "feature_summary", tables / "feature_summary.parquet")
    add("table", "feature_summary_csv", tables / "feature_summary.csv")
    add("table", "correlations", tables / "correlations.parquet")
    add("table", "correlations_csv", tables / "correlations.csv")
    add("table", "top_correlations", tables / "top_correlations.parquet")
    add("table", "top_correlations_csv", tables / "top_correlations.csv")
    add("table", "rolling_corr", tables / "rolling_corr.parquet")
    add("table", "rolling_corr_csv", tables / "rolling_corr.csv")
    add("table", "lag", tables / "lag.parquet")
    add("table", "lag_profile", tables / "lag_profile.parquet")
    add("table", "lag_summary", tables / "lag_summary.parquet")
    add("table", "lag_summary_csv", tables / "lag_summary.csv")
    add("table", "mutual_information", tables / "mi.parquet")
    add("table", "mutual_information_csv", tables / "mi.csv")
    if result.dcor_table is not None:
        add("table", "distance_correlation", tables / "distance_correlation.parquet")
    if result.bootstrap_table is not None and not result.bootstrap_table.is_empty():
        add("table", "bootstrap_ci", tables / "bootstrap_ci.parquet")

    plots = run_root / "plots"
    add("plot", "rolling_corr", plots / "rolling_corr.png")
    add("plot", "lag_profiles", plots / "lag_profiles.png")

    add("readme", "run_readme", run_root / "README.md")
    add("manifest", "summary", run_root / "summary.json")

    return artifacts


def _write_table_with_csv(
    table: pl.DataFrame,
    parquet_path: Path,
    csv_path: Path,
    *,
    sample_max_rows: int | None = None,
) -> None:
    write_table(table, parquet_path)
    export = table
    if sample_max_rows is not None and export.height > sample_max_rows:
        keep_n = min(sample_max_rows, export.height)
        if keep_n <= 0:
            export = export.head(0)
        else:
            export = export.sample(n=keep_n, with_replacement=False, seed=1)
    export.write_csv(csv_path)


def _build_top_correlations_table(
    correlation_table: pl.DataFrame,
    *,
    top: int,
    min_effective: int,
) -> pl.DataFrame:
    if correlation_table.is_empty() or top <= 0:
        return pl.DataFrame(
            {
                "feature": [],
                "metric": [],
                "score": [],
                "p_value": [],
                "n_effective": [],
            }
        )

    rows: list[dict[str, Any]] = []
    for row in _top_features(
        correlation_table,
        "pearson",
        top=max(top * 2, 1),
        abs_score=True,
        min_effective=min_effective,
    ):
        rows.append(
            {
                "feature": row.get("feature"),
                "metric": "pearson",
                "score": _safe_float(row.get("pearson")),
                "p_value": row.get("p_value"),
                "n_effective": row.get("n_effective"),
            }
        )

    for row in _top_features(
        correlation_table,
        "spearman",
        top=max(top * 2, 1),
        abs_score=True,
        min_effective=min_effective,
    ):
        rows.append(
            {
                "feature": row.get("feature"),
                "metric": "spearman",
                "score": _safe_float(row.get("spearman")),
                "p_value": row.get("p_value"),
                "n_effective": row.get("n_effective"),
            }
        )

    if not rows:
        return pl.DataFrame(
            {
                "feature": [],
                "metric": [],
                "score": [],
                "p_value": [],
                "n_effective": [],
            }
        )

    table = pl.DataFrame(rows).with_columns(pl.col("score").abs().alias("_score_abs"))
    table = table.sort("_score_abs", descending=True).head(top).drop("_score_abs")
    return table


def _write_tables(run_root: Path, result: RunResult, *, top: int, min_effective_obs: int) -> None:
    tables = run_root / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    _write_table_with_csv(
        result.correlation_table,
        parquet_path=tables / "correlations.parquet",
        csv_path=tables / "correlations.csv",
    )
    _write_table_with_csv(
        _build_top_correlations_table(
            correlation_table=result.correlation_table,
            top=top,
            min_effective=min_effective_obs,
        ),
        parquet_path=tables / "top_correlations.parquet",
        csv_path=tables / "top_correlations.csv",
    )
    _write_table_with_csv(
        result.rolling_table,
        parquet_path=tables / "rolling_corr.parquet",
        csv_path=tables / "rolling_corr.csv",
        sample_max_rows=ROLLING_CORR_CSV_MAX_ROWS,
    )
    write_table(result.lag_table, tables / "lag.parquet")
    # alias estable para contrato
    write_table(result.lag_table, tables / "lag_profile.parquet")
    _write_table_with_csv(
        result.lag_summary,
        parquet_path=tables / "lag_summary.parquet",
        csv_path=tables / "lag_summary.csv",
    )
    _write_table_with_csv(
        result.mi_table,
        parquet_path=tables / "mi.parquet",
        csv_path=tables / "mi.csv",
    )
    _write_table_with_csv(
        result.feature_summary_table,
        parquet_path=tables / "feature_summary.parquet",
        csv_path=tables / "feature_summary.csv",
    )
    if result.dcor_table is not None:
        write_table(result.dcor_table, tables / "distance_correlation.parquet")
        result.dcor_table.write_csv(tables / "distance_correlation.csv")
    if result.bootstrap_table is not None and not result.bootstrap_table.is_empty():
        write_table(result.bootstrap_table, tables / "bootstrap_ci.parquet")
        result.bootstrap_table.write_csv(tables / "bootstrap_ci.csv")


def _finalize_run(staging_dir: Path, run_dir: Path, *, run_dir_existed: bool) -> None:
    # staging_dir is `run_dir/.staging`
    if not staging_dir.is_dir():
        raise FileNotFoundError(f"No existe staging: {staging_dir}")
    if run_dir_existed and run_dir.exists():
        shutil.rmtree(run_dir)
        staging_dir.replace(run_dir)
        return
    if run_dir.exists():
        tmp_target = run_dir.with_name(f".{run_dir.name}.staging_finalize_tmp")
        if tmp_target.exists():
            shutil.rmtree(tmp_target)
        staging_dir.rename(tmp_target)
        run_dir.rmdir()
        tmp_target.rename(run_dir)
        return
    staging_dir.replace(run_dir)


def _append_traceback(staging_dir: Path, error: Exception) -> str:
    trace = traceback.format_exc()
    path = staging_dir / "traceback.txt"
    path.write_text(trace, encoding="utf-8")
    return str(path.relative_to(staging_dir.parent).as_posix())


def find_latest_run(reports_dir: str | Path) -> Path | None:
    root = Path(reports_dir)
    if not root.exists():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        return None
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[0]


def run_correlation(cfg: RunConfig) -> RunResult:
    dataset_path = Path(cfg.dataset).expanduser()
    if not dataset_path.exists():
        raise FileNotFoundError(dataset_path)

    dataset_hash = _dataset_hash(dataset_path)
    run_id = _make_run_id(dataset_hash, cfg)
    run_dir = Path(cfg.output_root).expanduser() / run_id
    run_dir_existed = run_dir.exists()
    staging_dir = run_dir / ".staging"

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any]

    cache = get_cache(cfg.cache_root)
    cache_key = f"corr:data:{dataset_hash}:{cfg.timestamp}:{cfg.target}"
    cached = cache.get(cache_key)
    if isinstance(cached, pl.DataFrame):
        frame = cached
    else:
        frame = read_table(dataset_path)
        frame = align_frames([frame], ts_col=cfg.timestamp)
        frame = _coerce_timestamp_column(frame, cfg.timestamp)
        frame = frame.sort(cfg.timestamp)
        cache.set(cache_key, frame)

    if cfg.target not in frame.columns:
        if cfg.target == "returns_1d" and "close" in frame.columns:
            frame = compute_returns_safe(frame, value_col="close", timestamp_col=cfg.timestamp, out_col="returns_1d")
            if "returns_1d" not in frame.columns:
                raise RuntimeError("No se pudo construir returns_1d a partir de close")
        else:
            raise ValueError(f"No existe columna target '{cfg.target}'")

    features = _resolve_features(frame, cfg.timestamp, cfg.target)
    if not features:
        raise ValueError("No hay features numéricas válidas para evaluar")

    run_started_at = _now()
    running_summary = _build_running_summary(
        cfg=cfg,
        run_id=run_id,
        dataset_path=dataset_path,
        dataset_hash=dataset_hash,
        dataset_rows=frame.height,
        created_at_utc=run_started_at,
    )
    write_corr_manifest_atomic(staging_dir, running_summary)

    if frame.height < cfg.min_effective_obs:
        skipped_summary = _build_skipped_summary(
            cfg=cfg,
            run_id=run_id,
            dataset_path=dataset_path,
            dataset_hash=dataset_hash,
            dataset_rows=frame.height,
            created_at_utc=run_started_at,
        )
        _validate_manifest(skipped_summary, staging_dir)
        write_corr_manifest_atomic(staging_dir, skipped_summary)
        _write_readme(
            path=staging_dir / "README.md",
            run_id=run_id,
            config=cfg,
            dataset_hash=dataset_hash,
            dataset_path=dataset_path,
            status="skipped",
            schema_version=SCHEMA_VERSION,
        )
        result = RunResult(
            run_id=run_id,
            run_dir=run_dir,
            summary=skipped_summary,
            correlation_table=pl.DataFrame(),
            lag_table=pl.DataFrame(),
            lag_summary=pl.DataFrame(),
            rolling_table=pl.DataFrame(),
            mi_table=pl.DataFrame(),
            dcor_table=None,
            bootstrap_table=None,
            feature_summary_table=pl.DataFrame(),
        )
        _finalize_run(staging_dir, run_dir, run_dir_existed=run_dir_existed)
        return result

    try:
        correlation_table = compute_correlations(frame, features=features, target=cfg.target, seed=cfg.seed)
        correlation_table = correlation_table.with_columns(
            [
                pl.Series("pearson_p_bh", benjamini_hochberg(correlation_table["pearson_p"].to_list())),
                pl.Series("spearman_p_bh", benjamini_hochberg(correlation_table["spearman_p"].to_list())),
            ]
        )
        correlation_table = correlation_table.with_columns(
            [
                (pl.col("pearson_p_bh") < 0.05).alias("pearson_significant_bh"),
                (pl.col("spearman_p_bh") < 0.05).alias("spearman_significant_bh"),
            ]
        )

        rolling_table = compute_rolling_correlations(
            frame,
            features=features,
            target=cfg.target,
            timestamp=cfg.timestamp,
            windows=cfg.windows,
        )

        lag_table, lag_summary = compute_lag_analysis(
            frame,
            features=features,
            target=cfg.target,
            max_lag=cfg.max_lag,
            seed=cfg.seed,
        )

        mi_table = compute_mutual_information(frame, features=features, target=cfg.target, seed=cfg.seed)
        dcor_table = None
        if cfg.distance_corr:
            dcor_table = compute_distance_correlation(frame, features=features, target=cfg.target, seed=cfg.seed)

        bootstrap_table = None
        if cfg.bootstrap > 0:
            bootstrap_table = compute_bootstrap_ci(
                frame,
                features=features,
                target=cfg.target,
                n_boot=cfg.bootstrap,
                seed=cfg.seed,
                alpha=0.05,
            )

        feature_summary_table = _build_feature_summary(
            correlation_table=correlation_table,
            lag_summary=lag_summary,
            mi_table=mi_table,
            dcor_table=dcor_table,
            bootstrap_table=bootstrap_table,
        )

        result = RunResult(
            run_id=run_id,
            run_dir=run_dir,
            summary={},
            correlation_table=correlation_table,
            lag_table=lag_table,
            lag_summary=lag_summary,
            rolling_table=rolling_table,
            mi_table=mi_table,
            dcor_table=dcor_table,
            bootstrap_table=bootstrap_table,
            feature_summary_table=feature_summary_table,
        )

        _write_tables(
            staging_dir,
            result,
            top=cfg.top,
            min_effective_obs=cfg.min_effective_obs,
        )

        plots_dir = staging_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        top_plot_features = _old_style_top_features(lag_summary, top=min(cfg.top, 10), min_effective=cfg.min_effective_obs)
        plot_rolling_correlations(
            plots_dir / "rolling_corr.png",
            rolling_table,
            top_features=top_plot_features,
            config_windows=cfg.windows,
        )
        plot_lag_profiles(
            plots_dir / "lag_profiles.png",
            lag_table,
            top_features=top_plot_features,
        )

        artifacts = _stable_artifacts(staging_dir, result)
        warnings = _collect_global_warnings(
            correlation_table=correlation_table,
            lag_summary=lag_summary,
            mi_table=mi_table,
            dcor_table=dcor_table,
            bootstrap_table=bootstrap_table,
            min_effective=cfg.min_effective_obs,
        )
        artifacts, missing_artifacts = _filter_existing_artifacts(artifacts, staging_dir)
        if missing_artifacts:
            warnings.extend(f"missing_artifact:{path}" for path in missing_artifacts)

        has_table_artifacts = any(entry.get("type") == "table" for entry in artifacts)
        has_plot_artifacts = any(entry.get("type") == "plot" for entry in artifacts)
        final_status = "complete"
        if not has_table_artifacts and not has_plot_artifacts:
            final_status = "skipped"
            warnings.append("no_artifacts_produced")
            warnings.append("reason:dataset too small")
        summary = _build_summary(
            cfg=cfg,
            run_id=run_id,
            dataset_path=dataset_path,
            dataset_hash=dataset_hash,
            dataset_rows=frame.height,
            status=final_status,
            artifacts=artifacts,
            tables=[entry["path"] for entry in artifacts if entry["type"] == "table" and entry["path"].endswith(".csv")],
            plots=[entry["path"] for entry in artifacts if entry["type"] == "plot"],
            correlation_table=correlation_table,
            lag_summary=lag_summary,
            mi_table=mi_table,
            dcor_table=dcor_table,
            feature_summary_table=feature_summary_table,
            min_effective=cfg.min_effective_obs,
            warnings=warnings,
            completed_at_utc=_now(),
            run_created_at_utc=run_started_at,
        )
        if final_status == "skipped":
            summary["reason"] = "no usable outputs"
        write_corr_manifest_atomic(staging_dir, summary)
        _write_readme(
            path=staging_dir / "README.md",
            run_id=run_id,
            config=cfg,
            dataset_hash=dataset_hash,
            dataset_path=dataset_path,
            status=final_status,
            schema_version=SCHEMA_VERSION,
        )
        if final_status != "skipped":
            _collect_artifact_paths(artifacts, staging_dir)
        _validate_manifest(summary, staging_dir)

        result.summary = summary
        _finalize_run(staging_dir, run_dir, run_dir_existed=run_dir_existed)
        return result
    except Exception as error:
        traceback_path = _append_traceback(staging_dir, error)
        failed_summary = _build_failed_summary(
            cfg=cfg,
            run_id=run_id,
            dataset_path=dataset_path,
            dataset_hash=dataset_hash,
            dataset_rows=frame.height,
            error=error,
            traceback_path=traceback_path,
            created_at_utc=run_started_at,
        )
        write_corr_manifest_atomic(staging_dir, failed_summary)
        _finalize_run(staging_dir, run_dir, run_dir_existed=run_dir_existed)
        raise
