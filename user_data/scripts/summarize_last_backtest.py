#!/usr/bin/env python3
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKTEST_DIR = REPO_ROOT / "user_data" / "backtest_results"
REPORTS_DIR = REPO_ROOT / "user_data" / "reports"
STATUS_FILE = REPORTS_DIR / "backtest_last_status.json"
JSON_OUT = REPORTS_DIR / "backtest_last_summary.json"
MD_OUT = REPORTS_DIR / "backtest_last_summary.md"


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    backtest_status = _safe_json_load(STATUS_FILE) if STATUS_FILE.exists() else None
    status_flag = backtest_status.get("status") if isinstance(backtest_status, dict) else None
    latest_meta = _find_latest_meta(BACKTEST_DIR)
    summary: dict[str, Any] = {
        "status": "ok",
        "no_new_backtest": False,
        "meta_file": str(latest_meta) if latest_meta else None,
        "strategy": None,
        "timerange": None,
        "total_profit_pct": None,
        "total_profit_usdt": None,
        "profit_factor": None,
        "drawdown": None,
        "trades": None,
        "backtest_status": backtest_status if isinstance(backtest_status, dict) else None,
    }

    if status_flag == "error":
        summary["status"] = "backtest_error"
        summary["no_new_backtest"] = True
        _write_outputs(summary)
        print(json.dumps(summary, ensure_ascii=True))
        return 0

    if latest_meta is None:
        summary["status"] = "no_backtest_meta_found"
        summary["no_new_backtest"] = True
        _write_outputs(summary)
        print(json.dumps(summary, ensure_ascii=True))
        return 0

    meta_payload = _safe_json_load(latest_meta)
    strategy = _first_key(meta_payload)
    summary["strategy"] = strategy
    summary["timerange"] = _extract_timerange(meta_payload, strategy)

    zip_path = latest_meta.with_suffix("").with_suffix(".zip")
    if zip_path.exists() and strategy:
        stats = _load_stats_from_zip(zip_path)
        strategy_stats = stats.get("strategy", {}).get(strategy, {}) if isinstance(stats, dict) else {}
        summary["total_profit_pct"] = _as_float(strategy_stats.get("profit_total"), scale=100.0)
        summary["total_profit_usdt"] = _as_float(strategy_stats.get("profit_total_abs"))
        summary["profit_factor"] = _as_float(strategy_stats.get("profit_factor"))
        summary["drawdown"] = _as_float(strategy_stats.get("max_drawdown_account"), scale=100.0)
        summary["trades"] = _as_int(strategy_stats.get("total_trades"))

    _write_outputs(summary)
    print(json.dumps(summary, ensure_ascii=True))
    return 0


def _find_latest_meta(root: Path) -> Path | None:
    files = sorted(root.glob("backtest-result-*.meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _safe_json_load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _first_key(d: dict[str, Any]) -> str | None:
    for k in d.keys():
        return k
    return None


def _extract_timerange(meta_payload: dict[str, Any], strategy: str | None) -> str | None:
    if not strategy:
        return None
    data = meta_payload.get(strategy, {})
    if not isinstance(data, dict):
        return None
    start_ts = data.get("backtest_start_ts")
    end_ts = data.get("backtest_end_ts")
    if start_ts is None or end_ts is None:
        return None
    try:
        start = datetime.fromtimestamp(float(start_ts), tz=timezone.utc).strftime("%Y%m%d")
        end = datetime.fromtimestamp(float(end_ts), tz=timezone.utc).strftime("%Y%m%d")
        return f"{start}-{end}"
    except Exception:
        return None


def _load_stats_from_zip(zip_path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            json_members = [n for n in zf.namelist() if n.endswith(".json") and "_config" not in n]
            if not json_members:
                return {}
            return json.loads(zf.read(json_members[0]).decode("utf-8"))
    except Exception:
        return {}


def _as_float(value: Any, scale: float = 1.0) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value) * scale
    except Exception:
        return None


def _as_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def _write_outputs(summary: dict[str, Any]) -> None:
    JSON_OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    md = [
        "# Last Backtest Summary",
        "",
        f"- status: {summary.get('status')}",
        f"- no_new_backtest: {summary.get('no_new_backtest')}",
        f"- meta_file: {summary.get('meta_file')}",
        f"- strategy: {summary.get('strategy')}",
        f"- timerange: {summary.get('timerange')}",
        f"- total_profit_pct: {summary.get('total_profit_pct')}",
        f"- total_profit_usdt: {summary.get('total_profit_usdt')}",
        f"- profit_factor: {summary.get('profit_factor')}",
        f"- drawdown: {summary.get('drawdown')}",
        f"- trades: {summary.get('trades')}",
        f"- backtest_status_file: {STATUS_FILE if STATUS_FILE.exists() else None}",
        "",
        "## Backtest Status Snapshot",
        "",
        "```json",
        json.dumps(summary.get("backtest_status"), ensure_ascii=True, indent=2),
        "```",
        "",
    ]
    MD_OUT.write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
