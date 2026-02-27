from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .social_specs import coerce_event

LOGGER = logging.getLogger("social_normalize")
SYMBOL_ALIASES: dict[str, list[str]] = {
    "BTC": ["btc", "bitcoin"],
    "ETH": ["eth", "ethereum"],
    "SOL": ["sol", "solana"],
    "XRP": ["xrp", "ripple"],
    "BNB": ["bnb", "binance coin"],
    "ARB": ["arb", "arbitrum"],
    "OP": ["op", "optimism"],
}
_PREFIXED_SYMBOL_RE = re.compile(r"[$#]\s*([A-Za-z]{2,12})\b")
_WORD_TOKEN_RE = re.compile(r"\b([A-Za-z]{2,12})\b")
_ALIAS_PATTERN_BY_SYMBOL: dict[str, list[re.Pattern[str]]] = {}
_ALIASES_TO_SYMBOL: dict[str, str] = {}

for _symbol, _aliases in SYMBOL_ALIASES.items():
    _patterns: list[re.Pattern[str]] = []
    for _alias in _aliases:
        _ALIASES_TO_SYMBOL[_alias.lower()] = _symbol
        _escaped = re.escape(_alias.lower()).replace(r"\ ", r"\s+")
        _patterns.append(re.compile(rf"(?<![a-z0-9]){_escaped}(?![a-z0-9])", re.IGNORECASE))
    _ALIAS_PATTERN_BY_SYMBOL[_symbol] = _patterns


def normalize(in_raw_jsonl: str, out_norm_jsonl: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    in_path = Path(in_raw_jsonl)
    out_path = Path(out_norm_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not in_path.exists() or in_path.stat().st_size == 0:
        out_path.write_text("", encoding="utf-8")
        summary = {"status": "ok", "rows_in": 0, "rows_out": 0, "output_jsonl": str(out_path)}
        LOGGER.info("stage=normalize rows_in=0 rows_out=0 output=%s", out_path)
        return summary, []

    rows_out: list[dict[str, Any]] = []
    rows_in = 0
    unknown_count = 0

    with in_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows_in += 1
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue

            row = coerce_event(payload)
            row["ts_utc"] = _normalize_ts(row.get("ts_utc"))
            text = str(row.get("text", "") or "")
            symbols = _detect_symbols(text)
            if not symbols:
                symbols = ["UNKNOWN"]
                unknown_count += 1
            metadata = row.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            metadata["symbols_detected"] = symbols
            row["metadata"] = metadata
            rows_out.append(row)

    with out_path.open("w", encoding="utf-8") as f:
        for row in rows_out:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")

    rows_out_count = len(rows_out)
    unknown_ratio = (unknown_count / rows_out_count) if rows_out_count > 0 else 0.0
    summary = {
        "status": "ok",
        "rows_in": rows_in,
        "rows_out": rows_out_count,
        "total_unknown_count": unknown_count,
        "unknown_ratio": round(unknown_ratio, 6),
        "output_jsonl": str(out_path),
    }
    LOGGER.info("stage=normalize rows_in=%d rows_out=%d output=%s", rows_in, len(rows_out), out_path)
    return summary, rows_out


def _normalize_ts(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return str(value or "")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _detect_symbols(text: str) -> list[str]:
    if not text:
        return []

    out: list[str] = []
    seen: set[str] = set()

    # Prefixed forms: $BTC, #ETH, etc.
    for match in _PREFIXED_SYMBOL_RE.finditer(text):
        token = (match.group(1) or "").lower()
        symbol = _ALIASES_TO_SYMBOL.get(token, token.upper() if token.upper() in SYMBOL_ALIASES else "")
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)

    # Full-name aliases with robust boundaries, e.g., "binance coin", "ethereum".
    for symbol, patterns in _ALIAS_PATTERN_BY_SYMBOL.items():
        if symbol in seen:
            continue
        for pattern in patterns:
            if pattern.search(text):
                seen.add(symbol)
                out.append(symbol)
                break

    # Bare ticker tokens, case-insensitive, but boundary-safe.
    for match in _WORD_TOKEN_RE.finditer(text):
        token_upper = (match.group(1) or "").upper()
        if token_upper in SYMBOL_ALIASES and token_upper not in seen:
            seen.add(token_upper)
            out.append(token_upper)
    return out
