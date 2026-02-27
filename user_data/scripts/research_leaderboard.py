#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from report_utils import find_repo_root, get_paths, load_json, write_json


def _default_thresholds() -> dict[str, float]:
    return {
        "min_trades_for_confidence": 80.0,
        "low_sample_trades": 30.0,
    }


def _load_thresholds(paths) -> dict[str, float]:
    out = _default_thresholds()
    cfg = paths.experiments / "research_thresholds.json"
    if not cfg.exists():
        return out
    try:
        obj = load_json(cfg)
        if isinstance(obj, dict):
            for k in out:
                if k in obj:
                    out[k] = float(obj[k])
    except Exception:
        pass
    return out


def _load_result_files(paths) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in paths.results.glob("*.json"):
        try:
            obj = load_json(p)
        except Exception:
            # Keep leaderboard resilient to malformed legacy files.
            continue
        if not isinstance(obj, dict) or "metrics" not in obj:
            continue
        obj["_path"] = str(p)
        rows.append(obj)
    rows.sort(key=lambda x: x.get("created_at", ""))
    return rows


def _key(obj: dict[str, Any]) -> str:
    return f"{obj.get('strategy_name')}|{obj.get('timeframe')}|{obj.get('universe_label')}"


def _latest_by_key(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest[_key(row)] = row
    return latest


def _is_baseline(r: dict[str, Any]) -> bool:
    universe = str(r.get("universe_label", ""))
    return (
        r.get("strategy_name") == "Strat03RSIBBMeanReversion_v3c"
        and str(r.get("timeframe")) == "1h"
        and (
            universe == "top15_mr1h_stable_candidate_sanity"
            or universe == "top15_mr1h_stable_candidate_effective"
        )
    )


def _is_benchmark(r: dict[str, Any]) -> bool:
    universe = str(r.get("universe_label", ""))
    is_1h_benchmark = (
        r.get("strategy_name") == "Strat03RSIBBMeanReversion_v3c"
        and str(r.get("timeframe")) == "1h"
        and universe == "top15_mr1h_effective"
    )
    is_4h_benchmark = (
        r.get("strategy_name") == "Strat19VolCompressionBreakout_4h_v1"
        and str(r.get("timeframe")) == "4h"
        and "top15_mr4h_effective" in universe
    )
    return is_1h_benchmark or is_4h_benchmark


def _is_baseline_provisional(r: dict[str, Any]) -> bool:
    return (
        r.get("strategy_name") == "Strat19VolCompressionBreakout_4h_v1"
        and str(r.get("timeframe")) == "4h"
        and "top15_mr4h_stable_candidate" in str(r.get("universe_label", ""))
    )


def _status_default(r: dict[str, Any], thresholds: dict[str, float]) -> str:
    if _is_baseline(r):
        return "baseline"
    if _is_benchmark(r):
        return "benchmark"
    if _is_baseline_provisional(r):
        return "baseline_provisional"

    m = r.get("metrics", {})
    pf = m.get("profit_factor")
    trades = int(m.get("trades", 0) or 0)
    status = str(r.get("status", "success"))

    if status != "success" or pf is None:
        return "pending"
    if isinstance(pf, (int, float)) and pf <= 1 and trades >= int(thresholds["min_trades_for_confidence"]):
        return "discarded"
    if isinstance(pf, (int, float)) and pf > 1:
        return "viable"
    if trades < int(thresholds["low_sample_trades"]):
        return "pending"
    return "research"


def _pair_concentration_note(r: dict[str, Any]) -> str:
    rv = r.get("robustness_validation", {}) or {}
    flags = [str(x) for x in (rv.get("flags") or [])]
    if any(f in flags for f in ["TOO_CONCENTRATED_TOP1", "TOO_CONCENTRATED_TOP3", "PAIR_DEPENDENCY_RISK"]):
        return "concentration_risk"
    if "MISSING_PAIR_BREAKDOWN" in flags:
        return "unknown"
    return "ok_or_unknown"


def _composite_score(r: dict[str, Any]) -> float:
    m = r.get("metrics", {})
    rv = r.get("robustness_validation", {}) or {}

    pf = float(m.get("profit_factor", 0.0) or 0.0)
    dd = float(m.get("max_drawdown_pct", 0.0) or 0.0)
    trades = int(m.get("trades", 0) or 0)
    robust = rv.get("robustness_score")
    robust_score = float(robust) if isinstance(robust, (int, float)) else 50.0

    pf_component = min(max(pf, 0.0), 2.0) / 2.0 * 40.0
    dd_component = max(0.0, 1.0 - min(dd, 10.0) / 10.0) * 20.0
    trades_component = min(trades, 200) / 200.0 * 20.0
    robust_component = min(max(robust_score, 0.0), 100.0) / 100.0 * 20.0
    return round(pf_component + dd_component + trades_component + robust_component, 2)


def _row_for_markdown(r: dict[str, Any], status: str) -> list[str]:
    m = r.get("metrics", {})
    rv = r.get("robustness_validation", {}) or {}
    flags = ",".join((rv.get("flags", []) or [])[:3])
    blocker = str(r.get("validation_blocker_type", "")) if r.get("validation_blocker") else ""
    return [
        str(r.get("strategy_name", "")),
        str(r.get("universe_label", "")),
        str(int(m.get("trades", 0) or 0)),
        f"{float(m.get('trades_per_day', 0.0) or 0.0):.2f}",
        f"{float(m.get('profit_total_pct', 0.0) or 0.0):.4f}",
        str(m.get("profit_factor")),
        f"{float(m.get('max_drawdown_pct', 0.0) or 0.0):.4f}",
        str(rv.get("robustness_score", "")),
        flags,
        blocker,
        status,
    ]


def _markdown_section(title: str, rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        f"## {title}",
        "| strategy | universe | trades | trades/day | profit% | PF | maxDD% | robust | flags | blocker | status |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    if not rows:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - |")
        return lines
    for r in rows:
        lines.append("| " + " | ".join(_row_for_markdown(r, r["_status"])) + " |")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate research leaderboard (markdown + json).")
    parser.add_argument("--out-md", default="user_data/research/RESEARCH_LEADERBOARD.md")
    parser.add_argument("--out-json", default="user_data/research/research_leaderboard.json")
    args = parser.parse_args()

    repo_root = find_repo_root(Path.cwd())
    paths = get_paths(repo_root)
    thresholds = _load_thresholds(paths)

    rows = _load_result_files(paths)
    latest = list(_latest_by_key(rows).values())

    by_tf: dict[str, list[dict[str, Any]]] = {"1h": [], "4h": [], "1d": []}
    entries: list[dict[str, Any]] = []

    for r in latest:
        tf = str(r.get("timeframe", ""))
        if tf not in by_tf:
            continue
        status = _status_default(r, thresholds)
        r["_status"] = status
        r["_composite_score"] = _composite_score(r)
        by_tf[tf].append(r)

        rv = r.get("robustness_validation", {}) or {}
        entries.append(
            {
                "experiment_id": r.get("experiment_id"),
                "strategy": r.get("strategy_name"),
                "family": r.get("strategy_family"),
                "timeframe": tf,
                "universe": r.get("universe_label"),
                "status": status,
                "metrics": r.get("metrics", {}),
                "robustness_score": rv.get("robustness_score"),
                "robustness_flags": rv.get("flags", []),
                "validation_blocker": bool(r.get("validation_blocker", False)),
                "validation_blocker_type": r.get("validation_blocker_type"),
                "retry_ready": bool(r.get("retry_ready", False)),
                "infra_pending_items": r.get("infra_pending_items", []),
                "pair_concentration_note": _pair_concentration_note(r),
                "composite_score": r["_composite_score"],
            }
        )

    for tf in by_tf:
        by_tf[tf].sort(key=lambda r: r.get("_composite_score", 0.0), reverse=True)

    top_candidates: dict[str, list[dict[str, Any]]] = {}
    grouped_status: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for tf, items in by_tf.items():
        top_candidates[tf] = items[:3]
        grouped_status[tf] = {
            "baseline": [r for r in items if r["_status"] in {"baseline", "baseline_provisional"}],
            "benchmark": [r for r in items if r["_status"] == "benchmark"],
            "viable": [r for r in items if r["_status"] == "viable"],
            "discarded": [r for r in items if r["_status"] == "discarded"],
            "pending": [r for r in items if r["_status"] in {"pending", "research"}],
        }

    md_lines = [
        "# Research Leaderboard By Timeframe",
        "",
        f"Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}",
        "",
        "## Top Candidates Por Timeframe",
    ]
    for tf in ["1h", "4h", "1d"]:
        md_lines.extend([f"### {tf}"])
        md_lines.extend(_markdown_section(f"Top 3 ({tf})", top_candidates.get(tf, [])))
        md_lines.append("")

    for tf in ["1h", "4h", "1d"]:
        md_lines.extend([f"## {tf} - Baseline / Baseline Provisional"])
        md_lines.extend(_markdown_section(f"{tf} baseline", grouped_status[tf]["baseline"]))
        md_lines.append("")
        md_lines.extend([f"## {tf} - Benchmark"])
        md_lines.extend(_markdown_section(f"{tf} benchmark", grouped_status[tf]["benchmark"]))
        md_lines.append("")
        md_lines.extend([f"## {tf} - Viable Alternatives"])
        md_lines.extend(_markdown_section(f"{tf} viable", grouped_status[tf]["viable"]))
        md_lines.append("")
        md_lines.extend([f"## {tf} - Discarded"])
        md_lines.extend(_markdown_section(f"{tf} discarded", grouped_status[tf]["discarded"]))
        md_lines.append("")
        md_lines.extend([f"## {tf} - Pending / Research"])
        md_lines.extend(_markdown_section(f"{tf} pending", grouped_status[tf]["pending"]))
        md_lines.append("")

    md_lines.extend(
        [
            "## Next Best Actions",
            "1. Mantener 1h stable candidate como baseline principal y top15 original como benchmark secundario.",
            "2. Expandir universo/splits antes de bajar timeframe.",
            "3. 3h no soportado en este entorno; usar pivot 2h/4h.",
            "4. Priorizar validación anti-humo (lookahead/recursive/costos/concentración) antes de promover nuevas baselines.",
        ]
    )

    out_md = Path(args.out_md)
    if not out_md.is_absolute():
        out_md = (repo_root / out_md).resolve()
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    payload = {
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "thresholds_used": thresholds,
        "top_candidates": {
            tf: [
                {
                    "experiment_id": r.get("experiment_id"),
                    "strategy": r.get("strategy_name"),
                    "universe": r.get("universe_label"),
                    "composite_score": r.get("_composite_score"),
                }
                for r in rows
            ]
            for tf, rows in top_candidates.items()
        },
        "by_timeframe": {
            tf: {
                "baseline": [r.get("experiment_id") for r in grouped_status[tf]["baseline"]],
                "benchmark": [r.get("experiment_id") for r in grouped_status[tf]["benchmark"]],
                "viable": [r.get("experiment_id") for r in grouped_status[tf]["viable"]],
                "discarded": [r.get("experiment_id") for r in grouped_status[tf]["discarded"]],
                "pending": [r.get("experiment_id") for r in grouped_status[tf]["pending"]],
            }
            for tf in ["1h", "4h", "1d"]
        },
        "entries": entries,
    }

    out_json = Path(args.out_json)
    if not out_json.is_absolute():
        out_json = (repo_root / out_json).resolve()
    write_json(out_json, payload)

    print(json.dumps({"markdown": str(out_md), "json": str(out_json), "entries": len(entries)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
