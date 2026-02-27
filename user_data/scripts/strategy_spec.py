#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_KEYS = [
    "id",
    "family",
    "hypothesis",
    "market_regime_target",
    "timeframe",
    "universe_assumptions",
    "indicators",
    "entry_rules",
    "exit_rules",
    "risk_rules",
    "anti_lookahead_notes",
]


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2]


def _spec_dir() -> Path:
    return _repo_root() / "user_data" / "research" / "strategy_specs"


def cmd_new(args: argparse.Namespace) -> int:
    spec_dir = _spec_dir()
    spec_dir.mkdir(parents=True, exist_ok=True)
    src = spec_dir / ("STRATEGY_SPEC_TEMPLATE.json" if args.format == "json" else "STRATEGY_SPEC_TEMPLATE.md")
    dst = spec_dir / f"{args.spec_id}.{args.format}"
    if dst.exists() and not args.force:
        raise SystemExit(f"Spec already exists: {dst} (use --force)")
    text = src.read_text(encoding="utf-8")
    if args.format == "json":
        obj = json.loads(text)
        obj["id"] = args.spec_id
        text = json.dumps(obj, indent=2, ensure_ascii=True) + "\n"
    else:
        text = text.replace("stratXX_name_v1", args.spec_id)
    dst.write_text(text, encoding="utf-8")
    print(dst)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    p = Path(args.spec)
    if not p.is_absolute():
        p = (_repo_root() / p).resolve()
    if not p.exists():
        raise SystemExit(f"Spec not found: {p}")

    if p.suffix.lower() != ".json":
        # Markdown validation is checklist-like.
        text = p.read_text(encoding="utf-8").lower()
        checks = {
            "hypothesis": "hypothesis" in text,
            "entry": "entry rules" in text or "entry" in text,
            "exit": "exit rules" in text or "exit" in text,
            "risk": "risk" in text or "stop" in text,
            "anti_lookahead": "anti-lookahead" in text or "lookahead" in text,
        }
        score = int((sum(1 for v in checks.values() if v) / len(checks)) * 100)
        out = {
            "spec": str(p),
            "format": "markdown",
            "completeness_score": score,
            "checks": checks,
            "missing": [k for k, v in checks.items() if not v],
        }
        print(json.dumps(out, indent=2, ensure_ascii=True))
        return 0

    obj = json.loads(p.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_KEYS if k not in obj]
    empty = [k for k in REQUIRED_KEYS if k in obj and (obj[k] in ("", [], {}, None))]
    score = int((1.0 - ((len(missing) + len(empty)) / (len(REQUIRED_KEYS) * 2))) * 100)
    out = {
        "spec": str(p),
        "format": "json",
        "completeness_score": max(0, score),
        "missing_keys": missing,
        "empty_keys": empty,
    }
    print(json.dumps(out, indent=2, ensure_ascii=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create/validate structured strategy specs.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new")
    p_new.add_argument("--spec-id", required=True)
    p_new.add_argument("--format", choices=["json", "md"], default="json")
    p_new.add_argument("--force", action="store_true", default=False)
    p_new.set_defaults(func=cmd_new)

    p_val = sub.add_parser("validate")
    p_val.add_argument("--spec", required=True)
    p_val.set_defaults(func=cmd_validate)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
