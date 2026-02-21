#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any

from report_utils import (
    append_ledger,
    ensure_experiment_dirs,
    find_repo_root,
    format_metrics_markdown,
    get_git_commit,
    get_paths,
    load_config_pairs_count,
    parse_metrics_from_text,
    slugify,
    utc_now_compact,
    utc_now_iso,
    write_json,
)


def _infer_zip_from_meta(meta_path: Path) -> Path:
    if meta_path.name.endswith(".meta.json"):
        return meta_path.with_name(meta_path.name.replace(".meta.json", ".zip"))
    return meta_path.with_suffix(".zip")


def _extract_export_json(zip_path: Path, out_path: Path) -> tuple[dict[str, Any], str]:
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".json") and not n.endswith(".meta.json") and not n.endswith("_config.json")]
        if not names:
            raise ValueError(f"No backtest json found inside {zip_path}")
        inner_name = names[0]
        payload = json.loads(zf.read(inner_name))
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return payload, inner_name


def _extract_metrics_from_payload(payload: dict[str, Any], strategy_name: str) -> tuple[dict[str, Any], int, list[str], dict[str, Any]]:
    strategy_block = payload.get("strategy", {}).get(strategy_name)
    if not strategy_block:
        available = list(payload.get("strategy", {}).keys())
        raise KeyError(f"Strategy '{strategy_name}' not found in backtest payload. Available: {available}")

    metrics = {
        "trades": int(strategy_block.get("total_trades", 0) or 0),
        "trades_per_day": float(strategy_block.get("trades_per_day", 0.0) or 0.0),
        "profit_total_pct": float((strategy_block.get("profit_total", 0.0) or 0.0) * 100.0),
        "winrate_pct": float((strategy_block.get("winrate", 0.0) or 0.0) * 100.0),
        "profit_factor": strategy_block.get("profit_factor"),
        "max_drawdown_pct": float((strategy_block.get("max_drawdown_account", 0.0) or 0.0) * 100.0),
    }

    pair_rows = strategy_block.get("results_per_pair", [])
    pair_names = [row.get("key") for row in pair_rows if row.get("key") and row.get("key") != "TOTAL"]
    return metrics, len(pair_names), pair_names, strategy_block


def _auto_observations(metrics: dict[str, Any]) -> list[str]:
    obs: list[str] = []
    pf = metrics.get("profit_factor")
    trades = int(metrics.get("trades", 0) or 0)
    if pf is None:
        obs.append("Profit factor no disponible.")
    elif float(pf) > 1 and trades < 30:
        obs.append("PF > 1 con pocos trades: evidencia estadística limitada.")
    elif float(pf) > 1:
        obs.append("PF > 1 en este experimento.")
    else:
        obs.append("PF < 1 en este experimento.")

    if float(metrics.get("max_drawdown_pct", 0.0)) > 10:
        obs.append("Drawdown alto (>10%).")
    return obs


def _make_notes_short(metrics: dict[str, Any], oos: bool | None, pairs_count: int) -> str:
    parts: list[str] = []
    pf = metrics.get("profit_factor")
    trades = int(metrics.get("trades", 0) or 0)
    dd = float(metrics.get("max_drawdown_pct", 0.0) or 0.0)

    if pf is None:
        parts.append("PF missing")
    else:
        pf_val = float(pf)
        if pf_val > 1 and trades < 30:
            parts.append("PF>1 low trades")
        elif pf_val > 1:
            parts.append("PF>1")
        elif dd > 10:
            parts.append("PF<1 high DD")
        else:
            parts.append("PF<1")

    if oos is True:
        parts.append("OOS pass" if (pf is not None and float(pf) > 1) else "OOS fail")

    parts.append(f"pairs={pairs_count}")
    return "; ".join(parts)


def _build_experiment_result(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = find_repo_root(Path.cwd())
    paths = get_paths(repo_root)
    ensure_experiment_dirs(paths)

    created_at = utc_now_iso()
    exp_id = f"{utc_now_compact()}_{slugify(args.strategy)}_{slugify(args.timeframe)}_{slugify(args.universe)}"
    warnings: list[str] = []
    extra_files: list[str] = []

    metrics: dict[str, Any]
    pairs_count = 0
    pair_names: list[str] = []
    strategy_block: dict[str, Any] = {}
    backtest_meta_json: str | None = None
    backtest_export_json: str | None = None
    status = "success"

    if args.from_meta:
        meta_path = Path(args.from_meta)
        if not meta_path.is_absolute():
            meta_path = (repo_root / meta_path).resolve()
        if not meta_path.exists():
            raise FileNotFoundError(f"Meta file not found: {meta_path}")

        zip_path = _infer_zip_from_meta(meta_path)
        if not zip_path.exists():
            status = "partial"
            warnings.append(f"Zip asociado no encontrado: {zip_path}")
            metrics = {
                "trades": 0,
                "trades_per_day": 0.0,
                "profit_total_pct": 0.0,
                "winrate_pct": 0.0,
                "profit_factor": None,
                "max_drawdown_pct": 0.0,
            }
        else:
            export_json_path = paths.results / f"{exp_id}.backtest_export.json"
            payload, _ = _extract_export_json(zip_path, export_json_path)
            metrics, pairs_count, pair_names, strategy_block = _extract_metrics_from_payload(payload, args.strategy)
            backtest_export_json = str(export_json_path)
            extra_files.append(str(zip_path))

        backtest_meta_json = str(meta_path)

    else:
        text_path = Path(args.from_text)
        if not text_path.is_absolute():
            text_path = (repo_root / text_path).resolve()
        if not text_path.exists():
            raise FileNotFoundError(f"Text file not found: {text_path}")
        text = text_path.read_text(encoding="utf-8")
        metrics = parse_metrics_from_text(text)
        backtest_export_json = None
        backtest_meta_json = None
        warnings.append("Parseado desde texto. Métricas pueden ser incompletas.")

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()

    if pairs_count == 0:
        pairs_count, pair_names = load_config_pairs_count(config_path)
        if pairs_count == 0:
            warnings.append("No se pudo inferir cantidad de pares desde resultado ni config.")

    summary_md_path = paths.summaries / f"{exp_id}.md"
    idea_spec_id = args.idea_spec_id or None
    robustness_report_path: str | None = None
    robustness_flags: list[str] = []
    robustness_score: float | None = None
    if args.robustness_report:
        rr_path = Path(args.robustness_report)
        if not rr_path.is_absolute():
            rr_path = (repo_root / rr_path).resolve()
        if rr_path.exists():
            try:
                rr_obj = json.loads(rr_path.read_text(encoding="utf-8"))
                robustness_report_path = str(rr_path)
                robustness_flags = [str(x) for x in rr_obj.get("flags", [])]
                rs = rr_obj.get("robustness_score")
                robustness_score = float(rs) if rs is not None else None
            except Exception:
                warnings.append(f"No se pudo leer robustness_report: {rr_path}")
        else:
            warnings.append(f"robustness_report no existe: {rr_path}")

    result = {
        "experiment_id": exp_id,
        "created_at": created_at,
        "status": status,
        "strategy_name": args.strategy,
        "strategy_family": args.family,
        "config_path": str(config_path),
        "timeframe": args.timeframe,
        "timerange": args.timerange,
        "universe_label": args.universe,
        "pairs_count": int(pairs_count),
        "market_mode": args.market,
        "split_label": args.split_label,
        "idea_spec_id": idea_spec_id,
        "metrics": {
            "trades": int(metrics.get("trades", 0)),
            "trades_per_day": float(metrics.get("trades_per_day", 0.0)),
            "profit_total_pct": float(metrics.get("profit_total_pct", 0.0)),
            "winrate_pct": float(metrics.get("winrate_pct", 0.0)),
            "profit_factor": metrics.get("profit_factor"),
            "max_drawdown_pct": float(metrics.get("max_drawdown_pct", 0.0)),
        },
        "robustness": {
            "oos": None if args.oos is None else bool(args.oos),
            "fee_sensitivity_tested": bool(args.fee_sensitivity_tested),
            "fee_delta_pct": None if args.fee_delta_pct is None else float(args.fee_delta_pct),
        },
        "robustness_validation": {
            "robustness_score": robustness_score,
            "flags": robustness_flags,
            "report_json": robustness_report_path,
        },
        "artifacts": {
            "backtest_meta_json": backtest_meta_json,
            "backtest_export_json": backtest_export_json,
            "summary_md": str(summary_md_path),
            "extra_files": extra_files,
        },
        "notes": {
            "warnings": warnings,
            "observations": _auto_observations(metrics),
        },
        "provenance": {
            "command_run": " ".join(args.command_run) if args.command_run else "",
            "git_commit": get_git_commit(repo_root),
        },
    }

    if pair_names and isinstance(strategy_block, dict):
        top = []
        bottom = []
        for row in strategy_block.get("results_per_pair", []):
            key = row.get("key")
            if not key or key == "TOTAL":
                continue
            top.append((key, float(row.get("profit_total_pct", 0.0) or 0.0)))
        top.sort(key=lambda x: x[1], reverse=True)
        bottom = list(reversed(top))
        result["notes"]["top_pairs_by_profit_pct"] = top[:10]
        result["notes"]["bottom_pairs_by_profit_pct"] = bottom[:10]

    result_path = paths.results / f"{exp_id}.json"
    write_json(result_path, result)

    summary_lines = [
        f"# Experiment {exp_id}",
        "",
        "## Metadata",
        f"- strategy: `{args.strategy}` ({args.family})",
        f"- config: `{config_path}`",
        f"- timeframe: `{args.timeframe}`",
        f"- timerange: `{args.timerange}`",
        f"- universe: `{args.universe}` ({pairs_count} pairs)",
        f"- market: `{args.market}`",
        f"- status: `{status}`",
        "",
        "## Metrics",
        format_metrics_markdown(result["metrics"]),
        "",
        "## Notes",
    ]
    for w in result["notes"]["warnings"]:
        summary_lines.append(f"- warning: {w}")
    for o in result["notes"]["observations"]:
        summary_lines.append(f"- observation: {o}")

    summary_lines.extend(
        [
            "",
            "## Artifacts",
            f"- result_json: `{result_path}`",
            f"- backtest_meta_json: `{backtest_meta_json}`",
            f"- backtest_export_json: `{backtest_export_json}`",
            f"- idea_spec_id: `{idea_spec_id}`",
            f"- robustness_report_json: `{robustness_report_path}`",
        ]
    )

    summary_md_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    notes_short = _make_notes_short(result["metrics"], result["robustness"]["oos"], pairs_count)
    append_ledger(
        paths,
        {
            "experiment_id": exp_id,
            "created_at": created_at,
            "strategy_name": args.strategy,
            "timeframe": args.timeframe,
            "universe_label": args.universe,
            "timerange": args.timerange,
            "trades": result["metrics"]["trades"],
            "profit_total_pct": result["metrics"]["profit_total_pct"],
            "profit_factor": result["metrics"]["profit_factor"],
            "max_drawdown_pct": result["metrics"]["max_drawdown_pct"],
            "status": status,
            "split_label": args.split_label or "",
            "idea_spec_id": idea_spec_id or "",
            "robustness_score": "" if robustness_score is None else robustness_score,
            "robustness_flags": ",".join(robustness_flags),
            "notes_short": notes_short,
        },
    )

    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Convert Freqtrade backtest output into experiment JSON + ledger.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-meta", help="Path to backtest-result-...meta.json")
    src.add_argument("--from-text", help="Path to text summary file")

    p.add_argument("--strategy", required=True)
    p.add_argument("--family", default="unknown")
    p.add_argument("--config", required=True)
    p.add_argument("--timeframe", required=True)
    p.add_argument("--timerange", required=True)
    p.add_argument("--universe", required=True)
    p.add_argument("--market", choices=["spot", "futures"], required=True)
    p.add_argument("--split-label", default=None)
    p.add_argument("--idea-spec-id", default=None, help="Optional strategy idea/spec identifier")
    p.add_argument("--robustness-report", default=None, help="Optional path to anti-humo robustness report json")

    p.add_argument("--oos", action="store_true", default=None)
    p.add_argument("--fee-sensitivity-tested", action="store_true", default=False)
    p.add_argument("--fee-delta-pct", type=float, default=None)
    p.add_argument("--command-run", nargs="*", default=[])
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    result = _build_experiment_result(args)
    repo_root = find_repo_root(Path.cwd())
    result_json = repo_root / "user_data" / "experiments" / "results" / f"{result['experiment_id']}.json"
    print(json.dumps({
        "experiment_id": result["experiment_id"],
        "result_json": str(result_json),
        "summary_md": result["artifacts"]["summary_md"],
        "status": result["status"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
