#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from infra_retry import detect_infra_failure, run_cmd as infra_run_cmd
from report_utils import ensure_experiment_dirs, find_repo_root, get_paths, load_json, write_json


def _default_thresholds() -> dict[str, Any]:
    return {
        "min_trades_for_confidence": 80,
        "low_sample_trades": 30,
        "concentration_top1_pct": 45.0,
        "concentration_top3_pct": 75.0,
        "pair_dependency_topn": 5,
        "pair_dependency_topn_pct": 90.0,
        "cost_fragile_pf_drop_threshold": 0.2,
        "cost_fragile_fee50_below_pf": 1.0,
        "robust_candidate_min_score": 70.0,
    }


def _load_thresholds(paths) -> dict[str, Any]:
    out = _default_thresholds()
    cfg = paths.experiments / "research_thresholds.json"
    if not cfg.exists():
        return out
    try:
        obj = load_json(cfg)
        if isinstance(obj, dict):
            out.update({k: obj.get(k) for k in out.keys() if k in obj})
    except Exception:
        pass
    return out


def _result_by_id(paths, experiment_id: str) -> dict[str, Any]:
    p = paths.results / f"{experiment_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"Result not found: {p}")
    return load_json(p)


def _load_strategy_block(result: dict[str, Any]) -> dict[str, Any] | None:
    strategy_name = result.get("strategy_name")
    export = result.get("artifacts", {}).get("backtest_export_json")
    if not export:
        return None
    p = Path(export)
    if not p.exists():
        return None
    payload = load_json(p)
    return payload.get("strategy", {}).get(strategy_name)


def _pair_concentration(strategy_block: dict[str, Any] | None, thresholds: dict[str, Any]) -> dict[str, Any]:
    if not strategy_block:
        return {
            "top1_share_pct": None,
            "top3_share_pct": None,
            "topn_share_pct": None,
            "top_n": int(thresholds.get("pair_dependency_topn", 5)),
            "flags": ["MISSING_PAIR_BREAKDOWN"],
            "note": "missing_strategy_block",
        }

    rows = [r for r in strategy_block.get("results_per_pair", []) if r.get("key") and r.get("key") != "TOTAL"]
    if not rows:
        return {
            "top1_share_pct": None,
            "top3_share_pct": None,
            "topn_share_pct": None,
            "top_n": int(thresholds.get("pair_dependency_topn", 5)),
            "flags": ["MISSING_PAIR_BREAKDOWN"],
            "note": "no_pair_rows",
        }

    weighted: list[tuple[str, float, float]] = []
    for r in rows:
        key = str(r.get("key"))
        abs_pnl = float(r.get("profit_total_abs", 0.0) or 0.0)
        pct_pnl = float(r.get("profit_total_pct", 0.0) or 0.0)
        contribution = abs_pnl if abs_pnl > 0 else max(0.0, pct_pnl)
        weighted.append((key, contribution, pct_pnl))

    positives = [(k, c, p) for (k, c, p) in weighted if c > 0]
    if not positives:
        return {
            "top1_share_pct": 100.0,
            "top3_share_pct": 100.0,
            "topn_share_pct": 100.0,
            "top_n": int(thresholds.get("pair_dependency_topn", 5)),
            "top_pairs": [],
            "bottom_pairs": sorted([(k, p) for (k, _, p) in weighted], key=lambda x: x[1])[:5],
            "flags": ["PAIR_DEPENDENCY_RISK"],
            "note": "no_positive_contribution",
        }

    positives.sort(key=lambda x: x[1], reverse=True)
    total = sum(x[1] for x in positives) or 1.0
    top_n = int(thresholds.get("pair_dependency_topn", 5))
    top1 = (positives[0][1] / total) * 100.0
    top3 = (sum(x[1] for x in positives[:3]) / total) * 100.0
    topn = (sum(x[1] for x in positives[:top_n]) / total) * 100.0

    flags: list[str] = []
    if top1 >= float(thresholds.get("concentration_top1_pct", 45.0)):
        flags.append("TOO_CONCENTRATED_TOP1")
    if top3 >= float(thresholds.get("concentration_top3_pct", 75.0)):
        flags.append("TOO_CONCENTRATED_TOP3")
    if topn >= float(thresholds.get("pair_dependency_topn_pct", 90.0)):
        flags.append("PAIR_DEPENDENCY_RISK")

    bottom_pairs = sorted([(k, p) for (k, _, p) in weighted], key=lambda x: x[1])[:5]
    top_pairs = [(k, p) for (k, _, p) in sorted(weighted, key=lambda x: x[2], reverse=True)[:5]]
    return {
        "top1_share_pct": top1,
        "top3_share_pct": top3,
        "topn_share_pct": topn,
        "top_n": top_n,
        "top_pairs": top_pairs,
        "bottom_pairs": bottom_pairs,
        "flags": flags,
        "note": "ok",
    }


def _base_universe_label(label: str) -> str:
    return re.sub(r"_fee.*$", "", label)


def _collect_fee_rows(paths, result: dict[str, Any]) -> list[dict[str, Any]]:
    strategy = result.get("strategy_name")
    timeframe = result.get("timeframe")
    config = result.get("config_path")
    timerange = result.get("timerange")
    base_universe = _base_universe_label(str(result.get("universe_label", "")))

    rows: list[dict[str, Any]] = []
    for p in paths.results.glob("*.json"):
        try:
            obj = load_json(p)
        except Exception:
            continue
        if obj.get("strategy_name") != strategy:
            continue
        if obj.get("timeframe") != timeframe or obj.get("config_path") != config or obj.get("timerange") != timerange:
            continue
        if not str(obj.get("universe_label", "")).startswith(base_universe):
            continue
        rb = obj.get("robustness", {})
        fd = rb.get("fee_delta_pct")
        if fd is None:
            continue
        rows.append(
            {
                "experiment_id": obj.get("experiment_id"),
                "fee_delta_pct": float(fd),
                "profit_factor": obj.get("metrics", {}).get("profit_factor"),
                "profit_total_pct": obj.get("metrics", {}).get("profit_total_pct"),
                "max_drawdown_pct": obj.get("metrics", {}).get("max_drawdown_pct"),
            }
        )
    rows.sort(key=lambda x: x["fee_delta_pct"])
    return rows


def _run_cmd(cmd: list[str]) -> dict[str, Any]:
    detail = infra_run_cmd(cmd, output_tail_chars=1200)
    return {"cmd": detail["cmd"], "returncode": detail["returncode"], "output_tail": detail["output_tail"]}


def _resolve_freqtrade_cmd(repo_root: Path) -> str:
    local = repo_root / ".env" / "bin" / "freqtrade"
    if local.exists():
        return str(local)
    return "freqtrade"


def _retry_lookahead_with_temp_config(
    repo_root: Path, original_cmd: list[str], original_config: str, error_output: str
) -> tuple[dict[str, Any], str | None]:
    entry_marker = 'Market entry orders require entry_pricing.price_side = "other".'
    exit_marker = 'Market exit orders require exit_pricing.price_side = "other".'
    if entry_marker not in error_output and exit_marker not in error_output:
        return {}, None

    cfg_path = Path(original_config)
    if not cfg_path.is_absolute():
        cfg_path = (repo_root / cfg_path).resolve()
    if not cfg_path.exists():
        return {}, None

    cfg_obj = load_json(cfg_path)
    entry_pricing = cfg_obj.setdefault("entry_pricing", {})
    if not isinstance(entry_pricing, dict):
        entry_pricing = {}
        cfg_obj["entry_pricing"] = entry_pricing
    entry_pricing["price_side"] = "other"
    exit_pricing = cfg_obj.setdefault("exit_pricing", {})
    if not isinstance(exit_pricing, dict):
        exit_pricing = {}
        cfg_obj["exit_pricing"] = exit_pricing
    exit_pricing["price_side"] = "other"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".lookahead.tmp.json", prefix="anti_smoke_", delete=False, encoding="utf-8"
    ) as tf:
        json.dump(cfg_obj, tf, indent=2, ensure_ascii=True)
        tf.write("\n")
        tmp_cfg = tf.name

    retry_cmd = list(original_cmd)
    if "-c" in retry_cmd:
        idx = retry_cmd.index("-c")
        if idx + 1 < len(retry_cmd):
            retry_cmd[idx + 1] = tmp_cfg
    detail = _run_cmd(retry_cmd)
    detail["retry_reason"] = "entry_pricing.price_side override to other"
    return detail, tmp_cfg


def main() -> int:
    p = argparse.ArgumentParser(description="Anti-humo validator for backtest results.")
    p.add_argument("--experiment-id", default="", help="Experiment result id from experiments/results")
    p.add_argument("--result-json", default="", help="Path to experiment result json")
    p.add_argument("--min-trades", type=int, default=None, help="Override min trades threshold")
    p.add_argument("--run-lookahead", action="store_true", default=False)
    p.add_argument("--run-recursive", action="store_true", default=False)
    p.add_argument("--dry-run", action="store_true", default=False)
    p.add_argument("--retry-attempts", type=int, default=1, help="Retry attempts for infra failures.")
    p.add_argument("--retry-delay-sec", type=float, default=2.0, help="Base delay (seconds) between retries.")
    p.add_argument("--out", default="", help="Output report path")
    p.add_argument("--write-back", action="store_true", default=False, help="Write robustness block back to result json")
    args = p.parse_args()

    repo_root = find_repo_root(Path.cwd())
    paths = get_paths(repo_root)
    ensure_experiment_dirs(paths)
    thresholds = _load_thresholds(paths)
    min_trades = int(args.min_trades or thresholds.get("low_sample_trades", 30))

    if args.result_json:
        rp = Path(args.result_json)
        if not rp.is_absolute():
            rp = (repo_root / rp).resolve()
        result = load_json(rp)
        result_path = rp
    elif args.experiment_id:
        result = _result_by_id(paths, args.experiment_id)
        result_path = paths.results / f"{args.experiment_id}.json"
    else:
        raise SystemExit("Provide --experiment-id or --result-json")

    strategy_block = _load_strategy_block(result)
    concentration = _pair_concentration(strategy_block, thresholds)
    fee_rows = _collect_fee_rows(paths, result)
    metrics = result.get("metrics", {})
    trades = int(metrics.get("trades", 0) or 0)
    pf = metrics.get("profit_factor")
    max_dd = float(metrics.get("max_drawdown_pct", 0.0) or 0.0)

    flags: list[str] = []
    notes: list[str] = []

    lookahead = {"status": "not_run", "details": []}
    recursive = {"status": "not_run", "details": []}

    config = str(result.get("config_path", ""))
    strategy = str(result.get("strategy_name", ""))
    timerange = str(result.get("timerange", ""))

    freqtrade_cmd = _resolve_freqtrade_cmd(repo_root)
    planned_lookahead_cmd = [freqtrade_cmd, "lookahead-analysis", "-c", config, "-s", strategy, "--timerange", timerange]
    planned_recursive_cmd = [freqtrade_cmd, "recursive-analysis", "-c", config, "-s", strategy, "--timerange", timerange]

    retry_attempts = max(1, int(args.retry_attempts))
    retry_delay_sec = max(0.0, float(args.retry_delay_sec))
    temp_override_config: str | None = None
    infra_failures: list[dict[str, Any]] = []
    retryable = False

    if args.run_lookahead and not args.dry_run:
        details: list[dict[str, Any]] = []
        detail: dict[str, Any] = {}
        for attempt in range(1, retry_attempts + 1):
            d = _run_cmd(planned_lookahead_cmd)
            d["attempt"] = attempt
            details.append(d)
            detail = d
            infra = detect_infra_failure(d.get("output_tail", ""), int(d.get("returncode", 1)))
            if d["returncode"] == 0:
                break
            if attempt == 1:
                retry_detail, temp_override_config = _retry_lookahead_with_temp_config(
                    repo_root=repo_root,
                    original_cmd=planned_lookahead_cmd,
                    original_config=config,
                    error_output=d.get("output_tail", ""),
                )
                if retry_detail:
                    retry_detail["attempt"] = f"{attempt}-config-override"
                    details.append(retry_detail)
                    detail = retry_detail
                    infra = detect_infra_failure(
                        retry_detail.get("output_tail", ""),
                        int(retry_detail.get("returncode", 1)),
                    )
                    if retry_detail["returncode"] == 0:
                        break
            if infra["is_infra"]:
                retryable = True
                infra_failures.append(
                    {"check": "lookahead", "attempt": attempt, "reason": infra["reason"], "returncode": d["returncode"]}
                )
                if attempt < retry_attempts:
                    time.sleep(retry_delay_sec * attempt)
                    continue
            break

        final_infra = detect_infra_failure(detail.get("output_tail", ""), int(detail.get("returncode", 1)))
        if detail.get("returncode") == 0:
            status = "ok"
        elif final_infra["is_infra"]:
            status = "infra_fail"
            retryable = True
        else:
            status = "fail"
        lookahead = {"status": status, "details": details}
    else:
        lookahead = {"status": "dry_run", "details": [{"cmd": " ".join(planned_lookahead_cmd)}]}

    if args.run_recursive and not args.dry_run:
        details = []
        detail = {}
        for attempt in range(1, retry_attempts + 1):
            d = _run_cmd(planned_recursive_cmd)
            d["attempt"] = attempt
            details.append(d)
            detail = d
            infra = detect_infra_failure(d.get("output_tail", ""), int(d.get("returncode", 1)))
            if d["returncode"] == 0:
                break
            if infra["is_infra"]:
                retryable = True
                infra_failures.append(
                    {"check": "recursive", "attempt": attempt, "reason": infra["reason"], "returncode": d["returncode"]}
                )
                if attempt < retry_attempts:
                    time.sleep(retry_delay_sec * attempt)
                    continue
            break

        final_infra = detect_infra_failure(detail.get("output_tail", ""), int(detail.get("returncode", 1)))
        if detail.get("returncode") == 0:
            status = "ok"
        elif final_infra["is_infra"]:
            status = "infra_fail"
            retryable = True
        else:
            status = "fail"
        recursive = {"status": status, "details": details}
    else:
        recursive = {"status": "dry_run", "details": [{"cmd": " ".join(planned_recursive_cmd)}]}

    if lookahead["status"] == "fail":
        flags.append("FAIL_LOOKAHEAD")
    if lookahead["status"] == "infra_fail":
        flags.append("INFRA_FAIL_LOOKAHEAD")
        notes.append("Lookahead failed due to infrastructure issue (retryable).")
    if recursive["status"] == "fail":
        flags.append("FAIL_RECURSIVE")
    if recursive["status"] == "infra_fail":
        flags.append("INFRA_FAIL_RECURSIVE")
        notes.append("Recursive failed due to infrastructure issue (retryable).")

    for f in concentration.get("flags", []):
        if f not in flags:
            flags.append(f)

    if trades < min_trades:
        flags.append("LOW_SAMPLE")
        notes.append(f"Trades below threshold: {trades} < {min_trades}")

    cost_fragile = False
    if fee_rows:
        base = next((r for r in fee_rows if r["fee_delta_pct"] == 0), None)
        fee50 = next((r for r in fee_rows if abs(r["fee_delta_pct"] - 50.0) < 1e-9), None)
        if base and fee50:
            base_pf = base.get("profit_factor")
            fee50_pf = fee50.get("profit_factor")
            if isinstance(base_pf, (int, float)) and isinstance(fee50_pf, (int, float)):
                if base_pf > 1 and fee50_pf < float(thresholds.get("cost_fragile_fee50_below_pf", 1.0)):
                    cost_fragile = True
                if (base_pf - fee50_pf) > float(thresholds.get("cost_fragile_pf_drop_threshold", 0.2)):
                    cost_fragile = True
    if cost_fragile:
        flags.append("COST_FRAGILE")

    score = 100.0
    penalties = {
        "FAIL_LOOKAHEAD": 40,
        "FAIL_RECURSIVE": 35,
        "INFRA_FAIL_LOOKAHEAD": 0,
        "INFRA_FAIL_RECURSIVE": 0,
        "TOO_CONCENTRATED_TOP1": 12,
        "TOO_CONCENTRATED_TOP3": 12,
        "PAIR_DEPENDENCY_RISK": 10,
        "LOW_SAMPLE": 20,
        "COST_FRAGILE": 15,
    }
    for f in flags:
        score -= penalties.get(f, 8)
    score = max(0.0, score)

    severe = {"FAIL_LOOKAHEAD", "FAIL_RECURSIVE", "COST_FRAGILE"}
    if not any(f in severe for f in flags) and isinstance(pf, (int, float)) and pf > 1:
        if trades >= int(thresholds.get("min_trades_for_confidence", 80)) and max_dd <= float(
            thresholds.get("baseline_candidate_max_dd", 1.5)
        ):
            if score >= float(thresholds.get("robust_candidate_min_score", 70.0)):
                flags.append("ROBUST_CANDIDATE")

    report = {
        "experiment_id": result.get("experiment_id"),
        "strategy_name": strategy,
        "timeframe": result.get("timeframe"),
        "universe_label": result.get("universe_label"),
        "robustness_score": round(score, 2),
        "flags": flags,
        "retryable": retryable,
        "infra_failures": infra_failures,
        "thresholds_used": thresholds,
        "checks": {
            "lookahead": lookahead,
            "recursive": recursive,
            "pair_concentration": concentration,
            "fee_sensitivity_rows": fee_rows,
            "sample_check": {"trades": trades, "min_trades": min_trades},
        },
        "notes": notes,
    }
    if temp_override_config:
        report["temporary_config_override"] = temp_override_config

    out = Path(args.out) if args.out else (paths.robustness / f"{result.get('experiment_id')}.robustness.json")
    if not out.is_absolute():
        out = (repo_root / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, report)
    print(json.dumps({"report": str(out), "robustness_score": report["robustness_score"], "flags": flags}, indent=2))

    if args.write_back:
        result["robustness_validation"] = {
            "robustness_score": report["robustness_score"],
            "flags": flags,
            "retryable": retryable,
            "infra_failures": infra_failures,
            "report_json": str(out),
        }
        write_json(result_path, result)
        print(json.dumps({"updated_result": str(result_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
