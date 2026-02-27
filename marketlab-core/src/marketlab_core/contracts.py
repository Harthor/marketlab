"""Contract validators for reusable dataset exchange between repos."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import polars as pl


TIMESTAMP_COL = "ts_utc"
TARGET_RETURNS_1D = "returns_1d"
FEATURE_LOG_RETURNS_1D = "log_returns_1d"

STATUS_COMPLETE = "complete"
STATUS_SKIPPED = "skipped"
STATUS_PARTIAL = "partial"
STATUS_STALE = "stale"


def sha256_file(path: str | Path) -> str:
    """Compute SHA-256 checksum for a file."""
    hasher = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_sha256_file(path: str | Path) -> str:
    """Backward-compatible alias retained for earlier callers."""
    return sha256_file(path)


def now_utc_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class MissingArtifact(TypedDict):
    path: str
    reason: str


@dataclass(frozen=True)
class ManifestContract:
    warnings: list[str]
    errors: list[str]
    missing_artifacts: list[MissingArtifact]

    @classmethod
    def create(
        cls,
        *,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        missing_artifacts: list[MissingArtifact] | None = None,
    ) -> "ManifestContract":
        return cls(
            warnings=list(warnings or []),
            errors=list(errors or []),
            missing_artifacts=list(missing_artifacts or []),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "missing_artifacts": [dict(item) for item in self.missing_artifacts],
        }


def _as_report_ok(
    table: str,
    rows: int,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> "ContractValidation":
    return ContractValidation(
        table=table,
        rows=rows,
        errors=list(errors or []),
        warnings=list(warnings or []),
        ok=not bool(errors),
    )


@dataclass(frozen=True)
class ContractValidation:
    table: str
    ok: bool
    rows: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _require_columns(
    df: pl.DataFrame,
    required: list[str],
) -> list[str]:
    return [col for col in required if col not in df.columns]


def _timestamp_report(df: pl.DataFrame) -> tuple[list[str], list[str], str | None]:
    errors: list[str] = []
    warnings: list[str] = []

    ts_column = TIMESTAMP_COL if TIMESTAMP_COL in df.columns else "timestamp" if "timestamp" in df.columns else None
    if ts_column is None:
        errors.append(f"missing column: {TIMESTAMP_COL} (or timestamp)")
        return errors, warnings, None

    if ts_column == "timestamp":
        warnings.append(f"use {TIMESTAMP_COL} for canonical timestamp column")

    ts_dtype = df[ts_column].dtype
    if not str(ts_dtype).startswith("Datetime"):
        errors.append("timestamp must be datetime type")
        return errors, warnings, ts_column

    if not str(ts_dtype).endswith("+00:00"):
        warnings.append("timestamp is not UTC; normalize to UTC")

    if df[ts_column].is_null().sum() > 0:
        warnings.append("timestamp contains nulls")

    return errors, warnings, ts_column


def _require_numeric(df: pl.DataFrame, cols: list[str], table: str, *, min_non_negative: bool = False) -> list[str]:
    errors: list[str] = []
    for col in cols:
        if col not in df.columns:
            continue
        if not df[col].dtype.is_numeric():
            errors.append(f"{table}.{col} must be numeric")
            continue
        if min_non_negative and df[col].min() is not None and df[col].min() < 0:
            errors.append(f"{table}.{col} must be non-negative")
    return errors


def _choose_first(df: pl.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def validate_prices_df(df: pl.DataFrame) -> ContractValidation:
    """Validate OHLCV-style prices contract.

    Contract rules are intentionally not over-strict:
    - required: ts_utc, symbol, open, high, low, close, volume
    - legacy aliases accepted: timestamp
    """

    table = "prices"
    errors: list[str] = []
    warnings: list[str] = []

    required = ["symbol", "open", "high", "low", "close", "volume"]
    missing_required = _require_columns(df, required)
    if missing_required:
        errors.extend([f"prices missing column: {col}" for col in missing_required])

    timestamp_errors, timestamp_warnings, _ = _timestamp_report(df)
    errors.extend(timestamp_errors)
    warnings.extend(timestamp_warnings)

    numeric_errors = _require_numeric(df, ["open", "high", "low", "close", "volume"], table, min_non_negative=True)
    errors.extend(numeric_errors)

    if "high" in df.columns and "low" in df.columns:
        try:
            if (df["high"] < df["low"]).sum() > 0:
                warnings.append("high < low detected in some rows")
        except Exception:
            warnings.append("could not validate high/low consistency")

    if "close" in df.columns:
        try:
            if (df["close"] <= 0).sum() > 0:
                warnings.append("close <= 0 detected in some rows")
        except Exception:
            warnings.append("could not validate close positivity")

    return _as_report_ok(table, rows=df.height, errors=errors, warnings=warnings)


def validate_signals_df(df: pl.DataFrame) -> ContractValidation:
    """Validate signal contract used across research/pipeline repos.

    Required:
    - ts_utc
    - symbol
    - one signal id column: signal or signal_name
    - one numeric value column: signal_value or score or value
    """

    table = "signals"
    errors: list[str] = []
    warnings: list[str] = []

    if "symbol" not in df.columns:
        errors.append("signals missing required column: symbol")

    timestamp_errors, timestamp_warnings, _ = _timestamp_report(df)
    errors.extend(timestamp_errors)
    warnings.extend(timestamp_warnings)

    signal_col = _choose_first(df, ["signal", "signal_name"])
    value_col = _choose_first(df, ["signal_value", "value", "score", "prediction"])

    if signal_col is None:
        errors.append("signals missing column: signal or signal_name")
    if value_col is None:
        errors.append("signals missing numeric column: signal_value/value/score/prediction")
    else:
        errors.extend(_require_numeric(df, [value_col], table))

    return _as_report_ok(table, rows=df.height, errors=errors, warnings=warnings)


def validate_dataset_df(df: pl.DataFrame) -> ContractValidation:
    """Validate research dataset contract.

    Required:
    - timestamp
    - symbol
    - at least one target column: target, y, or label
    """

    table = "research_dataset"
    errors: list[str] = []
    warnings: list[str] = []

    if "symbol" not in df.columns:
        errors.append("research_dataset missing required column: symbol")

    missing = _require_columns(df, ["timestamp"])
    if missing:
        errors.extend([f"research_dataset missing column: {col}" for col in missing])

    timestamp_errors, timestamp_warnings, _ = _timestamp_report(df)
    errors.extend(timestamp_errors)
    warnings.extend(timestamp_warnings)

    target_col = _choose_first(df, ["target", "y", "label"])
    if target_col is None:
        errors.append("research_dataset missing target column: target or y or label")
    else:
        errors.extend(_require_numeric(df, [target_col], table))

    feature_candidates = [
        col
        for col in df.columns
        if col.startswith("feature_")
    ]
    if not feature_candidates:
        warnings.append("research_dataset has no columns prefixed with feature_")

    if "split" in df.columns:
        if not str(df["split"].dtype).startswith("Utf8"):
            errors.append("split must be string (e.g. train/val/test)")

    if "dataset_id" not in df.columns:
        warnings.append("research_dataset missing optional column: dataset_id")

    return _as_report_ok(table, rows=df.height, errors=errors, warnings=warnings)
