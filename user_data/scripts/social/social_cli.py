from __future__ import annotations

import argparse
import json
import logging
import sys
from glob import glob

from .social_features_1h import build_features_1h
from .social_ingest import ingest
from .merge_social_features import merge_with_candles_csv
from .social_normalize import normalize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Social pipeline CLI")
    parser.add_argument("--log-level", default="INFO")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("--output-jsonl", "--output", dest="output_jsonl", required=True)
    ingest_parser.add_argument("--source", "--sources", dest="source_items", action="append", default=[])
    ingest_parser.add_argument("--external-jsonl", "--external-jsonl-path", dest="external_jsonl", action="append", default=[])
    ingest_parser.add_argument("--external-jsonl-glob", default="")

    normalize_parser = subparsers.add_parser("normalize")
    normalize_parser.add_argument("--input-jsonl", required=True)
    normalize_parser.add_argument("--output-jsonl", required=True)

    features_parser = subparsers.add_parser("features-1h")
    features_parser.add_argument("--input-jsonl", required=True)
    features_parser.add_argument("--output-jsonl", required=True)
    features_parser.add_argument("--output-csv", required=True)

    merge_parser = subparsers.add_parser("merge-with-candles")
    merge_parser.add_argument("--candles-csv", required=True)
    merge_parser.add_argument("--social-features-csv", required=True)
    merge_parser.add_argument("--output-csv", required=True)
    merge_parser.add_argument("--timestamp-col", default="timestamp")
    merge_parser.add_argument("--symbol-col", default="symbol")
    merge_parser.add_argument("--include-unknown", action="store_true")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(message)s",
    )

    try:
        if args.command == "ingest":
            sources = _parse_sources(args.source_items)
            external_paths = list(args.external_jsonl)
            matched_from_glob = 0
            if args.external_jsonl_glob:
                globbed = sorted(glob(args.external_jsonl_glob))
                matched_from_glob = len(globbed)
                external_paths.extend(globbed)
            logging.getLogger("social_cli").info(
                "stage=ingest_cli sources=%s external_jsonl_matched=%d",
                ",".join(sources),
                matched_from_glob,
            )
            summary = ingest(
                out_raw_jsonl=args.output_jsonl,
                sources_requested=sources,
                external_jsonl_paths=external_paths,
            )
            print(json.dumps(summary, ensure_ascii=True))
            return 0

        if args.command == "normalize":
            summary, _rows = normalize(args.input_jsonl, args.output_jsonl)
            print(json.dumps(summary, ensure_ascii=True))
            return 0

        if args.command == "features-1h":
            summary = build_features_1h(args.input_jsonl, args.output_jsonl, args.output_csv)
            print(json.dumps(summary, ensure_ascii=True))
            return 0

        if args.command == "merge-with-candles":
            summary = merge_with_candles_csv(
                candles_csv=args.candles_csv,
                social_features_csv=args.social_features_csv,
                out_csv=args.output_csv,
                timestamp_col=args.timestamp_col,
                symbol_col=args.symbol_col,
                include_unknown=args.include_unknown,
            )
            print(json.dumps(summary, ensure_ascii=True))
            return 0

        return 2
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 2


def _parse_sources(source_items: list[str]) -> list[str]:
    if not source_items:
        return ["mock"]
    sources: list[str] = []
    for item in source_items:
        for part in str(item).split(","):
            source = part.strip()
            if source:
                sources.append(source)
    return sources or ["mock"]


if __name__ == "__main__":
    raise SystemExit(main())
