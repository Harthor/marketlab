#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from report_utils import find_repo_root
except ModuleNotFoundError:  # pragma: no cover - fallback for package-style imports
    from user_data.scripts.report_utils import find_repo_root


@dataclass(frozen=True)
class UIPaths:
    repo_root: Path
    experiments_root: Path
    results_dir: Path
    summaries_dir: Path
    prompts_dir: Path
    logs_dir: Path
    ledger_csv: Path
    baseline_json: Path
    status_json: Path


def get_ui_paths(start: Path | None = None) -> UIPaths:
    repo_root = find_repo_root(start or Path(__file__).resolve())
    experiments = repo_root / "user_data" / "experiments"
    return UIPaths(
        repo_root=repo_root,
        experiments_root=experiments,
        results_dir=experiments / "results",
        summaries_dir=experiments / "summaries",
        prompts_dir=experiments / "prompts",
        logs_dir=experiments / "logs",
        ledger_csv=experiments / "ledger.csv",
        baseline_json=experiments / "baseline.json",
        status_json=experiments / "status.json",
    )


def safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_ledger_df(paths: UIPaths) -> pd.DataFrame:
    if not paths.ledger_csv.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(paths.ledger_csv)
    except Exception:
        return pd.DataFrame()

    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    for col in ["trades", "profit_total_pct", "profit_factor", "max_drawdown_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_latest_ledger_row(df: pd.DataFrame) -> dict[str, Any] | None:
    if df.empty:
        return None
    if "created_at" in df.columns and df["created_at"].notna().any():
        row = df.sort_values("created_at", ascending=False).iloc[0]
    else:
        row = df.iloc[-1]
    return row.to_dict()


def load_experiment_result(paths: UIPaths, experiment_id: str) -> dict[str, Any] | None:
    return safe_read_json(paths.results_dir / f"{experiment_id}.json")


def list_prompt_files(paths: UIPaths) -> list[Path]:
    if not paths.prompts_dir.exists():
        return []
    return sorted(paths.prompts_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)


def list_log_files(paths: UIPaths) -> list[Path]:
    if not paths.logs_dir.exists():
        return []
    return sorted(paths.logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_text_head(path: Path, lines: int = 20) -> str:
    content = read_text_file(path).splitlines()
    return "\n".join(content[:lines])


def tail_text_file(path: Path, lines: int = 200) -> str:
    content = read_text_file(path).splitlines()
    return "\n".join(content[-lines:])


def get_baseline(paths: UIPaths) -> dict[str, Any] | None:
    return safe_read_json(paths.baseline_json)


def get_status(paths: UIPaths) -> dict[str, Any]:
    default = {
        "state": "idle",
        "current_task": None,
        "progress": 0,
        "updated_at": None,
    }
    payload = safe_read_json(paths.status_json)
    if not payload:
        return default
    out = dict(default)
    out.update({k: payload.get(k) for k in default.keys() if k in payload})
    return out


def latest_prompt_path(paths: UIPaths) -> Path | None:
    prompts = list_prompt_files(paths)
    return prompts[0] if prompts else None


def format_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def compare_result_vs_baseline(
    experiment: dict[str, Any] | None,
    baseline_result: dict[str, Any] | None,
) -> dict[str, float] | None:
    if not experiment or not baseline_result:
        return None

    e_m = experiment.get("metrics", {})
    b_m = baseline_result.get("metrics", {})
    try:
        e_pf = float(e_m.get("profit_factor"))
        b_pf = float(b_m.get("profit_factor"))
        e_dd = float(e_m.get("max_drawdown_pct", 0.0))
        b_dd = float(b_m.get("max_drawdown_pct", 0.0))
    except Exception:
        return None

    return {
        "delta_pf": e_pf - b_pf,
        "delta_dd_pct": e_dd - b_dd,
    }
