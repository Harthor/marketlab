from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

LOGGER = logging.getLogger("merge_social_features")


def merge_with_candles_csv(
    candles_csv: str,
    social_features_csv: str,
    out_csv: str,
    timestamp_col: str = "timestamp",
    symbol_col: str = "symbol",
    include_unknown: bool = False,
) -> dict[str, Any]:
    candles_path = Path(candles_csv)
    social_path = Path(social_features_csv)
    out_path = Path(out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    social_index, social_summary = _load_social_index(social_path, include_unknown=include_unknown)
    with candles_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if timestamp_col not in fieldnames:
            raise ValueError(f"missing required column: {timestamp_col}")
        if symbol_col not in fieldnames:
            raise ValueError(f"missing required column: {symbol_col}")

        out_fields = list(fieldnames)
        if "social_mentions_count_1h" not in out_fields:
            out_fields.append("social_mentions_count_1h")
        if "social_avg_engagement_score_1h" not in out_fields:
            out_fields.append("social_avg_engagement_score_1h")
        if "social_bucket_start_utc" not in out_fields:
            out_fields.append("social_bucket_start_utc")

        rows_out: list[dict[str, Any]] = []
        rows_in = 0
        filled_zeros = 0
        for row in reader:
            rows_in += 1
            symbol = _norm_symbol(str(row.get(symbol_col, "") or ""))
            bucket_start = _bucket_1h_utc(str(row.get(timestamp_col, "") or ""))
            social = social_index.get((symbol, bucket_start))

            if social is None:
                row["social_mentions_count_1h"] = 0
                row["social_avg_engagement_score_1h"] = 0.0
                filled_zeros += 1
            else:
                row["social_mentions_count_1h"] = social["mentions_count"]
                row["social_avg_engagement_score_1h"] = social["avg_engagement_score"]
            row["social_bucket_start_utc"] = bucket_start
            rows_out.append(row)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(rows_out)

    summary = {
        "status": "ok",
        "rows_in": rows_in,
        "rows_out": len(rows_out),
        "filled_zeros": filled_zeros,
        "include_unknown": include_unknown,
        "social_rows_loaded": social_summary["rows_loaded"],
        "social_rows_skipped_unknown": social_summary["rows_skipped_unknown"],
        "output_csv": str(out_path),
    }
    LOGGER.info(
        "stage=merge_with_candles rows_in=%d rows_out=%d output=%s",
        rows_in,
        len(rows_out),
        out_path,
    )
    return summary


def merge_with_candle_rows(
    candle_rows: Iterable[dict[str, Any]],
    social_features_csv: str,
    timestamp_col: str = "timestamp",
    symbol_col: str = "symbol",
    include_unknown: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    social_index, social_summary = _load_social_index(Path(social_features_csv), include_unknown=include_unknown)
    rows_out: list[dict[str, Any]] = []
    rows_in = 0
    filled_zeros = 0
    for row in candle_rows:
        rows_in += 1
        out_row = dict(row)
        symbol = _norm_symbol(str(out_row.get(symbol_col, "") or ""))
        bucket_start = _bucket_1h_utc(str(out_row.get(timestamp_col, "") or ""))
        social = social_index.get((symbol, bucket_start))
        if social is None:
            out_row["social_mentions_count_1h"] = 0
            out_row["social_avg_engagement_score_1h"] = 0.0
            filled_zeros += 1
        else:
            out_row["social_mentions_count_1h"] = social["mentions_count"]
            out_row["social_avg_engagement_score_1h"] = social["avg_engagement_score"]
        out_row["social_bucket_start_utc"] = bucket_start
        rows_out.append(out_row)

    summary = {
        "status": "ok",
        "rows_in": rows_in,
        "rows_out": len(rows_out),
        "filled_zeros": filled_zeros,
        "include_unknown": include_unknown,
        "social_rows_loaded": social_summary["rows_loaded"],
        "social_rows_skipped_unknown": social_summary["rows_skipped_unknown"],
    }
    return rows_out, summary


def _load_social_index(path: Path, include_unknown: bool) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    rows_loaded = 0
    rows_skipped_unknown = 0
    if not path.exists() or path.stat().st_size == 0:
        return index, {"rows_loaded": 0, "rows_skipped_unknown": 0}

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = _norm_symbol(str(row.get("symbol", "") or ""))
            bucket_start = _bucket_1h_utc(str(row.get("bucket_start", "") or ""))
            if not symbol or not bucket_start:
                continue
            if symbol == "UNKNOWN" and not include_unknown:
                rows_skipped_unknown += 1
                continue
            key = (symbol, bucket_start)
            index[key] = {
                "mentions_count": _to_int(row.get("mentions_count"), default=0),
                "avg_engagement_score": _to_float(row.get("avg_engagement_score"), default=0.0),
            }
            rows_loaded += 1

    return index, {"rows_loaded": rows_loaded, "rows_skipped_unknown": rows_skipped_unknown}


def _bucket_1h_utc(ts_text: str) -> str:
    text = (ts_text or "").strip()
    if not text:
        return ""
    dt: datetime | None = None
    if text.isdigit():
        dt = datetime.fromtimestamp(float(text), tz=timezone.utc)
    else:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            dt = datetime.fromisoformat(normalized)
        except Exception:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
    dt = dt.replace(minute=0, second=0, microsecond=0)
    return dt.isoformat()


def _norm_symbol(value: str) -> str:
    text = value.upper().strip()
    if "/" in text:
        return text.split("/", 1)[0]
    return text


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default

