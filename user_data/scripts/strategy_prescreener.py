#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


MICROSTRUCTURE_TERMS = {
    "orderbook",
    "order book",
    "level2",
    "l2",
    "ticks",
    "tick",
    "footprint",
    "dom",
    "queue",
    "latency",
    "spread micro",
    "intrabar",
}
LOOKAHEAD_TERMS = {
    "future candle",
    "next candle close",
    "tomorrow close",
    "uses future",
    "lookahead",
    "forward return",
}
OHLCV_HARD_TERMS = {"funding rate", "news sentiment", "twitter", "reddit", "orderflow", "onchain"}


def _load_text(args: argparse.Namespace) -> str:
    if args.spec and Path(args.spec).exists():
        return Path(args.spec).read_text(encoding="utf-8")
    if args.description:
        return args.description
    if args.from_file:
        return Path(args.from_file).read_text(encoding="utf-8")
    raise SystemExit("Provide --description, --from-file or --spec")


def _count_matches(text: str, terms: set[str]) -> int:
    lo = text.lower()
    return sum(1 for t in terms if t in lo)


def _has_structure(text: str) -> dict[str, bool]:
    lo = text.lower()
    return {
        "has_hypothesis": "hypothesis" in lo or "hipotesis" in lo,
        "has_entry": "entry" in lo or "entrada" in lo,
        "has_exit": "exit" in lo or "salida" in lo,
        "has_stop": "stop" in lo or "stoploss" in lo,
        "has_regime": "regime" in lo or "régimen" in lo or "regimen" in lo,
    }


def _score(text: str, timeframe: str | None) -> dict[str, Any]:
    tf = (timeframe or "").strip().lower()
    micro_hits = _count_matches(text, MICROSTRUCTURE_TERMS)
    lookahead_hits = _count_matches(text, LOOKAHEAD_TERMS)
    hard_hits = _count_matches(text, OHLCV_HARD_TERMS)
    structure = _has_structure(text)
    structure_count = sum(1 for v in structure.values() if v)

    implementability = max(0.0, 100.0 - (hard_hits * 25.0) - (micro_hits * 20.0))
    lookahead_risk = max(0.0, 100.0 - (lookahead_hits * 35.0))
    microstructure = max(0.0, 100.0 - (micro_hits * 30.0))
    freqtrade_compat = max(0.0, min(100.0, 100.0 - (hard_hits * 20.0) - (micro_hits * 15.0)))
    if tf in {"1h", "4h"}:
        preference_alignment = 100.0
    elif tf in {"2h"}:
        preference_alignment = 75.0
    elif tf in {"15m", "30m", "5m", "1m", "3m"}:
        preference_alignment = 20.0
    else:
        preference_alignment = 55.0
    hypothesis_clarity = (structure_count / 5.0) * 100.0

    score_total = (
        implementability * 0.22
        + lookahead_risk * 0.20
        + microstructure * 0.16
        + freqtrade_compat * 0.16
        + preference_alignment * 0.10
        + hypothesis_clarity * 0.16
    )

    flags: list[str] = []
    if micro_hits > 0:
        flags.append("needs_orderflow")
    if lookahead_hits > 0:
        flags.append("lookahead_risk")
    if structure_count < 4:
        flags.append("needs_spec_detail")
    if not structure["has_exit"]:
        flags.append("ambiguous_exit")
    if tf in {"1m", "3m", "5m", "15m", "30m"}:
        flags.append("preference_mismatch_timeframe")
    if hard_hits > 0:
        flags.append("non_ohlcv_dependency")

    if score_total >= 75 and "non_ohlcv_dependency" not in flags:
        recommendation = "IMPLEMENT"
    elif score_total >= 50:
        recommendation = "NEEDS_SPEC"
    else:
        recommendation = "DISCARD_IDEA"

    return {
        "score_total": round(score_total, 2),
        "sub_scores": {
            "implementability_ohlcv": round(implementability, 2),
            "lookahead_safety": round(lookahead_risk, 2),
            "microstructure_independence": round(microstructure, 2),
            "freqtrade_compatibility": round(freqtrade_compat, 2),
            "preference_alignment": round(preference_alignment, 2),
            "hypothesis_clarity": round(hypothesis_clarity, 2),
        },
        "flags": flags,
        "recommendation": recommendation,
        "diagnostics": {
            "microstructure_hits": micro_hits,
            "lookahead_hits": lookahead_hits,
            "non_ohlcv_hits": hard_hits,
            "structure": structure,
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Pre-screen strategy ideas before coding/backtesting.")
    p.add_argument("--description", default="", help="Plain strategy idea text")
    p.add_argument("--from-file", default="", help="Path to text/markdown file with strategy idea")
    p.add_argument("--spec", default="", help="Path to structured spec markdown/json")
    p.add_argument("--timeframe", default="", help="Target timeframe hint (1h/4h/etc)")
    p.add_argument("--out", default="", help="Optional output JSON path")
    args = p.parse_args()

    text = _load_text(args)
    result = _score(text, args.timeframe)
    result["timeframe"] = args.timeframe or "unspecified"

    print(json.dumps(result, indent=2, ensure_ascii=True))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
