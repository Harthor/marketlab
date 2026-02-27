#!/usr/bin/env python3
"""Build research-ready BTC-USD dataset with target returns."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import numpy as np

SCHEMA_VERSION = "1.0"
DEFAULT_TARGET = "returns_1d"
PROVIDER = "builder"
REQUIRED_COLUMNS = ("ts_utc", "open", "high", "low", "close", "volume")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research-ready dataset with target labels.")
    parser.add_argument("--in", dest="in_path", default="data/datasets/BTC-USD/1d.parquet")
    parser.add_argument(
        "--out",
        default="data/datasets/BTC-USD/1d_research_ready.parquet",
        help="Output parquet path (default data/datasets/BTC-USD/1d_research_ready.parquet).",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help="Target name (default returns_1d).",
    )
    parser.add_argument(
        "--horizon-days",
        type=int,
        default=1,
        help="Forward horizon in days (default 1).",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=365,
        help="Minimum output rows for valid dataset (default 365).",
    )
    parser.add_argument(
        "--max-staleness-days",
        type=int,
        default=3,
        help="Max staleness in days for max ts_utc (default 3).",
    )
    return parser.parse_args()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    with temp_path.open("wb") as handle:
        handle.write(content)
    os.replace(temp_path, path)


def _atomic_write_parquet(frame: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    frame.to_parquet(temp_path, index=False, engine="pyarrow")
    os.replace(temp_path, path)
    return _sha256_file(path)


def _rotate_existing_backup(path: Path) -> Path | None:
    if not path.exists():
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.stem}_backup_{timestamp}{path.suffix}")
    try:
        path.rename(backup)
        print(f"INFO: previous output moved to backup: {backup}")
        return backup
    except OSError as exc:
        print(f"WARN: could not create backup for {path} ({exc}); overwriting in place.")
        return None


def _load_source(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    missing = [col for col in REQUIRED_COLUMNS if col not in frame.columns]
    if missing:
        raise ValueError(f"Input parquet missing required columns: {missing}")

    frame["ts_utc"] = pd.to_datetime(frame["ts_utc"], utc=True, errors="raise").dt.floor("D")
    frame = frame.loc[:, list(REQUIRED_COLUMNS)].sort_values("ts_utc").reset_index(drop=True)
    return frame


def _build_returns(frame: pd.DataFrame, horizon_days: int) -> pd.Series:
    if horizon_days < 1:
        raise ValueError(f"horizon-days must be >= 1, got {horizon_days}")
    close = pd.to_numeric(frame["close"], errors="raise")
    return (close.shift(-horizon_days) / close) - 1


def _build_target(frame: pd.DataFrame, target: str, horizon_days: int) -> pd.DataFrame:
    if target != "returns_1d":
        raise ValueError(f"Unsupported target: {target}")
    out = frame.copy()
    out[target] = _build_returns(out, horizon_days)
    out["log_returns_1d"] = np.log(out[target] + 1)
    return out


def _build_meta(
    *,
    source_path: str,
    source_sha256: str,
    out_sha256: str,
    rows: int,
    min_ts_utc: pd.Timestamp | None,
    max_ts_utc: pd.Timestamp | None,
    target: str,
    horizon_days: int,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": PROVIDER,
        "source_path": source_path,
        "source_sha256": source_sha256,
        "out_sha256": out_sha256,
        "rows": rows,
        "min_ts_utc": str(min_ts_utc) if min_ts_utc is not None else None,
        "max_ts_utc": str(max_ts_utc) if max_ts_utc is not None else None,
        "target_spec": {
            "name": target,
            "horizon_days": horizon_days,
            "direction": "forward",
            "formula": "close.shift(-horizon_days)/close - 1",
            "kind": "arithmetic",
        },
        "feature_spec": {
            "log_returns_1d": {
                "source": "close",
                "horizon_days": horizon_days,
                "direction": "forward",
                "kind": "log",
                "formula": "np.log(close.shift(-horizon_days)/close)",
            },
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _write_meta(payload: dict[str, Any], path: Path) -> None:
    _atomic_write_bytes(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def main() -> int:
    args = _parse_args()
    input_path = Path(args.in_path)
    output_path = Path(args.out)
    target = args.target
    horizon_days = args.horizon_days

    source_sha = _sha256_file(input_path)
    frame = _load_source(input_path)
    frame = _build_target(frame, target, horizon_days)
    frame = frame.iloc[:-1].reset_index(drop=True)

    if frame[target].isna().sum() != 0:
        raise SystemExit("Gating blocked: target contains NaN after dropping last row.")

    if len(frame) < args.min_rows:
        raise SystemExit(
            f"Gating blocked: rows={len(frame)} < min_rows={args.min_rows}. "
            f"Set a larger input range or lower min-rows."
        )

    max_ts = pd.to_datetime(frame["ts_utc"], utc=True).max()
    staleness_limit = datetime.now(timezone.utc).date() - timedelta(days=args.max_staleness_days)
    if pd.to_datetime(max_ts).date() < staleness_limit:
        raise SystemExit(
            f"Gating blocked: max_ts_utc={max_ts.date()} < {staleness_limit} (hoy - {args.max_staleness_days} días)."
        )

    _rotate_existing_backup(output_path)
    out_sha = _atomic_write_parquet(frame, output_path)

    meta_path = output_path.with_suffix(".meta.json")
    min_ts = pd.to_datetime(frame["ts_utc"], utc=True).min()
    meta = _build_meta(
        source_path=str(input_path),
        source_sha256=source_sha,
        out_sha256=out_sha,
        rows=len(frame),
        min_ts_utc=min_ts,
        max_ts_utc=max_ts,
        target=target,
        horizon_days=horizon_days,
    )
    _write_meta(meta, meta_path)

    print(f"OK: {len(frame)} rows -> {output_path}")
    print(f"target: {target}, horizon_days={horizon_days}")
    print(f"ts_range: {min_ts} -> {max_ts}")
    print(f"meta: {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
