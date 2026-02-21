#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEDGER_COLUMNS = [
    "experiment_id",
    "created_at",
    "strategy_name",
    "timeframe",
    "universe_label",
    "timerange",
    "trades",
    "profit_total_pct",
    "profit_factor",
    "max_drawdown_pct",
    "status",
    "split_label",
    "idea_spec_id",
    "robustness_score",
    "robustness_flags",
    "notes_short",
]


@dataclass
class ExperimentPaths:
    root: Path
    experiments: Path
    results: Path
    summaries: Path
    prompts: Path
    templates: Path
    logs: Path
    robustness: Path
    ledger: Path
    schema: Path
    baseline: Path


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current] + list(current.parents):
        if (candidate / ".git").exists() and (candidate / "user_data").exists():
            return candidate
        if (candidate / "freqtrade").exists() and (candidate / "freqtrade" / "user_data").exists():
            return candidate / "freqtrade"
    raise FileNotFoundError("Could not detect Freqtrade repo root from current path.")


def get_paths(repo_root: Path) -> ExperimentPaths:
    experiments = repo_root / "user_data" / "experiments"
    return ExperimentPaths(
        root=repo_root,
        experiments=experiments,
        results=experiments / "results",
        summaries=experiments / "summaries",
        prompts=experiments / "prompts",
        templates=experiments / "templates",
        logs=experiments / "logs",
        robustness=experiments / "robustness",
        ledger=experiments / "ledger.csv",
        schema=experiments / "schema.experiment_result.json",
        baseline=experiments / "baseline.json",
    )


def ensure_experiment_dirs(paths: ExperimentPaths) -> None:
    for p in [paths.experiments, paths.results, paths.summaries, paths.prompts, paths.templates, paths.logs, paths.robustness]:
        p.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str, max_len: int = 48) -> str:
    v = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return (v[:max_len]).strip("-") or "exp"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_ledger(paths: ExperimentPaths) -> list[dict[str, str]]:
    _normalize_ledger_schema(paths)
    if not paths.ledger.exists():
        return []
    with paths.ledger.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    # Backward compatibility with older ledgers that don't have new columns.
    for row in rows:
        for col in LEDGER_COLUMNS:
            row.setdefault(col, "")
    return rows


def append_ledger(paths: ExperimentPaths, row: dict[str, Any]) -> None:
    _normalize_ledger_schema(paths)
    exists = paths.ledger.exists()
    with paths.ledger.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in LEDGER_COLUMNS})


def _normalize_ledger_schema(paths: ExperimentPaths) -> None:
    """Migrate ledger header to current LEDGER_COLUMNS while preserving rows."""
    if not paths.ledger.exists():
        return
    with paths.ledger.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        current_fields = reader.fieldnames or []
        rows = list(reader)
    if current_fields == LEDGER_COLUMNS:
        return

    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append({k: row.get(k, "") for k in LEDGER_COLUMNS})

    with paths.ledger.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
        writer.writeheader()
        writer.writerows(normalized)


def get_git_commit(repo_root: Path) -> str | None:
    head = repo_root / ".git" / "HEAD"
    if not head.exists():
        return None
    try:
        import subprocess

        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            return res.stdout.strip() or None
    except Exception:
        return None
    return None


def _coerce_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _extract_main_json_from_zip(zip_path: Path) -> tuple[dict[str, Any], str]:
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".json") and not n.endswith(".meta.json") and not n.endswith("_config.json")]
        if not names:
            raise ValueError(f"No result json found inside {zip_path}")
        name = names[0]
        payload = json.loads(zf.read(name))
    return payload, name


def extract_metrics_from_backtest_zip(zip_path: Path, strategy_name: str) -> dict[str, Any]:
    payload, _ = _extract_main_json_from_zip(zip_path)
    strategy_block = payload.get("strategy", {}).get(strategy_name)
    if not strategy_block:
        keys = list(payload.get("strategy", {}).keys())
        raise KeyError(f"Strategy '{strategy_name}' not found in zip. Available: {keys}")

    results_per_pair = strategy_block.get("results_per_pair", [])
    pair_names = [p.get("key") for p in results_per_pair if p.get("key") and p.get("key") != "TOTAL"]

    metrics = {
        "trades": int(strategy_block.get("total_trades", 0) or 0),
        "trades_per_day": float(strategy_block.get("trades_per_day", 0.0) or 0.0),
        "profit_total_pct": float((strategy_block.get("profit_total", 0.0) or 0.0) * 100.0),
        "winrate_pct": float((strategy_block.get("winrate", 0.0) or 0.0) * 100.0),
        "profit_factor": _coerce_float(strategy_block.get("profit_factor")),
        "max_drawdown_pct": float((strategy_block.get("max_drawdown_account", 0.0) or 0.0) * 100.0),
    }

    return {
        "metrics": metrics,
        "pairs_count": len(pair_names),
        "pair_names": pair_names,
        "strategy_block": strategy_block,
        "payload": payload,
    }


def parse_metrics_from_text(text: str) -> dict[str, Any]:
    patterns = {
        "trades_per_day": r"Total/Daily Avg Trades\s*[│:]+\s*([0-9]+)\s*/\s*([0-9]+(?:\.[0-9]+)?)",
        "profit_total_pct": r"Total profit %\s*[│:]+\s*([-+]?[0-9]+(?:\.[0-9]+)?)%",
        "winrate_pct": r"Win%\s*[│:]+\s*([0-9]+(?:\.[0-9]+)?)",
        "profit_factor": r"Profit factor\s*[│:]+\s*([-+]?[0-9]+(?:\.[0-9]+)?)",
        "max_drawdown_pct": r"Absolute drawdown\s*[│:]+\s*[-+]?[0-9]+(?:\.[0-9]+)?\s+\w+\s*\(([0-9]+(?:\.[0-9]+)?)%\)",
    }

    trades = 0
    trades_per_day = 0.0
    m = re.search(patterns["trades_per_day"], text, flags=re.IGNORECASE)
    if m:
        trades = int(m.group(1))
        trades_per_day = float(m.group(2))

    def pick_float(pattern_key: str) -> float | None:
        mm = re.search(patterns[pattern_key], text, flags=re.IGNORECASE)
        return float(mm.group(1)) if mm else None

    metrics = {
        "trades": trades,
        "trades_per_day": trades_per_day,
        "profit_total_pct": pick_float("profit_total_pct") or 0.0,
        "winrate_pct": pick_float("winrate_pct") or 0.0,
        "profit_factor": pick_float("profit_factor"),
        "max_drawdown_pct": pick_float("max_drawdown_pct") or 0.0,
    }
    return metrics


def load_config_pairs_count(config_path: Path) -> tuple[int, list[str]]:
    if not config_path.exists():
        return 0, []
    data = load_json(config_path)
    pairs = data.get("exchange", {}).get("pair_whitelist", [])
    return len(pairs), pairs


def format_metrics_markdown(metrics: dict[str, Any]) -> str:
    pf = metrics.get("profit_factor")
    pf_txt = "null" if pf is None else f"{pf:.3f}"
    return "\n".join(
        [
            "| Metric | Value |",
            "|---|---:|",
            f"| trades | {int(metrics.get('trades', 0))} |",
            f"| trades_per_day | {float(metrics.get('trades_per_day', 0.0)):.4f} |",
            f"| profit_total_pct | {float(metrics.get('profit_total_pct', 0.0)):.4f}% |",
            f"| winrate_pct | {float(metrics.get('winrate_pct', 0.0)):.4f}% |",
            f"| profit_factor | {pf_txt} |",
            f"| max_drawdown_pct | {float(metrics.get('max_drawdown_pct', 0.0)):.4f}% |",
        ]
    )
