from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export merged candles+social CSV into per-pair files for Freqtrade."
    )
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if "timestamp" not in fieldnames:
            raise ValueError("Missing required column: timestamp")
        if "symbol" not in fieldnames:
            raise ValueError("Missing required column: symbol")

        by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in reader:
            symbol_norm = _normalize_symbol(str(row.get("symbol", "") or ""))
            if not symbol_norm:
                continue
            out_row = dict(row)
            out_row["symbol"] = symbol_norm
            out_row["timestamp"] = _normalize_timestamp_iso8601(str(row.get("timestamp", "") or ""))
            by_symbol[symbol_norm].append(out_row)

    summary: dict[str, int] = {}
    for symbol_norm, rows in sorted(by_symbol.items()):
        rows.sort(key=lambda r: r.get("timestamp", ""))
        out_file = output_dir / f"{symbol_norm}_1h.csv"
        with out_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        summary[symbol_norm] = len(rows)

    print("Export summary:")
    for symbol_norm, count in summary.items():
        print(f"- {symbol_norm}: {count} rows")
    return 0


def _normalize_symbol(symbol: str) -> str:
    text = symbol.strip().upper()
    if not text:
        return ""
    return text.replace("/", "_")


def _normalize_timestamp_iso8601(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if text.isdigit():
        dt = datetime.fromtimestamp(float(text), tz=timezone.utc)
        return dt.isoformat()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(normalized)
    except Exception:
        return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())

