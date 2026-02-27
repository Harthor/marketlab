from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("social_features_1h")


def build_features_1h(in_norm_jsonl: str, out_jsonl: str, out_csv: str) -> dict[str, Any]:
    in_path = Path(in_norm_jsonl)
    out_jsonl_path = Path(out_jsonl)
    out_csv_path = Path(out_csv)
    out_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)

    rows_in = 0
    aggregates: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"mentions_count": 0, "eng_sum": 0.0, "eng_n": 0})

    if in_path.exists() and in_path.stat().st_size > 0:
        with in_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows_in += 1
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue

                ts_hour = _bucket_hour_utc(str(row.get("ts_utc", "") or ""))
                symbols = _get_symbols(row) or ["UNKNOWN"]
                eng = _to_float(row.get("engagement_score"))
                for symbol in symbols:
                    key = (ts_hour, symbol)
                    agg = aggregates[key]
                    agg["mentions_count"] += 1
                    if eng is not None:
                        agg["eng_sum"] += eng
                        agg["eng_n"] += 1

    feature_rows: list[dict[str, Any]] = []
    for (bucket_start, symbol), agg in sorted(aggregates.items()):
        avg_eng = (agg["eng_sum"] / agg["eng_n"]) if agg["eng_n"] > 0 else None
        feature_rows.append(
            {
                "bucket_start": bucket_start,
                "symbol": symbol,
                "mentions_count": agg["mentions_count"],
                "avg_engagement_score": avg_eng,
            }
        )

    with out_jsonl_path.open("w", encoding="utf-8") as f:
        for row in feature_rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")

    fieldnames = ["bucket_start", "symbol", "mentions_count", "avg_engagement_score"]
    with out_csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        if feature_rows:
            writer.writerows(feature_rows)

    summary = {
        "status": "ok",
        "timeframe": "1h",
        "rows_in": rows_in,
        "rows_out": len(feature_rows),
        "output_jsonl": str(out_jsonl_path),
        "output_csv": str(out_csv_path),
    }
    LOGGER.info("stage=features_1h rows_in=%d rows_out=%d output=%s", rows_in, len(feature_rows), out_csv_path)
    return summary


def _bucket_hour_utc(ts_text: str) -> str:
    text = (ts_text or "").strip()
    if not text:
        return ""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return dt.isoformat()


def _get_symbols(row: dict[str, Any]) -> list[str]:
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        symbols = metadata.get("symbols_detected")
        if isinstance(symbols, list):
            out = [str(s).upper() for s in symbols if str(s).strip()]
            return sorted(set(out))
    return []


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None

