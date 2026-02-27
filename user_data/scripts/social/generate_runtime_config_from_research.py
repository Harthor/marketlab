from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate runtime Freqtrade config from research candidates CSV."
    )
    parser.add_argument("--base-config", required=True)
    parser.add_argument("--candidates-csv", required=True)
    parser.add_argument("--output-config", required=True)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--quote", default="USDT")
    args = parser.parse_args()

    quote = args.quote.upper().strip()
    top_n = max(1, int(args.top_n))

    candidates = _load_candidates(Path(args.candidates_csv), quote=quote)
    candidates.sort(key=lambda r: (float(r["score"]), int(r["mentions"])), reverse=True)

    pair_whitelist: list[str] = []
    seen: set[str] = set()
    for row in candidates:
        pair = row["pair"]
        if pair in seen:
            continue
        seen.add(pair)
        pair_whitelist.append(pair)
        if len(pair_whitelist) >= top_n:
            break

    base_cfg_path = Path(args.base_config)
    output_cfg_path = Path(args.output_config)
    cfg = json.loads(base_cfg_path.read_text(encoding="utf-8"))
    cfg.setdefault("exchange", {})
    cfg["exchange"]["pair_whitelist"] = pair_whitelist

    output_cfg_path.parent.mkdir(parents=True, exist_ok=True)
    output_cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    summary = {
        "status": "ok",
        "pairs_count": len(pair_whitelist),
        "output_config": str(output_cfg_path),
        "quote": quote,
        "top_n": top_n,
    }
    print(json.dumps(summary, ensure_ascii=True))
    return 0


def _load_candidates(path: Path, quote: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pair = _normalize_to_pair(str(row.get("symbol", "") or ""), quote=quote)
            if not pair:
                continue
            if pair.split("/", 1)[1] != quote:
                continue
            out.append(
                {
                    "pair": pair,
                    "score": _as_float(row.get("score"), 0.0),
                    "mentions": _as_int(row.get("mentions"), 0),
                }
            )
    return out


def _normalize_to_pair(symbol: str, quote: str) -> str:
    text = symbol.strip().upper()
    if not text:
        return ""
    text = text.replace("-", "_")
    if "/" in text:
        base, q = text.split("/", 1)
        if not base or not q:
            return ""
        return f"{base}/{q}"
    if "_" in text:
        base, q = text.split("_", 1)
        if not base:
            return ""
        q_norm = q or quote
        return f"{base}/{q_norm}"
    return f"{text}/{quote}"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


if __name__ == "__main__":
    raise SystemExit(main())

