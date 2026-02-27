"""Core utilities for quantitative market research."""

from .config import MarketLabSettings
from .contracts import (
    ContractValidation,
    validate_dataset_df,
    validate_prices_df,
    validate_signals_df,
)
from .io import DataCatalog, read_csv, read_parquet, write_csv, write_parquet
from .manifests import (
    ManifestArtifact,
    ManifestBase,
    validate_artifacts_exist,
    validate_manifest,
    write_json_atomic,
    write_manifest_atomic,
)
from .storage import Cache
from .timeseries import (
    align,
    compute_returns,
    normalize_timezone,
    parse_timestamps,
    resample_ohlcv,
    resample_series,
    rolling_rank,
    rolling_zscore,
)

__all__ = [
    "MarketLabSettings",
    "align",
    "compute_returns",
    "normalize_timezone",
    "parse_timestamps",
    "resample_ohlcv",
    "resample_series",
    "rolling_rank",
    "rolling_zscore",
    "Cache",
    "DataCatalog",
    "read_csv",
    "read_parquet",
    "write_csv",
    "write_parquet",
    "ManifestArtifact",
    "ManifestBase",
    "validate_manifest",
    "validate_artifacts_exist",
    "write_json_atomic",
    "write_manifest_atomic",
    "ContractValidation",
    "validate_dataset_df",
    "validate_prices_df",
    "validate_signals_df",
]

__version__ = "0.1.0"
