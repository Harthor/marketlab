#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKTEST_DIR = REPO_ROOT / "user_data" / "backtest_results"
REPORTS_DIR = REPO_ROOT / "user_data" / "reports"
CSV_OUT = REPORTS_DIR / "backtest_index.csv"
JSON_OUT = REPORTS_DIR / "backtest_index.json"
MD_OUT = REPORTS_DIR / "backtest_dashboard.md"

COLUMNS = [
    "file",
    "timestamp_utc",
    "strategy",
    "timerange_from",
    "timerange_to",
    "total_profit_pct",
    "total_profit_usdt",
    "profit_factor",
    "max_drawdown_pct",
    "trades",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build backtest index and markdown dashboard.")
    parser.add_argument(
        "--backtest-dir",
        default=str(BACKTEST_DIR),
        help="Directory with backtest-result-*.meta.json files.",
    )
    parser.add_argument(
        "--reports-dir",
        default=str(REPORTS_DIR),
        help="Directory for outputs: CSV/JSON/Markdown.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    backtest_dir = Path(args.backtest_dir)
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_out = reports_dir / CSV_OUT.name
    json_out = reports_dir / JSON_OUT.name
    md_out = reports_dir / MD_OUT.name

    meta_files = sorted(backtest_dir.glob("backtest-result-*.meta.json"))
    rows: list[dict[str, Any]] = []
    missing_fields_count = 0

    for meta_path in meta_files:
        row = parse_meta(meta_path)
        if has_missing_fields(row):
            missing_fields_count += 1
        rows.append(row)

    rows.sort(
        key=lambda r: (
            as_datetime(r.get("timestamp_utc")) or datetime.fromtimestamp(0, tz=timezone.utc)
        ),
        reverse=True,
    )

    write_csv(csv_out, rows)
    write_json(json_out, rows)
    write_dashboard(md_out, rows, missing_fields_count)

    print(f"[build_backtest_index] rows={len(rows)} csv={csv_out}")
    print(f"[build_backtest_index] json={json_out}")
    print(f"[build_backtest_index] dashboard={md_out}")
    return 0


def parse_meta(meta_path: Path) -> dict[str, Any]:
    payload = safe_load_json(meta_path)
    strategy = first_key(payload)
    meta_obj = payload.get(strategy, {}) if strategy else {}
    if not isinstance(meta_obj, dict):
        meta_obj = {}

    start_ts = as_float(meta_obj.get("backtest_start_ts"))
    end_ts = as_float(meta_obj.get("backtest_end_ts"))
    run_ts = as_float(meta_obj.get("backtest_start_time")) or end_ts or start_ts

    row: dict[str, Any] = {
        "file": str(meta_path),
        "timestamp_utc": ts_to_iso(run_ts),
        "strategy": strategy,
        "timerange_from": ts_to_date(start_ts),
        "timerange_to": ts_to_date(end_ts),
        "total_profit_pct": None,
        "total_profit_usdt": None,
        "profit_factor": None,
        "max_drawdown_pct": None,
        "trades": None,
    }

    strategy_stats = load_strategy_stats(meta_path, strategy)
    if strategy_stats:
        row["total_profit_pct"] = scaled_percent(strategy_stats.get("profit_total"))
        row["total_profit_usdt"] = as_float(strategy_stats.get("profit_total_abs"))
        row["profit_factor"] = as_float(strategy_stats.get("profit_factor"))
        row["max_drawdown_pct"] = scaled_percent(strategy_stats.get("max_drawdown_account"))
        row["trades"] = as_int(strategy_stats.get("total_trades"))

    return row


def load_strategy_stats(meta_path: Path, strategy: str | None) -> dict[str, Any]:
    if not strategy:
        return {}
    zip_path = meta_path.with_suffix("").with_suffix(".zip")
    if not zip_path.exists():
        return {}
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = [name for name in zf.namelist() if name.endswith(".json") and "_config" not in name]
            for member in members:
                payload = json.loads(zf.read(member).decode("utf-8"))
                if not isinstance(payload, dict):
                    continue
                strategy_map = payload.get("strategy", {})
                if isinstance(strategy_map, dict):
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
            writer.writerow({k: row.get(k) for k in COLUMNS})


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_dashboard(path: Path, rows: list[dict[str, Any]], missing_fields_count: int) -> None:
    latest10 = rows[:10]
    top_profit = sorted(
        [r for r in rows if as_float(r.get("total_profit_pct")) is not None],
        key=lambda r: as_float(r.get("total_profit_pct")) or float("-inf"),
        reverse=True,
    )[:10]
    top_pf = sorted(
        [
            r
            for r in rows
            if (as_float(r.get("profit_factor")) is not None and (as_int(r.get("trades")) or 0) > 10)
        ],
        key=lambda r: as_float(r.get("profit_factor")) or float("-inf"),
        reverse=True,
    )[:10]

    lines: list[str] = []
    lines.append("# Backtest Dashboard")
    lines.append("")
    lines.append(f"- generated_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- total_runs_indexed: {len(rows)}")
    lines.append(f"- missing_fields_runs: {missing_fields_count}")
    lines.append("")
    lines.append("## Ultimos 10 runs")
    lines.append("")
    lines.extend(render_table(latest10))
    lines.append("")
    lines.append("## Top 10 por total_profit_pct")
    lines.append("")
    lines.extend(render_table(top_profit))
    lines.append("")
    lines.append("## Top 10 por profit_factor (trades > 10)")
    lines.append("")
    lines.extend(render_table(top_pf))
    lines.append("")
    if missing_fields_count > 0:
        lines.append(f"Nota: hay {missing_fields_count} run(s) con campos faltantes o no parseables.")
    else:
        lines.append("Nota: no se detectaron campos faltantes en los runs parseados.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def render_table(rows: list[dict[str, Any]]) -> list[str]:
    headers = [
        "timestamp_utc",
        "strategy",
        "timerange_from",
        "timerange_to",
        "total_profit_pct",
        "profit_factor",
        "max_drawdown_pct",
        "trades",
        "file",
    ]
    out = [
        "|" + "|".join(headers) + "|",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        out.append(
            "|" + "|".join(safe_cell(row.get(h)) for h in headers) + "|"
        )
    if not rows:
        out.append("|-|-|-|-|-|-|-|-|-|")
    return out


def safe_load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def has_missing_fields(row: dict[str, Any]) -> bool:
    for key in ("timestamp_utc", "strategy", "timerange_from", "timerange_to"):
        if row.get(key) in (None, "", "null"):
            return True
    return False


def first_key(d: dict[str, Any]) -> str | None:
    for key in d.keys():
        return key
    return None


def scaled_percent(value: Any) -> float | None:
    number = as_float(value)
    if number is None:
        return None
    return number * 100.0


def as_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def as_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except Exception:
        return None


def ts_to_iso(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    except Exception:
        return None


def ts_to_date(value: float | None) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def as_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def safe_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("|", "/")
    return text


if __name__ == "__main__":
    raise SystemExit(main())
