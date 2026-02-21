#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from decision_rules import decide_next_step
from report_utils import find_repo_root, get_paths, load_json, read_ledger


def _default_thresholds() -> dict[str, Any]:
    return {
        "min_trades_for_confidence": 80,
        "low_sample_trades": 30,
        "baseline_candidate_min_pf": 1.05,
        "baseline_candidate_max_dd": 1.5,
    }


def _load_thresholds(paths) -> dict[str, Any]:
    cfg = paths.experiments / "research_thresholds.json"
    out = _default_thresholds()
    if not cfg.exists():
        return out
    try:
        raw = load_json(cfg)
        if isinstance(raw, dict):
            out.update({k: raw.get(k) for k in out.keys() if k in raw})
    except Exception:
        pass
    return out


def _load_preferences(paths) -> dict[str, Any]:
    pref = paths.experiments / "preferences.json"
    if not pref.exists():
        return {
            "default_timeframe": "1h",
            "prioritize_universe_expansion": True,
            "avoid_lower_timeframes": True,
            "prefer_scoring_pure": True,
        }
    try:
        return load_json(pref)
    except Exception:
        return {
            "default_timeframe": "1h",
            "prioritize_universe_expansion": True,
            "avoid_lower_timeframes": True,
            "prefer_scoring_pure": True,
        }


def _result_rows(paths) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in sorted(paths.results.glob("*.json")):
        try:
            obj = load_json(p)
        except Exception:
            continue
        if not isinstance(obj, dict) or "metrics" not in obj:
            continue
        obj["_path"] = str(p)
        rows.append(obj)
    return rows


def _class_bucket(row: dict[str, Any], thresholds: dict[str, Any]) -> str:
    m = row.get("metrics", {})
    trades = int(m.get("trades", 0) or 0)
    pf = m.get("profit_factor")
    dd = float(m.get("max_drawdown_pct", 0.0) or 0.0)
    if not isinstance(pf, (int, float)):
        return "unknown"
    if trades < int(thresholds["low_sample_trades"]):
        return "low_sample"
    if pf > 1 and trades >= int(thresholds["min_trades_for_confidence"]) and dd <= float(thresholds["baseline_candidate_max_dd"]):
        return "good"
    if pf <= 1 and trades >= int(thresholds["min_trades_for_confidence"]):
        return "bad"
    return "mixed"


def _to_dataset_row(
    row: dict[str, Any],
    recommendation_code: str,
) -> dict[str, Any]:
    m = row.get("metrics", {})
    rv = row.get("robustness_validation", {}) or {}
    return {
        "experiment_id": row.get("experiment_id"),
        "strategy": row.get("strategy_name"),
        "family": row.get("strategy_family"),
        "timeframe": row.get("timeframe"),
        "universe": row.get("universe_label"),
        "trades": int(m.get("trades", 0) or 0),
        "trades_per_day": float(m.get("trades_per_day", 0.0) or 0.0),
        "profit_pct": float(m.get("profit_total_pct", 0.0) or 0.0),
        "pf": m.get("profit_factor"),
        "max_dd_pct": float(m.get("max_drawdown_pct", 0.0) or 0.0),
        "status": row.get("status"),
        "recommendation_code": recommendation_code,
        "robustness_score": rv.get("robustness_score"),
        "robustness_flags": ",".join(rv.get("flags", []) or []),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _run_backfill(
    repo_root: Path,
    rows: list[dict[str, Any]],
    limit: int,
    filter_tf: str,
    filter_strategy: str,
    write_back: bool,
) -> dict[str, Any]:
    pending = []
    for r in rows:
        if filter_tf and str(r.get("timeframe")) != filter_tf:
            continue
        if filter_strategy and str(r.get("strategy_name")) != filter_strategy:
            continue
        rv = r.get("robustness_validation", {}) or {}
        if rv.get("report_json"):
            continue
        pending.append(r)
    if limit > 0:
        pending = pending[:limit]

    processed: list[str] = []
    for r in pending:
        exp_id = str(r.get("experiment_id"))
        cmd = [
            str(repo_root / ".env" / "bin" / "python"),
            str(repo_root / "user_data" / "scripts" / "anti_smoke_validator.py"),
            "--experiment-id",
            exp_id,
            "--dry-run",
        ]
        if write_back:
            cmd.append("--write-back")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            processed.append(exp_id)

    return {"candidates": len(pending), "processed": len(processed), "processed_ids": processed}


def _scorecard(rows: list[dict[str, Any]], thresholds: dict[str, Any]) -> dict[str, Any]:
    severe = {
        "FAIL_LOOKAHEAD",
        "FAIL_RECURSIVE",
        "TOO_CONCENTRATED_TOP1",
        "TOO_CONCENTRATED_TOP3",
        "PAIR_DEPENDENCY_RISK",
        "COST_FRAGILE",
    }
    buckets = defaultdict(list)
    for r in rows:
        b = _class_bucket(r, thresholds)
        buckets[b].append(r)

    def has_flag(r: dict[str, Any], flag: str) -> bool:
        rv = r.get("robustness_validation", {}) or {}
        return flag in (rv.get("flags", []) or [])

    def has_severe(r: dict[str, Any]) -> bool:
        rv = r.get("robustness_validation", {}) or {}
        flags = set(rv.get("flags", []) or [])
        return bool(flags.intersection(severe))

    good = buckets["good"]
    bad = buckets["bad"]
    low_sample = buckets["low_sample"]

    good_robust = sum(1 for r in good if has_flag(r, "ROBUST_CANDIDATE"))
    bad_severe = sum(1 for r in bad if has_severe(r))
    fp = sum(1 for r in bad if has_flag(r, "ROBUST_CANDIDATE"))
    fn = sum(1 for r in good if not has_flag(r, "ROBUST_CANDIDATE"))

    dist = {"good": [], "bad": [], "low_sample": []}
    for name, items in [("good", good), ("bad", bad), ("low_sample", low_sample)]:
        for r in items:
            rv = r.get("robustness_validation", {}) or {}
            sc = rv.get("robustness_score")
            if isinstance(sc, (int, float)):
                dist[name].append(float(sc))

    def avg(vals: list[float]) -> float | None:
        return (sum(vals) / len(vals)) if vals else None

    return {
        "bucket_counts": {k: len(v) for k, v in buckets.items()},
        "good_marked_robust_candidate": {"count": good_robust, "total": len(good)},
        "bad_marked_with_severe_flags": {"count": bad_severe, "total": len(bad)},
        "false_positives_heuristic": fp,
        "false_negatives_heuristic": fn,
        "robustness_score_distribution": {
            "good_avg": avg(dist["good"]),
            "bad_avg": avg(dist["bad"]),
            "low_sample_avg": avg(dist["low_sample"]),
        },
    }


def _render_scorecard_md(scorecard: dict[str, Any], thresholds: dict[str, Any]) -> str:
    b = scorecard["bucket_counts"]
    g = scorecard["good_marked_robust_candidate"]
    bs = scorecard["bad_marked_with_severe_flags"]
    d = scorecard["robustness_score_distribution"]
    lines = [
        "# Calibration Scorecard",
        "",
        "## Buckets",
        f"- good: {b.get('good', 0)}",
        f"- bad: {b.get('bad', 0)}",
        f"- low_sample: {b.get('low_sample', 0)}",
        f"- mixed: {b.get('mixed', 0)}",
        "",
        "## Heuristic Classification Quality",
        f"- Good marked ROBUST_CANDIDATE: {g['count']}/{g['total']}",
        f"- Bad marked severe flags: {bs['count']}/{bs['total']}",
        f"- False positives (bad but robust): {scorecard['false_positives_heuristic']}",
        f"- False negatives (good not robust): {scorecard['false_negatives_heuristic']}",
        "",
        "## Robustness Score Distribution",
        f"- good avg: {d['good_avg']}",
        f"- bad avg: {d['bad_avg']}",
        f"- low_sample avg: {d['low_sample_avg']}",
        "",
        "## Thresholds Used",
        f"- min_trades_for_confidence: {thresholds['min_trades_for_confidence']}",
        f"- low_sample_trades: {thresholds['low_sample_trades']}",
        f"- baseline_candidate_min_pf: {thresholds['baseline_candidate_min_pf']}",
        f"- baseline_candidate_max_dd: {thresholds['baseline_candidate_max_dd']}",
        "",
        "## Suggested Adjustments",
        "- If many good candidates are not marked robust, lower `robust_candidate_min_score` slightly.",
        "- If many bad candidates pass robust, tighten concentration and cost fragility thresholds.",
        "- If low-sample dominates, raise sample generation priority before new ideas.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="Calibrate pre-screen + anti-humo tools from historical experiments.")
    p.add_argument("--out-dir", default="user_data/research/calibration")
    p.add_argument("--backfill-robustness", action="store_true", default=False)
    p.add_argument("--write-back", action="store_true", default=False)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--filter-timeframe", default="")
    p.add_argument("--filter-strategy", default="")
    args = p.parse_args()

    repo_root = find_repo_root(Path.cwd())
    paths = get_paths(repo_root)
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (repo_root / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _result_rows(paths)
    thresholds = _load_thresholds(paths)
    preferences = _load_preferences(paths)
    ledger = read_ledger(paths)
    baseline_obj = None
    if paths.baseline.exists():
        try:
            b = load_json(paths.baseline).get("experiment_id")
            if b:
                bp = paths.results / f"{b}.json"
                if bp.exists():
                    baseline_obj = load_json(bp)
        except Exception:
            baseline_obj = None

    backfill_report = None
    if args.backfill_robustness:
        backfill_report = _run_backfill(
            repo_root=repo_root,
            rows=rows,
            limit=args.limit,
            filter_tf=args.filter_timeframe.strip(),
            filter_strategy=args.filter_strategy.strip(),
            write_back=bool(args.write_back),
        )
        rows = _result_rows(paths)

    dataset_rows: list[dict[str, Any]] = []
    for r in rows:
        rec = decide_next_step(r, ledger, baseline_result=baseline_obj, preferences=preferences, thresholds=thresholds)
        dataset_rows.append(_to_dataset_row(r, rec["recommendation_code"]))

    dataset_json = out_dir / "calibration_dataset.json"
    dataset_csv = out_dir / "calibration_dataset.csv"
    dataset_json.write_text(json.dumps(dataset_rows, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    _write_csv(dataset_csv, dataset_rows)

    scorecard = _scorecard(rows, thresholds)
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "dataset_rows": len(dataset_rows),
        "scorecard": scorecard,
        "thresholds_used": thresholds,
        "backfill": backfill_report,
    }
    score_json = out_dir / "calibration_scorecard.json"
    score_md = out_dir / "calibration_scorecard.md"
    score_json.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    score_md.write_text(_render_scorecard_md(scorecard, thresholds), encoding="utf-8")

    print(
        json.dumps(
            {
                "dataset_csv": str(dataset_csv),
                "dataset_json": str(dataset_json),
                "scorecard_md": str(score_md),
                "scorecard_json": str(score_json),
                "backfill": backfill_report,
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
