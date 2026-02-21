#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infra_retry import run_with_retries
from report_utils import find_repo_root, get_paths, load_json, write_json


TARGET_EXPERIMENT_ID = "20260221T012208Z_strat19volcompressionbreakout-4h-v1_4h_top15-mr4h-stable-candidate"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_step(
    *,
    name: str,
    cmd: list[str],
    repo_root: Path,
    log_path: Path,
    attempts: int,
    delay: float,
    backoff: float,
) -> dict[str, Any]:
    result = run_with_retries(
        cmd,
        cwd=repo_root,
        attempts=attempts,
        base_delay_sec=delay,
        backoff_mult=backoff,
        output_tail_chars=6000,
    )
    event = {
        "ts_utc": _utc_now(),
        "step": name,
        "cmd": " ".join(cmd),
        "status": result.get("status"),
        "retryable": result.get("retryable"),
        "attempt_count": len(result.get("attempts", [])),
        "final": result.get("final"),
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as lf:
        lf.write(json.dumps(event, ensure_ascii=True) + "\n")
    return event


def _load_lopo_summary(repo_root: Path) -> dict[str, Any]:
    p = repo_root / "user_data/research/calibration/strat19_lopo_sensitivity_20260221.json"
    return load_json(p)


def _load_robustness(repo_root: Path, experiment_id: str) -> dict[str, Any]:
    p = repo_root / "user_data/experiments/robustness" / f"{experiment_id}.robustness.json"
    return load_json(p)


def _set_blocker_fields(repo_root: Path, experiment_id: str, lopo: dict[str, Any], robustness: dict[str, Any]) -> dict[str, Any]:
    paths = get_paths(repo_root)
    result_path = paths.results / f"{experiment_id}.json"
    result = load_json(result_path)

    pending_items: list[str] = []
    if int(lopo.get("missing_count", 0) or 0) > 0:
        pending_items.append("lopo_missing_pairs")

    lookahead_status = ((robustness.get("checks") or {}).get("lookahead") or {}).get("status")
    recursive_status = ((robustness.get("checks") or {}).get("recursive") or {}).get("status")
    if lookahead_status != "ok" or recursive_status != "ok":
        pending_items.append("anti_smoke_real")

    has_blocker = len(pending_items) > 0
    result["validation_blocker"] = has_blocker
    result["validation_blocker_type"] = "infrastructure" if has_blocker else None
    result["retry_ready"] = has_blocker
    result["infra_pending_items"] = pending_items
    write_json(result_path, result)

    return {
        "result_json": str(result_path),
        "validation_blocker": result["validation_blocker"],
        "validation_blocker_type": result["validation_blocker_type"],
        "retry_ready": result["retry_ready"],
        "infra_pending_items": result["infra_pending_items"],
    }


def _refresh_structural_report(repo_root: Path, blocker_payload: dict[str, Any], lopo: dict[str, Any], robustness: dict[str, Any]) -> dict[str, Any]:
    struct_json = repo_root / "user_data/research/calibration/strat19_4h_structural_validation_20260221.json"
    struct_md = repo_root / "user_data/research/calibration/strat19_4h_structural_validation_20260221.md"
    payload = load_json(struct_json) if struct_json.exists() else {}

    payload["validation_blocker"] = blocker_payload["validation_blocker"]
    payload["validation_blocker_type"] = blocker_payload["validation_blocker_type"]
    payload["retry_ready"] = blocker_payload["retry_ready"]
    payload["infra_pending_items"] = blocker_payload["infra_pending_items"]

    payload["lopo"] = payload.get("lopo", {})
    payload["lopo"]["summary"] = {
        "completed_count": lopo.get("completed_count"),
        "missing_count": lopo.get("missing_count"),
        "missing_due_infra": lopo.get("missing_due_infra", []),
    }

    payload["anti_smoke"] = {
        "lookahead_status": ((robustness.get("checks") or {}).get("lookahead") or {}).get("status"),
        "recursive_status": ((robustness.get("checks") or {}).get("recursive") or {}).get("status"),
        "retryable": robustness.get("retryable", False),
        "flags": robustness.get("flags", []),
    }

    payload["decision"] = {
        "final_decision": (
            "promote_to_baseline"
            if not blocker_payload["validation_blocker"]
            else "keep_4h_stable_candidate_as_baseline_provisional_infra_pending"
        ),
        "classification": "baseline_provisional" if blocker_payload["validation_blocker"] else "baseline",
        "updated_at_utc": _utc_now(),
    }
    write_json(struct_json, payload)

    md_lines = [
        "# Strat19 4h Revalidation Status",
        "",
        f"- updated_at_utc: {_utc_now()}",
        f"- validation_blocker: {str(blocker_payload['validation_blocker']).lower()}",
        f"- validation_blocker_type: {blocker_payload['validation_blocker_type']}",
        f"- retry_ready: {str(blocker_payload['retry_ready']).lower()}",
        f"- infra_pending_items: {', '.join(blocker_payload['infra_pending_items']) if blocker_payload['infra_pending_items'] else 'none'}",
        "",
        f"- LOPO completed/missing: {lopo.get('completed_count')}/{lopo.get('missing_count')}",
        f"- Anti-smoke lookahead/recursive: {payload['anti_smoke']['lookahead_status']}/{payload['anti_smoke']['recursive_status']}",
    ]
    struct_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return {"json": str(struct_json), "md": str(struct_md)}


def main() -> int:
    p = argparse.ArgumentParser(description="Run full revalidation flow for Strat19 4h stable candidate.")
    p.add_argument("--experiment-id", default=TARGET_EXPERIMENT_ID)
    p.add_argument("--attempts", type=int, default=3)
    p.add_argument("--base-delay-sec", type=float, default=3.0)
    p.add_argument("--backoff-mult", type=float, default=1.7)
    p.add_argument("--run-calibration", action="store_true", default=True)
    p.add_argument("--skip-calibration", action="store_true", default=False)
    p.add_argument("--log-jsonl", default="user_data/research/calibration/revalidate_strat19_4h_stable_20260221.jsonl")
    args = p.parse_args()

    repo_root = find_repo_root(Path.cwd())
    py_bin = repo_root / ".env/bin/python"
    log_path = (repo_root / args.log_jsonl).resolve()

    steps: list[dict[str, Any]] = []

    steps.append(
        _run_step(
            name="retry_lopo_missing_infra",
            cmd=[
                str(py_bin),
                "user_data/scripts/retry_strat19_lopo.py",
                "--attempts",
                str(args.attempts),
                "--base-delay-sec",
                str(args.base_delay_sec),
                "--backoff-mult",
                str(args.backoff_mult),
            ],
            repo_root=repo_root,
            log_path=log_path,
            attempts=1,
            delay=0.0,
            backoff=1.0,
        )
    )

    steps.append(
        _run_step(
            name="retry_anti_smoke_real",
            cmd=[
                str(py_bin),
                "user_data/scripts/anti_smoke_validator.py",
                "--experiment-id",
                args.experiment_id,
                "--run-lookahead",
                "--run-recursive",
                "--retry-attempts",
                str(args.attempts),
                "--retry-delay-sec",
                str(args.base_delay_sec),
                "--write-back",
            ],
            repo_root=repo_root,
            log_path=log_path,
            attempts=1,
            delay=0.0,
            backoff=1.0,
        )
    )

    steps.append(
        _run_step(
            name="refresh_leaderboard",
            cmd=[str(py_bin), "user_data/scripts/research_leaderboard.py"],
            repo_root=repo_root,
            log_path=log_path,
            attempts=1,
            delay=0.0,
            backoff=1.0,
        )
    )

    if args.run_calibration and not args.skip_calibration:
        steps.append(
            _run_step(
                name="refresh_calibration",
                cmd=[str(py_bin), "user_data/scripts/calibrate_research_tools.py"],
                repo_root=repo_root,
                log_path=log_path,
                attempts=1,
                delay=0.0,
                backoff=1.0,
            )
        )

    steps.append(
        _run_step(
            name="orchestrator_recommend",
            cmd=[str(py_bin), "user_data/scripts/orchestrator.py", "recommend", "--experiment-id", args.experiment_id],
            repo_root=repo_root,
            log_path=log_path,
            attempts=1,
            delay=0.0,
            backoff=1.0,
        )
    )

    lopo = _load_lopo_summary(repo_root)
    robustness = _load_robustness(repo_root, args.experiment_id)
    blocker = _set_blocker_fields(repo_root, args.experiment_id, lopo, robustness)
    structural = _refresh_structural_report(repo_root, blocker, lopo, robustness)

    # Regenerate leaderboard once more so blocker fields appear in leaderboard output.
    _run_step(
        name="refresh_leaderboard_with_blocker_fields",
        cmd=[str(py_bin), "user_data/scripts/research_leaderboard.py"],
        repo_root=repo_root,
        log_path=log_path,
        attempts=1,
        delay=0.0,
        backoff=1.0,
    )

    recommendation_code = "RERUN_OR_DEBUG" if blocker["validation_blocker"] else "BASELINE_CANDIDATE"
    promote_ready = (not blocker["validation_blocker"]) and (
        ((robustness.get("checks") or {}).get("lookahead") or {}).get("status") == "ok"
        and ((robustness.get("checks") or {}).get("recursive") or {}).get("status") == "ok"
    )

    out = {
        "experiment_id": args.experiment_id,
        "lopo_status": {
            "completed_count": lopo.get("completed_count"),
            "missing_count": lopo.get("missing_count"),
            "missing_due_infra": lopo.get("missing_due_infra", []),
        },
        "anti_smoke_status": {
            "lookahead": ((robustness.get("checks") or {}).get("lookahead") or {}).get("status"),
            "recursive": ((robustness.get("checks") or {}).get("recursive") or {}).get("status"),
            "retryable": robustness.get("retryable"),
            "flags": robustness.get("flags", []),
        },
        "blocker_fields": blocker,
        "recommendation_code": recommendation_code,
        "can_promote_baseline": promote_ready,
        "steps": steps,
        "structural_report": structural,
        "log_jsonl": str(log_path),
    }
    print(json.dumps(out, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

