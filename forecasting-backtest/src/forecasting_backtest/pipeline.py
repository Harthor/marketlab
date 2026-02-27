from __future__ import annotations

import json
import shutil
import sys
import traceback
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import yaml
import joblib
import numpy as np
import polars as pl
import pandas as pd

from . import __version__
from .backtest import run_simple_backtest
from .config import config_fingerprint
from .data import apply_imputation, dataset_checksum, ensure_features, frame_as_numpy, load_dataset, normalize_dataset
from .metrics import classification_scores, information_scores, regression_scores
from .models import feature_importance, is_baseline, make_model, predict_baseline
from .plots import plot_equity_curve, plot_feature_importance, plot_pred_vs_true
from .validation import iter_time_splits

try:
    from marketlab_core.manifests import validate_artifacts_exist, validate_manifest, write_json_atomic
except Exception:
    validate_artifacts_exist = None
    validate_manifest = None
    write_json_atomic = None


RUN_SCHEMA_VERSION = "1.0"


def _new_run_id(model_name: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{model_name}_{now}_{uuid.uuid4().hex[:8]}"


def _prepare_run_dir(base: Path, run_id: str | None = None, model: str = "model") -> tuple[Path, str]:
    base.mkdir(parents=True, exist_ok=True)
    base_id = run_id or _new_run_id(model)
    run_dir = base / base_id
    if run_dir.exists():
        for idx in range(1, 1000):
            candidate = f"{base_id}-{idx}"
            run_dir = base / candidate
            if not run_dir.exists():
                return run_dir, candidate
        raise FileExistsError(f"could not allocate run directory under {run_dir}")
    return run_dir, base_id


def _align_series(values: np.ndarray, length: int, *, fill_value: float | int | None = None) -> np.ndarray:
    arr = np.asarray(values)
    out = np.full(length, np.nan if fill_value is None else fill_value, dtype=float)
    if len(arr) >= length:
        out[:] = np.asarray(arr[:length], dtype=float)
        return out
    if len(arr) > 0:
        out[: len(arr)] = np.asarray(arr, dtype=float)
    return out


def _find_artifact(summary: dict[str, object], *, name: str | None = None, artifact_type: str | None = None, fallback_key: str | None = None) -> Path | None:
    files = summary.get("files")
    if isinstance(files, dict) and fallback_key and fallback_key in files:
        return Path(files[fallback_key])  # type: ignore[arg-type]

    artifacts = summary.get("artifacts")
    if isinstance(artifacts, list):
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            item_name = item.get("name")
            item_type = item.get("type")
            if name is not None and item_name == name:
                value = item.get("path")
                if isinstance(value, str):
                    return Path(value)
            if artifact_type is not None and item_type == artifact_type:
                value = item.get("path")
                if isinstance(value, str):
                    return Path(value)
    return None


def _manifest_output_path(run_dir: Path) -> Path:
    return run_dir / ".staging" / "run_summary.json"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    normalized = payload
    artifacts = normalized.get("artifacts")
    if isinstance(artifacts, list):
        cleaned_artifacts = []
        dropped = False
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_path = artifact.get("path")
            if not isinstance(artifact_path, str) or not artifact_path.strip():
                dropped = True
                continue
            cleaned_artifacts.append(artifact)
        if dropped:
            warnings = normalized.get("warnings")
            if isinstance(warnings, list):
                if "dropped_empty_artifact_paths" not in warnings:
                    warnings.append("dropped_empty_artifact_paths")
                normalized["warnings"] = warnings
            else:
                normalized["warnings"] = ["dropped_empty_artifact_paths"]
            normalized["artifacts"] = cleaned_artifacts
    if write_json_atomic is not None:
        try:
            write_json_atomic(path, normalized, allow_nan=False)
        except TypeError:
            write_json_atomic(path, normalized)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False, default=str, allow_nan=False),
        encoding="utf-8",
    )


def _flatten_metrics(metrics: object) -> dict[str, float]:
    if not isinstance(metrics, dict):
        return {}
    flat: dict[str, float] = {}
    for section_name, section_values in metrics.items():
        if not isinstance(section_values, dict):
            if isinstance(section_values, (int, float)):
                flat[str(section_name)] = float(section_values)
            continue
        for key, value in section_values.items():
            if isinstance(value, (int, float)):
                flat[f"{section_name}.{key}"] = float(value)
    return flat


def _build_marketlab_payload(summary: dict[str, object], *, status: str) -> dict[str, object]:
    seed_value = summary.get("seed", 0)
    if isinstance(seed_value, bool):
        seed = int(seed_value)
    elif isinstance(seed_value, (int, np.integer)):
        seed = int(seed_value)
    elif isinstance(seed_value, (float, np.floating)):
        seed = int(seed_value)
    elif isinstance(seed_value, str):
        try:
            seed = int(float(seed_value))
        except ValueError:
            seed = 0
    else:
        seed = 0

    payload: dict[str, object] = {
        "schema_version": RUN_SCHEMA_VERSION,
        "kind": summary.get("kind", "forecast"),
        "status": status,
        "run_id": str(summary.get("run_id")),
        "created_at_utc": str(summary.get("created_at_utc", "")),
        "started_at_utc": str(summary.get("started_at_utc", summary.get("created_at_utc", ""))),
        "dataset_path": str(summary.get("dataset_path", "")),
        "dataset_hash": str(summary.get("dataset_hash", "")),
        "config_hash": str(summary.get("config_hash", "")),
        "seed": seed,
        "artifacts": summary.get("artifacts", []),
        "model_name": str(summary.get("model_name")),
        "metrics": _flatten_metrics(summary.get("metrics")),
    }
    if summary.get("completed_at_utc") is not None:
        payload["completed_at_utc"] = str(summary.get("completed_at_utc"))
    return payload


def _mark_error_payload(exc: BaseException, *, traceback_path: str | None = None) -> dict[str, object]:
    return {
        "type": exc.__class__.__name__,
        "message": str(exc),
        "traceback_path": traceback_path,
    }


def _register_artifact(
    artifact_entries: list[dict[str, str]],
    artifact_type: str,
    name: str,
    *,
    path: str | None,
    run_root: Path,
    warnings: list[str],
    skip_reason: str = "empty path",
) -> None:
    if not isinstance(path, str) or not path.strip():
        if "dropped_empty_artifact_paths" not in warnings:
            warnings.append("dropped_empty_artifact_paths")
        warnings.append(f"omit_artifact_{artifact_type}_{name}: {skip_reason}")
        return
    if not (run_root / path).exists():
        warnings.append(f"missing_artifact_path_{artifact_type}_{name}: {path}")
        return
    artifact_entries.append({"type": artifact_type, "name": name, "path": path})


def _finalize_staged_run(run_root: Path) -> None:
    staging_dir = run_root / ".staging"
    if not staging_dir.exists():
        raise FileNotFoundError(f"staging directory missing: {staging_dir}")

    backup = run_root.with_name(f"{run_root.name}.staging_publish_tmp")
    if backup.exists():
        shutil.rmtree(backup)
    run_root.rename(backup)
    try:
        staged_payload = backup / ".staging"
        if not staged_payload.exists():
            raise FileNotFoundError(f"staging payload missing: {staged_payload}")
        staged_payload.rename(run_root)
    except Exception:
        # best effort rollback: preserve backup for inspection
        if (run_root / ".staging").exists():
            shutil.rmtree(run_root)
        backup.rename(run_root)
        raise
    finally:
        if backup.exists():
            shutil.rmtree(backup)


def execute_train(
    *,
    dataset: str,
    target: str,
    model: str,
    config: dict,
    run_id: str | None = None,
    command: str | None = None,
    output_root: str | None = None,
) -> dict:
    base_config = deepcopy(config)
    base_config["dataset"] = dict(base_config.get("dataset", {}))
    base_config["dataset"]["path"] = str(dataset)
    base_config["target"] = target
    base_config["model"]["name"] = model
    base_config["run_id"] = run_id or base_config.get("run_id")
    runs_root = Path(output_root or base_config.get("output_root", "runs"))

    run_dir, resolved_id = _prepare_run_dir(runs_root, base_config.get("run_id"), model=model)
    staging_dir = run_dir / ".staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = Path(base_config["dataset"]["path"])
    dataset_hash = "unknown"
    model_name = base_config["model"].get("name", "ridge")
    model_params = dict(base_config["model"].get("params", {}))
    model_random_state = int(base_config.get("random_state", 42))
    threshold = float(base_config["backtest"]["threshold"])
    walk_cfg = dict(base_config["walk_forward"])
    imputation_cfg = dict(base_config.get("imputation", {}))

    resolved_config = dict(base_config)
    resolved_config_hash = config_fingerprint(resolved_config)
    resolved_config["config_hash"] = resolved_config_hash

    created_at = datetime.now(timezone.utc)
    manifest_path = _manifest_output_path(run_dir)
    run_summary: dict[str, object] = {
        "run_id": resolved_id,
        "created_at": created_at.isoformat(),
        "created_at_utc": created_at.isoformat(),
        "started_at_utc": created_at.isoformat(),
        "completed_at_utc": None,
        "schema_version": RUN_SCHEMA_VERSION,
        "kind": "forecast",
        "status": "running",
        "dataset_path": str(dataset_path),
        "dataset_hash": dataset_hash,
        "model_name": model_name,
        "seed": model_random_state,
        "version": __version__,
        "command": command or "",
        "python": sys.version,
        "dataset": {
            "path": str(dataset_path),
            "hash": dataset_hash,
        },
        "target": target,
        "features": [],
        "imputation": dict(imputation_cfg),
        "split": walk_cfg,
        "split_params": walk_cfg,
        "model": {"type": model_name, "info": {}, "artifact": None},
        "config": resolved_config,
        "config_hash": resolved_config_hash,
        "folds": 0,
        "sweep": [],
        "metrics": {},
        "artifacts": [],
        "warnings": [],
        "files": {},
    }
    _write_json(manifest_path, run_summary)

    try:
        dataset_hash = dataset_checksum(dataset_path)
        df = load_dataset(dataset_path)
        df = normalize_dataset(df, target=target)
        run_summary["dataset_hash"] = dataset_hash
        dataset_payload = run_summary.setdefault("dataset", {})
        if isinstance(dataset_payload, dict):
            dataset_payload["hash"] = dataset_hash
        feature_cols = ensure_features(df, target=target, features=base_config.get("features"))
        imputed_df, imputation_report = apply_imputation(
            df,
            feature_cols=feature_cols,
            target=target,
            policy=imputation_cfg,
        )
        x, y, ts = frame_as_numpy(imputed_df, feature_cols=feature_cols, target=target)
        pdf = pd.DataFrame(x, columns=feature_cols)
        pdf["ts"] = pd.to_datetime(ts)
        pdf[target] = y
        pdf = pdf.sort_values("ts").reset_index(drop=True)

        split_kwargs = {
            "train_window_days": int(walk_cfg["train_window_days"]),
            "test_window_days": int(walk_cfg["test_window_days"]),
            "step_days": int(walk_cfg["step_days"]),
            "min_train_rows": int(walk_cfg["min_train_rows"]),
            "min_test_rows": int(walk_cfg["min_test_rows"]),
        }
        splits = list(
            iter_time_splits(
                pdf,
                ts_col="ts",
                **split_kwargs,
            )
        )
        if not splits:
            raise ValueError("walk-forward generated no splits; adjust windows or dataset size")

        all_predictions = np.full(len(pdf), np.nan, dtype=float)
        all_true = np.full(len(pdf), np.nan, dtype=float)
        all_folds = np.full(len(pdf), -1, dtype=int)

        model_info: dict[str, object] = {}
        fitted_model = None
        model_artifact: dict[str, str] | None = None
        fold_reports = []
        importance_names: list[str] = []
        importance_scores: list[float] = []
        warnings: list[str] = run_summary["warnings"]  # type: ignore[assignment]

        for split in splits:
            train_rows = pdf.iloc[split.train_idx]
            test_rows = pdf.iloc[split.test_idx]
            x_train = train_rows[feature_cols].to_numpy(dtype=float)
            y_train = train_rows[target].to_numpy(dtype=float)
            x_test = test_rows[feature_cols].to_numpy(dtype=float)
            y_test = test_rows[target].to_numpy(dtype=float)

            if is_baseline(model_name):
                if model_name == "naive":
                    model_name = "naive0"
                kind = "naive_last" if model_name == "naive_last" else "naive0"
                y_pred = predict_baseline(kind, y_train, len(y_test))
                model_info = {"type": f"baseline-{kind}"}
            else:
                fitted = make_model(model_name, model_params, random_state=model_random_state)
                fitted.fit(x_train, y_train)
                y_pred = fitted.predict(x_test)
                fitted_model = fitted
                model_info = {"type": model_name, "params": dict(model_params)}

            all_predictions[split.test_idx] = y_pred
            all_true[split.test_idx] = y_test
            all_folds[split.test_idx] = split.fold

            fold_reports.append(
                {
                    "fold": int(split.fold),
                    "train_start": str(split.train_start),
                    "train_end": str(split.train_end),
                    "test_start": str(split.test_start),
                    "test_end": str(split.test_end),
                    "train_rows": int(len(split.train_idx)),
                    "test_rows": int(len(split.test_idx)),
                    "regression": regression_scores(y_test, y_pred),
                    "classification": classification_scores(y_test, y_pred, threshold=float(base_config["backtest"]["threshold"])),
                    "information": information_scores(y_test, y_pred, threshold=float(base_config["backtest"]["threshold"])),
                }
            )

        valid = ~np.isnan(all_predictions)
        y_true_scored = all_true[valid]
        y_pred_scored = all_predictions[valid]

        regression = regression_scores(y_true_scored, y_pred_scored)
        classification = classification_scores(y_true_scored, y_pred_scored, threshold=float(base_config["backtest"]["threshold"]))
        information = information_scores(y_true_scored, y_pred_scored, threshold=float(base_config["backtest"]["threshold"]))

        predictions_for_backtest = np.where(np.isnan(all_predictions), 0.0, all_predictions)
        backtest = run_simple_backtest(
            timestamps=np.asarray(pdf["ts"], dtype="datetime64[ns]"),
            y_true=np.asarray(pdf[target], dtype=float),
            y_pred=predictions_for_backtest,
            threshold=threshold,
            transaction_cost=float(base_config["backtest"]["transaction_cost"]),
            slippage=float(base_config["backtest"]["slippage"]),
            initial_capital=float(base_config["backtest"]["initial_capital"]),
        )

        if fitted_model is not None:
            artifact_dir = staging_dir / "artifacts"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            model_path = artifact_dir / "model.joblib"
            joblib.dump(fitted_model, model_path)
            importance_names, importance_scores = feature_importance(fitted_model, feature_cols)
            importance_path = staging_dir / "feature_importance.parquet"
            if importance_names and importance_scores:
                fi = pl.DataFrame({"feature": importance_names, "importance": importance_scores})
                fi.write_parquet(importance_path)
                plot_feature_importance(importance_names, importance_scores, staging_dir / "feature_importance.png")
            model_artifact = {"path": str(model_path.relative_to(staging_dir)), "hash": dataset_checksum(model_path)}
        else:
            model_path = None
            artifact_dir = staging_dir / "artifacts"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            baseline_path = artifact_dir / "baseline.json"
            baseline_path.write_text(json.dumps({"type": model_info.get("type", "baseline")}, indent=2), encoding="utf-8")
            model_artifact = {"path": str(baseline_path.relative_to(staging_dir)), "hash": dataset_checksum(baseline_path)}
            model_info["type"] = model_info.get("type", "baseline")

        tables_dir = staging_dir / "tables"
        tables_dir.mkdir(exist_ok=True)

        predictions_path = tables_dir / "predictions.parquet"
        predictions_positions = _align_series(np.asarray(backtest["positions"], dtype=float), len(pdf))
        prediction_pnl = _align_series(np.asarray(backtest["pnl"], dtype=float), len(pdf), fill_value=0.0)
        pred_df = pl.DataFrame(
            {
                "ts_utc": np.asarray(pdf["ts"]),
                "fold": all_folds.astype(int),
                "y_true": all_true,
                "y_pred": all_predictions,
                "position": predictions_positions,
                "pnl": prediction_pnl,
            }
        )
        pred_df.write_parquet(predictions_path)

        equity_table_path = tables_dir / "equity.parquet"
        equity_table_legacy_path = tables_dir / "backtest_equity.parquet"
        equity_curve = _align_series(np.asarray(backtest["equity_curve"], dtype=float)[1:], len(pdf))
        drawdown_curve = _align_series(np.asarray(backtest["equity_drawdown"], dtype=float)[1:], len(pdf))
        equity_df = pl.DataFrame({"ts_utc": np.asarray(pdf["ts"]), "equity": equity_curve, "drawdown": drawdown_curve})
        equity_df.write_parquet(equity_table_path)
        equity_df.write_parquet(equity_table_legacy_path)

        equity_plot_path = staging_dir / "equity_curve.png"
        plot_equity_curve(np.asarray(pdf["ts"]), np.asarray(backtest["equity_curve"])[1:], equity_plot_path)
        pred_true_path = staging_dir / "pred_vs_true.png"
        plot_pred_vs_true(
            y_true=y_true_scored,
            y_pred=y_pred_scored,
            out_path=pred_true_path,
        )

        model_artifacts: list[dict[str, str]] = []
        model_artifact_path = None if model_artifact is None else model_artifact.get("path")
        _register_artifact(
            model_artifacts,
            artifact_type="model",
            name=str(model_info.get("type", "model")),
            path=model_artifact_path,
            run_root=staging_dir,
            warnings=warnings,
        )

        artifacts: list[dict[str, str]] = [
            {"type": "table", "name": "predictions", "path": str(predictions_path.relative_to(staging_dir))},
            {"type": "table", "name": "equity", "path": str(equity_table_path.relative_to(staging_dir))},
            {"type": "table", "name": "backtest_equity", "path": str(equity_table_legacy_path.relative_to(staging_dir))},
            {"type": "plot", "name": "equity_curve", "path": str(equity_plot_path.relative_to(staging_dir))},
            {"type": "plot", "name": "pred_vs_true", "path": str(pred_true_path.relative_to(staging_dir))},
            *model_artifacts,
        ]
        if importance_names and importance_scores:
            artifacts.append({"type": "plot", "name": "feature_importance", "path": "feature_importance.png"})
            artifacts.append(
                {"type": "table", "name": "feature_importance", "path": "feature_importance.parquet"}
            )

        completed_summary: dict[str, object] = {
            "run_id": resolved_id,
            "created_at": created_at.isoformat(),
            "created_at_utc": created_at.isoformat(),
            "started_at_utc": created_at.isoformat(),
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "schema_version": RUN_SCHEMA_VERSION,
            "kind": "forecast",
            "status": "complete",
            "dataset_path": str(dataset_path),
            "dataset_hash": dataset_hash,
            "model_name": model_name,
            "seed": model_random_state,
            "version": __version__,
            "command": command or "",
            "python": sys.version,
            "dataset": {
                "path": str(dataset_path),
                "hash": dataset_hash,
                "rows": int(len(imputed_df)),
            },
            "target": target,
            "features": feature_cols,
            "imputation": {
                "config": dict(imputation_cfg),
                "report": imputation_report,
            },
            "split": walk_cfg,
            "split_params": walk_cfg,
            "model": {
                "type": model_name,
                "info": model_info,
                "artifact": model_artifact
                if isinstance(model_artifact, dict) and model_artifact.get("path")
                else None,
            },
            "config": resolved_config,
            "config_hash": resolved_config_hash,
            "folds": int(len(splits)),
            "sweep": fold_reports,
            "metrics": {
                "regression": regression,
                "classification": classification,
                "information": information,
                "trading": backtest["stats"],
                "backtest": backtest["stats"],
            },
            "artifacts": artifacts,
            "warnings": warnings,
            "files": {
                "predictions": str(predictions_path.relative_to(staging_dir)),
                "equity_table": str((staging_dir / "tables/equity.parquet").relative_to(staging_dir)),
                "equity_table_legacy": str((staging_dir / "tables/backtest_equity.parquet").relative_to(staging_dir)),
                "equity_curve": str(equity_plot_path.relative_to(staging_dir)),
                "pred_vs_true": str(pred_true_path.relative_to(staging_dir)),
            },
        }
        files_section = cast(dict[str, str], completed_summary["files"])
        if isinstance(model_artifact, dict) and model_artifact.get("path"):
            run_summary_files = dict(files_section)
            run_summary_files["model"] = model_artifact["path"]
            completed_summary["files"] = run_summary_files
        elif model_artifact is not None:
            warnings.append("omit_artifact_model_path_empty")
        if importance_names and importance_scores:
            run_summary_files = cast(dict[str, str], completed_summary["files"])
            feature_importance_files = dict(run_summary_files)
            feature_importance_files["feature_importance"] = "feature_importance.png"
            completed_summary["files"] = feature_importance_files

        if validate_manifest is not None:
            marketlab_payload = _build_marketlab_payload(completed_summary, status="complete")
            ok, errors = validate_manifest(marketlab_payload)
            if not ok:
                raise RuntimeError(f"manifest validation failed: {', '.join(errors)}")
            if validate_artifacts_exist is not None:
                ok, errors = validate_artifacts_exist(marketlab_payload, workspace_root=staging_dir)
                if not ok:
                    raise RuntimeError(f"artifact validation failed: {', '.join(errors)}")

        resolved_cfg_path = staging_dir / "config_resolved.yaml"
        resolved_cfg_path.write_text(yaml.dump(resolved_config), encoding="utf-8")
        _write_json(manifest_path, completed_summary)
        _finalize_staged_run(run_dir)
        return completed_summary
    except Exception as exc:  # noqa: BLE001
        failure_time = datetime.now(timezone.utc)
        error_path = staging_dir / "error_traceback.log"
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text(traceback.format_exc(), encoding="utf-8")
        run_summary["status"] = "failed"
        run_summary["completed_at_utc"] = failure_time.isoformat()
        run_summary["error"] = _mark_error_payload(exc, traceback_path=str(error_path.relative_to(staging_dir)))
        _write_json(manifest_path, run_summary)
        _finalize_staged_run(run_dir)
        raise


def execute_backtest_only(run_id: str, runs_root: str | Path = "runs") -> dict:
    run_dir = Path(runs_root) / run_id
    summary_path = run_dir / "run_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"run summary not found for {run_id}: {summary_path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    pred_path = None
    if isinstance(summary.get("files"), dict):
        pred_file = summary["files"].get("predictions")  # type: ignore[union-attr]
        if isinstance(pred_file, str):
            pred_path = run_dir / pred_file
    if pred_path is None:
        pred_rel = _find_artifact(summary, name="predictions")
        if pred_rel is not None:
            pred_path = run_dir / pred_rel
    if pred_path is None:
        raise FileNotFoundError(f"predictions artifact missing for run {run_id}")
    pred_df = pl.read_parquet(pred_path)
    config = summary.get("config", {})
    back_cfg = config.get("backtest", {})
    timestamp_key = "ts_utc" if "ts_utc" in pred_df.columns else "ts"

    bt = run_simple_backtest(
        timestamps=np.asarray(pred_df[timestamp_key]),
        y_true=np.nan_to_num(np.asarray(pred_df["y_true"], dtype=float)),
        y_pred=np.nan_to_num(np.asarray(pred_df["y_pred"], dtype=float)),
        threshold=float(back_cfg.get("threshold", 0.0)),
        transaction_cost=float(back_cfg.get("transaction_cost", 0.0004)),
        slippage=float(back_cfg.get("slippage", 0.0002)),
        initial_capital=float(back_cfg.get("initial_capital", 1.0)),
    )

    summary.setdefault("metrics", {})
    summary["metrics"]["backtest"] = bt["stats"]
    summary["metrics"]["trading"] = bt["stats"]

    files_section = summary.setdefault("files", {})
    files_section["equity_curve"] = "equity_curve.png"
    files_section["pred_vs_true"] = files_section.get("pred_vs_true", "pred_vs_true.png")
    files_section["equity_table"] = str((run_dir / "tables/equity.parquet").relative_to(run_dir))
    files_section["equity_table_legacy"] = str((run_dir / "tables/backtest_equity.parquet").relative_to(run_dir))
    tables_equity_path = run_dir / "tables/equity.parquet"
    tables_equity_legacy_path = run_dir / "tables/backtest_equity.parquet"
    tables_equity_path.parent.mkdir(parents=True, exist_ok=True)
    np_ts = np.asarray(pred_df[timestamp_key])
    equity_curve = _align_series(np.asarray(bt["equity_curve"], dtype=float)[1:], len(pred_df))
    equity_drawdown = _align_series(np.asarray(bt["equity_drawdown"], dtype=float)[1:], len(pred_df))
    equity_data = pl.DataFrame({"ts_utc": np_ts, "equity": equity_curve, "drawdown": equity_drawdown})
    equity_data.write_parquet(tables_equity_path)
    equity_data.write_parquet(tables_equity_legacy_path)
    artifact_entries = summary.get("artifacts")
    if isinstance(artifact_entries, list):
        replaced = False
        for idx, artifact in enumerate(artifact_entries):
            if not isinstance(artifact, dict):
                continue
            if artifact.get("name") == "equity" and artifact.get("type") == "table":
                artifact_entries[idx] = {"type": "table", "name": "equity", "path": "tables/equity.parquet"}
                replaced = True
            if artifact.get("name") == "backtest_equity" and artifact.get("type") == "table":
                artifact_entries[idx] = {"type": "table", "name": "backtest_equity", "path": "tables/backtest_equity.parquet"}
                replaced = True
        if not replaced:
            artifact_entries.append({"type": "table", "name": "equity", "path": "tables/equity.parquet"})
            artifact_entries.append({"type": "table", "name": "backtest_equity", "path": "tables/backtest_equity.parquet"})
    else:
        summary["artifacts"] = [
            {"type": "table", "name": "equity", "path": "tables/equity.parquet"},
            {"type": "table", "name": "backtest_equity", "path": "tables/backtest_equity.parquet"},
        ]

    run_equity_path = run_dir / files_section["equity_curve"]
    plot_equity_curve(
        np.asarray(pred_df[timestamp_key]),
        np.asarray(bt["equity_curve"])[1:],
        run_equity_path,
    )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
