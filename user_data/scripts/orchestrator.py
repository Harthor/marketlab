#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collect_backtest import _build_experiment_result
from decision_rules import decide_next_step
from prompt_templates import render_prompt
from report_utils import (
    ensure_experiment_dirs,
    find_repo_root,
    get_paths,
    load_json,
    read_ledger,
    utc_now_compact,
    write_json,
)


INGEST_FIELDS = [
    ("--strategy", {"required": True}),
    ("--family", {"default": "unknown"}),
    ("--config", {"required": True}),
    ("--timeframe", {"required": True}),
    ("--timerange", {"required": True}),
    ("--universe", {"required": True}),
    ("--market", {"choices": ["spot", "futures"], "required": True}),
    ("--split-label", {"default": None}),
    ("--oos", {"action": "store_true", "default": None}),
    ("--fee-sensitivity-tested", {"action": "store_true", "default": False}),
    ("--fee-delta-pct", {"type": float, "default": None}),
    ("--idea-spec-id", {"default": None}),
    ("--robustness-report", {"default": None}),
    ("--command-run", {"nargs": "*", "default": []}),
]


def _configure_logger(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / f"orchestrator_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"
    logger = logging.getLogger("orchestrator")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def _as_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _as_int(v: Any) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except Exception:
        return None


def _get_result_by_id(paths, experiment_id: str) -> dict[str, Any]:
    p = paths.results / f"{experiment_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"Experiment result not found: {p}")
    return load_json(p)


def _latest_result(paths) -> dict[str, Any]:
    files = sorted(paths.results.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("No experiment results found. Run ingest first.")
    return load_json(files[0])


def _load_baseline_result(paths) -> dict[str, Any] | None:
    if not paths.baseline.exists():
        return None
    baseline_ref = load_json(paths.baseline)
    exp_id = baseline_ref.get("experiment_id")
    if not exp_id:
        return None
    candidate = paths.results / f"{exp_id}.json"
    if not candidate.exists():
        return None
    return load_json(candidate)


def _default_preferences() -> dict[str, Any]:
    return {
        "default_timeframe": "1h",
        "prioritize_universe_expansion": True,
        "avoid_lower_timeframes": True,
        "prefer_scoring_pure": True,
    }


def _load_preferences(paths) -> dict[str, Any]:
    pref_path = paths.experiments / "preferences.json"
    if not pref_path.exists():
        return _default_preferences()
    try:
        raw = load_json(pref_path)
        out = _default_preferences()
        out.update({k: raw.get(k) for k in out.keys() if k in raw})
        return out
    except Exception:
        return _default_preferences()


def _default_thresholds() -> dict[str, Any]:
    return {
        "min_trades_for_confidence": 80,
        "low_sample_trades": 30,
        "discard_pf_threshold": 0.8,
        "high_dd_pct_for_discard": 4.0,
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


def _run_recommend(paths, result: dict[str, Any]) -> dict[str, Any]:
    ledger = read_ledger(paths)
    baseline_result = _load_baseline_result(paths)
    preferences = _load_preferences(paths)
    thresholds = _load_thresholds(paths)
    recommendation = decide_next_step(
        result,
        ledger,
        baseline_result=baseline_result,
        preferences=preferences,
        thresholds=thresholds,
    )
    prompt_path = render_prompt(paths, result, recommendation, preferences=preferences)

    output = {
        "experiment_id": result["experiment_id"],
        "recommendation_code": recommendation["recommendation_code"],
        "recommendation_text": recommendation["recommendation_text"],
        "next_action_type": recommendation["next_action_type"],
        "prompt_file": str(prompt_path),
    }
    return output


def cmd_ingest(args: argparse.Namespace) -> int:
    result = _build_experiment_result(args)
    repo_root = find_repo_root(Path.cwd())
    out = {
        "experiment_id": result["experiment_id"],
        "status": result["status"],
        "result_json": str(repo_root / "user_data" / "experiments" / "results" / f"{result['experiment_id']}.json"),
        "summary_md": result["artifacts"]["summary_md"],
    }
    print(json.dumps(out, indent=2, ensure_ascii=True))
    return 0


def cmd_recommend(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(Path.cwd())
    paths = get_paths(repo_root)
    ensure_experiment_dirs(paths)

    result = _get_result_by_id(paths, args.experiment_id) if args.experiment_id else _latest_result(paths)
    output = _run_recommend(paths, result)
    print(json.dumps(output, indent=2, ensure_ascii=True))
    return 0


def cmd_ingest_and_recommend(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(Path.cwd())
    paths = get_paths(repo_root)
    ensure_experiment_dirs(paths)

    result = _build_experiment_result(args)
    recommendation = _run_recommend(paths, result)
    output = {
        "experiment_id": result["experiment_id"],
        "status": result["status"],
        "result_json": str(paths.results / f"{result['experiment_id']}.json"),
        "summary_md": result["artifacts"]["summary_md"],
        "prompt_file": recommendation["prompt_file"],
        "recommendation_code": recommendation["recommendation_code"],
        "recommendation_text": recommendation["recommendation_text"],
    }
    print(json.dumps(output, indent=2, ensure_ascii=True))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(Path.cwd())
    paths = get_paths(repo_root)
    ledger = read_ledger(paths)

    if not ledger:
        print("No experiments in ledger yet.")
        return 0

    latest = ledger[-args.last :]
    print(f"Last {len(latest)} experiments:")
    for row in latest:
        print(
            f"- {row['experiment_id']} | {row['strategy_name']} | tf={row['timeframe']} | "
            f"u={row['universe_label']} | trades={row['trades']} | PF={row['profit_factor']} | "
            f"PnL%={row['profit_total_pct']} | {row['status']} | {row.get('notes_short', '')}"
        )

    print("\nActive baseline:")
    baseline_result = _load_baseline_result(paths)
    if baseline_result:
        bm = baseline_result.get("metrics", {})
        print(
            f"- {baseline_result.get('experiment_id')} | {baseline_result.get('strategy_name')} | "
            f"tf={baseline_result.get('timeframe')} | u={baseline_result.get('universe_label')} | "
            f"PF={bm.get('profit_factor')} | DD%={bm.get('max_drawdown_pct')}"
        )
    else:
        print("- none")

    print(f"\nTop 5 by PF (min trades >= {args.min_trades}):")
    top_rows: list[tuple[float, dict[str, str]]] = []
    for row in ledger:
        pf = _as_float(row.get("profit_factor"))
        trades = _as_int(row.get("trades"))
        if pf is None or trades is None or trades < args.min_trades:
            continue
        top_rows.append((pf, row))
    top_rows.sort(key=lambda x: x[0], reverse=True)
    for pf, row in top_rows[:5]:
        print(
            f"- PF={pf:.3f} | {row['experiment_id']} | {row['strategy_name']} | tf={row['timeframe']} | "
            f"u={row['universe_label']} | trades={row['trades']} | PnL%={row['profit_total_pct']}"
        )
    if not top_rows:
        print("- no rows matching min_trades filter")

    print("\nSummary by strategy/timeframe/universe:")
    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in ledger:
        pf = _as_float(row.get("profit_factor"))
        if pf is None:
            continue
        key = (row.get("strategy_name", ""), row.get("timeframe", ""), row.get("universe_label", ""))
        grouped[key].append(pf)

    sorted_groups = sorted(
        grouped.items(),
        key=lambda kv: (sum(kv[1]) / len(kv[1])) if kv[1] else -999.0,
        reverse=True,
    )
    for (strategy, tf, universe), pfs in sorted_groups:
        avg_pf = sum(pfs) / len(pfs)
        print(f"- {strategy} | {tf} | {universe} => avg PF={avg_pf:.3f}, tests={len(pfs)}")

    return 0


def cmd_baseline(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(Path.cwd())
    paths = get_paths(repo_root)
    result = _get_result_by_id(paths, args.experiment_id)
    payload = {
        "experiment_id": result["experiment_id"],
        "strategy_name": result.get("strategy_name"),
        "timeframe": result.get("timeframe"),
        "universe_label": result.get("universe_label"),
        "marked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    write_json(paths.baseline, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(Path.cwd())
    paths = get_paths(repo_root)

    rows: list[dict[str, Any]] = []
    for exp_id in args.ids:
        obj = _get_result_by_id(paths, exp_id)
        m = obj.get("metrics", {})
        rows.append(
            {
                "experiment_id": exp_id,
                "strategy": obj.get("strategy_name"),
                "timeframe": obj.get("timeframe"),
                "universe": obj.get("universe_label"),
                "trades": m.get("trades"),
                "trades_per_day": m.get("trades_per_day"),
                "profit_total_pct": m.get("profit_total_pct"),
                "winrate_pct": m.get("winrate_pct"),
                "profit_factor": m.get("profit_factor"),
                "max_drawdown_pct": m.get("max_drawdown_pct"),
            }
        )

    lines = [
        "| experiment_id | strategy | timeframe | universe | trades | trades/day | profit % | winrate % | PF | max DD % |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['experiment_id']} | {r['strategy']} | {r['timeframe']} | {r['universe']} | {r['trades']} | "
            f"{float(r['trades_per_day'] or 0):.4f} | {float(r['profit_total_pct'] or 0):.4f} | "
            f"{float(r['winrate_pct'] or 0):.4f} | {r['profit_factor']} | {float(r['max_drawdown_pct'] or 0):.4f} |"
        )

    table = "\n".join(lines)
    out_path = paths.summaries / f"compare_{utc_now_compact()}.md"
    out_path.write_text(table + "\n", encoding="utf-8")
    print(table)
    print(f"\nSaved: {out_path}")
    return 0


def _add_ingest_args(parser: argparse.ArgumentParser) -> None:
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-meta")
    src.add_argument("--from-text")
    for key, kwargs in INGEST_FIELDS:
        parser.add_argument(key, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Experiment orchestrator for Freqtrade backtest workflow.")
    sub = p.add_subparsers(dest="cmd", required=True)

    ingest = sub.add_parser("ingest", help="Ingest one backtest result into experiment ledger")
    _add_ingest_args(ingest)
    ingest.set_defaults(func=cmd_ingest)

    ingest_rec = sub.add_parser(
        "ingest-and-recommend",
        help="Ingest one result, apply decision rules, and generate next prompt",
    )
    _add_ingest_args(ingest_rec)
    ingest_rec.set_defaults(func=cmd_ingest_and_recommend)

    rec = sub.add_parser("recommend", help="Apply decision rules and generate next prompt")
    rec.add_argument("--experiment-id", default=None)
    rec.set_defaults(func=cmd_recommend)

    status = sub.add_parser("status", help="Show ledger summary and baseline candidate")
    status.add_argument("--last", type=int, default=10)
    status.add_argument("--min-trades", type=int, default=10)
    status.set_defaults(func=cmd_status)

    baseline = sub.add_parser("baseline", help="Mark one experiment as baseline")
    baseline.add_argument("--experiment-id", required=True)
    baseline.set_defaults(func=cmd_baseline)

    compare = sub.add_parser("compare", help="Compare multiple experiment ids")
    compare.add_argument("--ids", nargs="+", required=True)
    compare.set_defaults(func=cmd_compare)

    return p


def main() -> int:
    repo_root = find_repo_root(Path.cwd())
    paths = get_paths(repo_root)
    ensure_experiment_dirs(paths)
    logger = _configure_logger(paths.logs)

    parser = build_parser()
    args = parser.parse_args()
    logger.info("Running command: %s", args.cmd)
    rc = args.func(args)
    logger.info("Command %s finished with rc=%s", args.cmd, rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
