#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infra_retry import run_with_retries
from report_utils import find_repo_root


def _slug_pair(pair: str) -> str:
    return pair.lower().replace("/", "-")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _latest_meta_after(backtest_results_dir: Path, ts_before: float) -> Path | None:
    metas = [p for p in backtest_results_dir.glob("backtest-result-*.meta.json") if p.stat().st_mtime >= ts_before - 1]
    if not metas:
        return None
    return max(metas, key=lambda p: p.stat().st_mtime)


def _parse_metrics_from_zip(zip_path: Path, strategy_name: str) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path) as zf:
        entries = [n for n in zf.namelist() if n.endswith(".json") and "_config" not in n and "_market_change" not in n]
        if not entries:
            raise RuntimeError(f"No strategy json in {zip_path}")
        payload = json.loads(zf.read(entries[0]).decode("utf-8"))
    strat = payload["strategy"][strategy_name]
    return {
        "trades": int(strat.get("total_trades", 0) or 0),
        "profit_pct": float(strat.get("profit_total", 0.0) or 0.0),
        "PF": float(strat.get("profit_factor", 0.0) or 0.0),
        "maxDD_pct": float(strat.get("max_drawdown_account", 0.0) or 0.0) * 100.0,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "pair_removed",
        "status",
        "retry_status",
        "trades",
        "profit_pct",
        "PF",
        "maxDD_pct",
        "delta_PF_vs_baseline",
        "delta_profit_pct_vs_baseline",
        "delta_maxDD_pp_vs_baseline",
        "meta_path",
        "infra_reason",
        "retry_count",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})


def main() -> int:
    p = argparse.ArgumentParser(description="Retry missing LOPO runs for Strat19 4h with infra-aware retries.")
    p.add_argument("--summary-json", default="user_data/research/calibration/strat19_lopo_sensitivity_20260221.json")
    p.add_argument("--summary-csv", default="user_data/research/calibration/strat19_lopo_sensitivity_20260221.csv")
    p.add_argument("--config", default="user_data/configs/config.bt_spot_4h_top15_mr_effective.json")
    p.add_argument("--strategy", default="Strat19VolCompressionBreakout_4h_v1")
    p.add_argument("--timerange", default="20250101-20260201")
    p.add_argument("--attempts", type=int, default=3)
    p.add_argument("--base-delay-sec", type=float, default=3.0)
    p.add_argument("--backoff-mult", type=float, default=2.0)
    p.add_argument("--retry-status", nargs="*", default=["missing_due_dns", "missing_due_infra", "infra_fail"])
    p.add_argument("--log-jsonl", default="user_data/research/calibration/strat19_lopo_retry_20260221.jsonl")
    args = p.parse_args()

    repo_root = find_repo_root(Path.cwd())
    summary_json = (repo_root / args.summary_json).resolve()
    summary_csv = (repo_root / args.summary_csv).resolve()
    config_path = (repo_root / args.config).resolve()
    log_path = (repo_root / args.log_jsonl).resolve()

    summary = _load_json(summary_json)
    rows = summary.get("rows", [])
    base = summary.get("baseline", {})
    base_pf = float(base.get("pf", 0.0) or 0.0)
    base_profit = float(base.get("profit_pct", 0.0) or 0.0)
    base_dd = float(base.get("maxDD_pct", 0.0) or 0.0)
    pairs_full = [str(r.get("pair_removed", "")) for r in rows if r.get("pair_removed")]

    config_obj = _load_json(config_path)
    outdir = (repo_root / "user_data/backtest_results/lopo_strat19_4h_20260221").resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    backtest_results_dir = (repo_root / "user_data/backtest_results").resolve()
    freqtrade_bin = (repo_root / ".env/bin/freqtrade").resolve()

    run_events: list[dict[str, Any]] = []

    for row in rows:
        pair = str(row.get("pair_removed", ""))
        if not pair:
            continue

        slug = _slug_pair(pair)
        target_meta = outdir / f"strat19_4h_top15_lopo_rm_{slug}.meta.json"
        target_zip = outdir / f"strat19_4h_top15_lopo_rm_{slug}.zip"

        if row.get("status") == "ok" and target_meta.exists() and target_zip.exists():
            row["retry_status"] = "skipped"
            row["retry_count"] = 0
            run_events.append({"pair_removed": pair, "status": "skipped", "reason": "already_ok"})
            continue

        if str(row.get("status", "")) not in set(args.retry_status):
            row["retry_status"] = "skipped"
            row["retry_count"] = 0
            run_events.append({"pair_removed": pair, "status": "skipped", "reason": f"status={row.get('status')}"})
            continue

        # Build temporary LOPO config for this pair.
        cfg = dict(config_obj)
        cfg["strategy"] = args.strategy
        exch = dict(cfg.get("exchange", {}))
        exch["pair_whitelist"] = [p for p in pairs_full if p != pair]
        exch["skip_pair_validation"] = True
        cfg["exchange"] = exch

        tmp_cfg = outdir / f"tmp_rm_{slug}.manual.json"
        tmp_cfg.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

        cmd = [
            str(freqtrade_bin),
            "backtesting",
            "-c",
            str(tmp_cfg),
            "-s",
            args.strategy,
            "--timerange",
            args.timerange,
            "--export",
            "trades",
        ]

        ts_before = datetime.now(timezone.utc).timestamp()
        run = run_with_retries(
            cmd,
            cwd=repo_root,
            attempts=args.attempts,
            base_delay_sec=args.base_delay_sec,
            backoff_mult=args.backoff_mult,
            output_tail_chars=4000,
        )

        row["retry_count"] = len(run["attempts"])
        final = run.get("final") or {}
        row["infra_reason"] = final.get("infra_reason")

        if run["status"] == "ok":
            latest = _latest_meta_after(backtest_results_dir, ts_before)
            if latest is None:
                row["status"] = "missing_due_infra"
                row["retry_status"] = "infra_fail"
                row["infra_reason"] = row.get("infra_reason") or "missing_meta_after_success"
            else:
                zip_src = Path(str(latest.with_suffix("")) + ".zip")
                if not zip_src.exists():
                    row["status"] = "missing_due_infra"
                    row["retry_status"] = "infra_fail"
                    row["infra_reason"] = "missing_zip_after_success"
                else:
                    shutil.copy2(latest, target_meta)
                    shutil.copy2(zip_src, target_zip)
                    metrics = _parse_metrics_from_zip(target_zip, args.strategy)
                    row["status"] = "ok"
                    row["retry_status"] = "ok"
                    row["meta_path"] = str(target_meta)
                    row["trades"] = metrics["trades"]
                    row["profit_pct"] = metrics["profit_pct"]
                    row["PF"] = metrics["PF"]
                    row["maxDD_pct"] = metrics["maxDD_pct"]
                    row["delta_PF_vs_baseline"] = metrics["PF"] - base_pf
                    row["delta_profit_pct_vs_baseline"] = metrics["profit_pct"] - base_profit
                    row["delta_maxDD_pp_vs_baseline"] = metrics["maxDD_pct"] - base_dd
        elif run["status"] == "infra_fail":
            row["status"] = "missing_due_infra"
            row["retry_status"] = "infra_fail"
            row["meta_path"] = None
            row["trades"] = None
            row["profit_pct"] = None
            row["PF"] = None
            row["maxDD_pct"] = None
            row["delta_PF_vs_baseline"] = None
            row["delta_profit_pct_vs_baseline"] = None
            row["delta_maxDD_pp_vs_baseline"] = None
        else:
            row["status"] = "missing_due_infra"
            row["retry_status"] = "fail"
            row["meta_path"] = None
            row["trades"] = None
            row["profit_pct"] = None
            row["PF"] = None
            row["maxDD_pct"] = None
            row["delta_PF_vs_baseline"] = None
            row["delta_profit_pct_vs_baseline"] = None
            row["delta_maxDD_pp_vs_baseline"] = None

        run_events.append(
            {
                "pair_removed": pair,
                "status": row.get("status"),
                "retry_status": row.get("retry_status"),
                "retry_count": row.get("retry_count"),
                "infra_reason": row.get("infra_reason"),
                "final_returncode": final.get("returncode"),
            }
        )

        with log_path.open("a", encoding="utf-8") as lf:
            lf.write(json.dumps({"pair_removed": pair, "run": run, "row": row}, ensure_ascii=True) + "\n")

    summary["rows"] = rows
    summary["completed_count"] = sum(1 for r in rows if r.get("status") == "ok")
    summary["missing_count"] = sum(1 for r in rows if r.get("status") != "ok")
    summary["missing_due_infra"] = [r.get("pair_removed") for r in rows if r.get("status") == "missing_due_infra"]
    summary["updated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    summary["retry_run_events"] = run_events
    _write_json(summary_json, summary)
    _write_csv(summary_csv, rows)

    print(
        json.dumps(
            {
                "summary_json": str(summary_json),
                "summary_csv": str(summary_csv),
                "log_jsonl": str(log_path),
                "completed_count": summary["completed_count"],
                "missing_count": summary["missing_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

