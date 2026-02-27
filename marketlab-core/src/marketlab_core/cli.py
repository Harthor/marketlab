"""Command line interface for marketlab-core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import polars as pl

from .io import DataCatalog, read_csv, read_parquet
from .storage import Cache
from .timeseries import align, compute_returns, parse_timestamps, resample_series
from .validation import validate_timestamp_series


def _load_dataset(path: str) -> pl.DataFrame:
    extension = Path(path).suffix.lower()
    if extension == ".parquet":
        return read_parquet(path)
    if extension == ".csv":
        return read_csv(path)
    raise ValueError("only .csv and .parquet are supported in the CLI")


def cmd_validate(args: argparse.Namespace) -> int:
    frame = _load_dataset(args.path)
    report = validate_timestamp_series(frame, ts_col=args.timestamp_column)
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok", False) else 1


def cmd_cache_info(args: argparse.Namespace) -> int:
    cache = Cache(root=args.cache_dir)
    stats = cache.cache_info()
    print(json.dumps(stats.__dict__, indent=2))
    return 0


def cmd_smoke_test(args: argparse.Namespace) -> int:
    base = pl.DataFrame(
        {
            "timestamp": parse_timestamps(
                [
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:01:00Z",
                    "2024-01-01T00:02:00Z",
                    "2024-01-01T00:03:00Z",
                    "2024-01-01T00:04:00Z",
                ]
            ),
            "value": [1.0, 1.1, 1.2, 1.3, 1.4],
        }
    )
    second = pl.DataFrame(
        {
            "timestamp": parse_timestamps(["2024-01-01T00:00:30Z", "2024-01-01T00:02:30Z", "2024-01-01T00:04:30Z"]),
            "value": [10, 11, 12],
        }
    )
    aligned = align([base, second], how="outer", freq="1m", method="ffill")
    returns = compute_returns(base, value_col="value", method="simple", horizon=1)
    _ = resample_series(base, freq="2m", agg="mean")
    cache = Cache(root=args.cache_dir)
    cache.set("smoke-test-aligned", aligned)
    cache.get("smoke-test-aligned")
    print("smoke-test: ok")
    print(f"aligned_rows={aligned.height}")
    print(f"returns_last={returns[-1, 'value_simple_ret_1']}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="marketlab-core")
    parser.add_argument("--cache-dir", default=str(Path.home() / ".cache" / "marketlab-core"), help="Cache directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_validate = subparsers.add_parser("validate", help="Validate timestamped dataframe")
    parser_validate.add_argument("path", help="Path to input file (.csv or .parquet)")
    parser_validate.add_argument("--timestamp-column", default="timestamp", help="Timestamp column name")
    parser_validate.set_defaults(func=cmd_validate)

    parser_cache = subparsers.add_parser("cache-info", help="Show cache index metadata")
    parser_cache.set_defaults(func=cmd_cache_info)

    parser_smoke = subparsers.add_parser("smoke-test", help="Run a small internal smoke test")
    parser_smoke.set_defaults(func=cmd_smoke_test)

    parser_catalog = subparsers.add_parser("catalog", help="Catalog helper commands")
    catalog_sub = parser_catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_ls = catalog_sub.add_parser("ls", help="List registered assets")
    catalog_ls.set_defaults(func=lambda args: _catalog_ls(args))

    return parser


def _catalog_ls(args: argparse.Namespace) -> int:
    catalog = DataCatalog(args.cache_dir)
    assets = catalog.list_assets()
    payload = [asset.__dict__ for asset in assets]
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
