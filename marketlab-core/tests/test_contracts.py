from datetime import UTC, datetime

import polars as pl

from marketlab_core.contracts import (
    validate_dataset_df,
    validate_prices_df,
    validate_signals_df,
)


def test_validate_prices_df_ok() -> None:
    frame = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
            ],
            "symbol": ["BTC", "BTC"],
            "open": [100.0, 100.5],
            "high": [101.0, 101.5],
            "low": [99.5, 100.1],
            "close": [100.2, 100.9],
            "volume": [10.0, 12.0],
        }
    )
    report = validate_prices_df(frame)
    assert report.ok
    assert report.errors == []
    assert report.rows == 2


def test_validate_prices_df_with_missing_required_columns() -> None:
    frame = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1, 0, 0, tzinfo=UTC)],
            "symbol": ["BTC"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.5],
        }
    )
    report = validate_prices_df(frame)
    assert not report.ok
    assert any("prices missing column: volume" in item for item in report.errors)


def test_validate_signals_df_supports_aliases() -> None:
    frame = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
            ],
            "symbol": ["BTC", "BTC"],
            "signal_name": ["m", "m"],
            "score": [0.1, -0.3],
            "note": ["ok", "ok"],
        }
    )
    report = validate_signals_df(frame)
    assert report.ok
    assert report.errors == []


def test_validate_signals_df_errors_when_signal_value_missing() -> None:
    frame = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1, 0, 0, tzinfo=UTC)],
            "symbol": ["BTC"],
            "signal": ["momentum"],
        }
    )
    report = validate_signals_df(frame)
    assert not report.ok
    assert any("signals missing numeric column" in item for item in report.errors)


def test_validate_dataset_df_allows_optional_schema_and_requires_target() -> None:
    valid = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
            ],
            "symbol": ["BTC", "BTC"],
            "y": [0.01, -0.02],
            "feature_momentum": [1.1, 1.3],
            "feature_vol": [0.2, 0.4],
        }
    )
    report = validate_dataset_df(valid)
    assert report.ok
    assert report.rows == 2


def test_validate_dataset_df_requires_dataset_target() -> None:
    invalid = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1, 0, 0, tzinfo=UTC)],
            "symbol": ["BTC"],
            "feature_momentum": [1.1],
        }
    )
    report = validate_dataset_df(invalid)
    assert not report.ok
    assert any("research_dataset missing target column" in item for item in report.errors)
