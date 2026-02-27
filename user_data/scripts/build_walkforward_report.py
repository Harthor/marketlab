#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STATUS_JSON = REPO_ROOT / "user_data" / "reports" / "walkforward_status_1h.json"
CSV_OUT = REPO_ROOT / "user_data" / "reports" / "walkforward_1h.csv"
JSON_OUT = REPO_ROOT / "user_data" / "reports" / "walkforward_1h.json"
MD_OUT = REPO_ROOT / "user_data" / "reports" / "walkforward_1h.md"

COLUMNS = [
    "window_name",
    "timerange",
    "strategy",
    "trades",
    "total_profit_pct",
    "total_profit_usdt",
    "profit_factor",
    "max_drawdown_pct",
    "status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build walk-forward 1h report from status and backtest outputs.")
    parser.add_argument("--status-json", default=str(STATUS_JSON))
    parser.add_argument("--output-csv", default=str(CSV_OUT))
    parser.add_argument("--output-json", default=str(JSON_OUT))
    parser.add_argument("--output-md", default=str(MD_OUT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    status_path = Path(args.status_json)
    csv_out = Path(args.output_csv)
    json_out = Path(args.output_json)
    md_out = Path(args.output_md)
    csv_out.parent.mkdir(parents=True, exist_ok=True)

    payload = safe_json_load(status_path) if status_path.exists() else {}
    windows = payload.get("windows", []) if isinstance(payload, dict) else []
    if not isinstance(windows, list):
        windows = []

    rows: list[dict[str, Any]] = []
    for w in windows:
        if not isinstance(w, dict):
            continue
        rows.append(build_row(w))

    rows.sort(key=lambda r: str(r.get("window_name", "")))
    write_csv(csv_out, rows)
    write_json(json_out, rows)
    write_md(md_out, rows, status_path if status_path.exists() else None)

    print(f"[build_walkforward_report] rows={len(rows)} csv={csv_out}")
    print(f"[build_walkforward_report] json={json_out}")
    print(f"[build_walkforward_report] md={md_out}")
    return 0


def build_row(window_entry: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "window_name": window_entry.get("window_name"),
        "timerange": window_entry.get("timerange"),
        "strategy": window_entry.get("strategy"),
        "trades": None,
        "total_profit_pct": None,
        "total_profit_usdt": None,
        "profit_factor": None,
        "max_drawdown_pct": None,
        "status": window_entry.get("status", "error"),
    }

    if row["status"] != "ok":
        return row

    meta_path_value = window_entry.get("meta_file")
    if not meta_path_value:
        row["status"] = "error"
        return row

    meta_path = Path(str(meta_path_value))
    strategy = str(window_entry.get("strategy") or "")
    stats = load_strategy_stats(meta_path, strategy)
    if not stats:
        row["status"] = "error"
        return row

    row["trades"] = as_int(stats.get("total_trades"))
    row["total_profit_pct"] = as_float(stats.get("profit_total"), scale=100.0)
    row["total_profit_usdt"] = as_float(stats.get("profit_total_abs"))
    row["profit_factor"] = as_float(stats.get("profit_factor"))
    row["max_drawdown_pct"] = as_float(stats.get("max_drawdown_account"), scale=100.0)
    return row


def load_strategy_stats(meta_path: Path, strategy: str) -> dict[str, Any]:
    if not meta_path.exists():
        return {}
    zip_path = meta_path.with_suffix("").with_suffix(".zip")
    if not zip_path.exists():
        return {}
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = [m for m in zf.namelist() if m.endswith(".json") and "_config" not in m]
            for member in members:
                payload = json.loads(zf.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                strategy_map = payload.get("strategy")
                if not isinstance(strategy_map, dict):
                    continue
                stats = strategy_map.get(strategy)
                if isinstance(stats, dict):
                    return stats
    except Exception:
        return {}
    return {}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c) for c in COLUMNS})


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_md(path: Path, rows: list[dict[str, Any]], status_path: Path | None) -> None:
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    pf_values = [float(v) for v in (r.get("profit_factor") for r in ok_rows) if v is not None]
    profit_values = [float(v) for v in (r.get("total_profit_pct") for r in ok_rows) if v is not None]

    lines = [
        "# Walk-forward 1h Report",
        "",
        f"- generated_utc: {datetime.now(timezone.utc).isoformat()}",
        f"- windows_total: {len(rows)}",
        f"- windows_ok: {len(ok_rows)}",
        f"- status_source: {status_path if status_path else 'not_found'}",
        "",
        "|window_name|timerange|strategy|trades|total_profit_pct|total_profit_usdt|profit_factor|max_drawdown_pct|status|",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "|" + "|".join(
                to_cell(row.get(k))
                for k in [
                    "window_name",
                    "timerange",
                    "strategy",
                    "trades",
                    "total_profit_pct",
                    "total_profit_usdt",
                    "profit_factor",
                    "max_drawdown_pct",
                    "status",
                ]
            ) + "|"
        )
    if not rows:
        lines.append("|-|-|-|-|-|-|-|-|-|")

    lines.extend(
        [
            "",
            "## Resumen (solo ventanas status=ok)",
            "",
            f"- avg_profit_factor: {safe_stat_mean(pf_values)}",
            f"- median_profit_factor: {safe_stat_median(pf_values)}",
            f"- avg_total_profit_pct: {safe_stat_mean(profit_values)}",
            f"- median_total_profit_pct: {safe_stat_median(profit_values)}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def safe_json_load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def as_float(value: Any, scale: float = 1.0) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value) * scale
    except Exception:
        return None


def as_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except Exception:
        return None


def to_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "/")


def safe_stat_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.mean(values))


def safe_stat_median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


if __name__ == "__main__":
    raise SystemExit(main())
