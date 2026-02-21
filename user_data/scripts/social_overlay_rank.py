#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("social_overlay_rank")


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _base_symbol(pair_or_symbol: str) -> str:
    text = (pair_or_symbol or "").upper().strip()
    if "/" in text:
        return text.split("/", 1)[0]
    return text


def _normalize_column(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if abs(hi - lo) < 1e-12:
        return {k: 0.0 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def load_pair_ranking(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_social_features(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def build_social_symbol_score(features: list[dict[str, Any]], recent_buckets: int = 50) -> dict[str, float]:
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in features:
        sym = _base_symbol(str(row.get("symbol", "")))
        if sym:
            by_symbol.setdefault(sym, []).append(row)

    mentions_raw: dict[str, float] = {}
    sent_abs_raw: dict[str, float] = {}
    recency_sent_raw: dict[str, float] = {}
    diversity_raw: dict[str, float] = {}

    for sym, rows in by_symbol.items():
        rows_sorted = sorted(rows, key=lambda r: str(r.get("bucket_start", "")))
        recent = rows_sorted[-max(1, recent_buckets):]
        mentions_raw[sym] = sum(_as_float(r.get("mentions_count"), 0.0) for r in recent)
        sent_abs_raw[sym] = sum(_as_float(r.get("sentiment_abs_mean"), 0.0) for r in recent) / max(1, len(recent))
        recency_sent_raw[sym] = sum(_as_float(r.get("recency_weighted_sentiment"), 0.0) for r in recent) / max(1, len(recent))
        diversity_raw[sym] = sum(_as_float(r.get("source_diversity_score"), 0.0) for r in recent) / max(1, len(recent))

    mentions_n = _normalize_column(mentions_raw)
    sent_abs_n = _normalize_column(sent_abs_raw)
    recency_sent_n = _normalize_column(recency_sent_raw)
    diversity_n = _normalize_column(diversity_raw)

    out: dict[str, float] = {}
    keys = set(mentions_n) | set(sent_abs_n) | set(recency_sent_n) | set(diversity_n)
    for sym in keys:
        out[sym] = (
            0.35 * mentions_n.get(sym, 0.0)
            + 0.25 * sent_abs_n.get(sym, 0.0)
            + 0.25 * recency_sent_n.get(sym, 0.0)
            + 0.15 * diversity_n.get(sym, 0.0)
        )
    return out


def _parse_weight_grid(weight_grid: str) -> list[float]:
    vals = []
    for part in weight_grid.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            x = float(part)
        except Exception:
            continue
        vals.append(max(0.0, min(1.0, x)))
    return sorted(set(vals)) or [0.0, 0.05, 0.10, 0.20, 0.30]


def main() -> int:
    parser = argparse.ArgumentParser(description="Experimental social overlay ranking v2 (grid mode).")
    parser.add_argument("--pair-ranking-csv", required=True)
    parser.add_argument("--social-features-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--weight-grid", default="0.0,0.05,0.10,0.20,0.30")
    parser.add_argument("--w-social", type=float, default=None, help="Backward-compatible single weight override.")
    parser.add_argument("--recent-buckets", type=int, default=50)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")

    ranking = load_pair_ranking(Path(args.pair_ranking_csv))
    social = load_social_features(Path(args.social_features_csv))
    social_score = build_social_symbol_score(social, recent_buckets=max(1, args.recent_buckets))

    if args.w_social is not None:
        weight_grid = [max(0.0, min(1.0, float(args.w_social)))]
    else:
        weight_grid = _parse_weight_grid(args.weight_grid)

    # Base order reference.
    base_sorted = sorted(ranking, key=lambda r: _as_float(r.get("score"), 0.0), reverse=True)
    base_rank = {str(r.get("symbol", "")): idx + 1 for idx, r in enumerate(base_sorted)}

    rows_out: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    for w_social in weight_grid:
        w_base = 1.0 - w_social
        temp: list[dict[str, Any]] = []
        for row in ranking:
            symbol_pair = str(row.get("symbol", ""))
            sym = _base_symbol(symbol_pair)
            base = _as_float(row.get("score"), 0.0)
            s_score = social_score.get(sym, 0.0)
            combined = (w_base * base) + (w_social * s_score)
            out = dict(row)
            out["w_social"] = round(w_social, 4)
            out["base_score"] = round(base, 8)
            out["social_score"] = round(s_score, 8)
            out["combined_score"] = round(combined, 8)
            out["overlay_mode"] = "diagnostic_only"
            temp.append(out)

        temp.sort(key=lambda r: _as_float(r.get("combined_score"), 0.0), reverse=True)
        rank_shift_abs_sum = 0
        for idx, row in enumerate(temp, start=1):
            row["combined_rank"] = idx
            b_rank = base_rank.get(str(row.get("symbol", "")), idx)
            row["base_rank"] = b_rank
            row["rank_diff_vs_base"] = int(b_rank) - int(idx)
            rank_shift_abs_sum += abs(int(row["rank_diff_vs_base"]))

        rows_out.extend(temp)
        summary_rows.append(
            {
                "w_social": round(w_social, 4),
                "rows": len(temp),
                "avg_abs_rank_shift": round(rank_shift_abs_sum / max(1, len(temp)), 6),
                "top_symbol": str(temp[0].get("symbol", "")) if temp else "",
            }
        )

    out_path = Path(args.output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows_out[0].keys()) if rows_out else []
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    summary = {
        "rows_in": len(ranking),
        "social_feature_rows": len(social),
        "weight_grid": weight_grid,
        "summary_by_weight": summary_rows,
        "output_csv": str(out_path),
    }
    if args.summary_json:
        p = Path(args.summary_json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    LOGGER.info("Input pair rows: %d", len(ranking))
    LOGGER.info("Input social feature rows: %d", len(social))
    LOGGER.info("Weight grid: %s", weight_grid)
    LOGGER.info("Output combined rows: %d", len(rows_out))
    LOGGER.info("Output: %s", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
