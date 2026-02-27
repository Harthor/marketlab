from datetime import UTC, datetime, timedelta, timezone

import polars as pl

from marketlab_core.timeseries import align, compute_returns, resample_series


def test_align_outer_ffill_keeps_union_shape() -> None:
    a = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 3, tzinfo=UTC),
            ],
            "value": [1.0, 2.0, 3.0],
        }
    )
    b = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 0, 2, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 4, tzinfo=UTC),
            ],
            "value": [10.0, 20.0],
        }
    )
    out = align([a, b], how="outer", freq="1m", method="ffill")
    assert out.height == 5
    assert out["timestamp"][0] == datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    assert out["timestamp"][-1] == datetime(2024, 1, 1, 0, 4, tzinfo=UTC)


def test_resample_mean() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 2, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 3, tzinfo=UTC),
            ],
            "value": [1, 2, 3, 4],
        }
    )
    out = resample_series(df, freq="2m", agg="mean")
    assert out.height == 2
    assert out["value"][0] == 1.5
    assert out["value"][1] == 3.5


def test_compute_returns_simple_and_log() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 2, tzinfo=UTC),
            ],
            "value": [100.0, 110.0, 121.0],
        }
    )
    simple = compute_returns(df, value_col="value", method="simple", horizon=1)
    log = compute_returns(df, value_col="value", method="log", horizon=1)
    assert abs(simple["value_simple_ret_1"][1] - 0.10) < 1e-9
    assert abs(log["value_log_ret_1"][1] - 0.0953102) < 1e-4


def test_align_outer_ffill_with_mixed_tz_duplicates_and_gaps() -> None:
    local_plus_one = timezone(timedelta(hours=1))

    a = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                datetime(2024, 1, 1, 9, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 9, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 9, 4, tzinfo=UTC),
            ],
            "value_a": [1.0, 2.0, 2.0, 4.0],
        }
    )
    b = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 10, 1, tzinfo=local_plus_one),
                datetime(2024, 1, 1, 10, 2, tzinfo=local_plus_one),
                datetime(2024, 1, 1, 10, 2, tzinfo=local_plus_one),
                datetime(2024, 1, 1, 10, 4, tzinfo=local_plus_one),
            ],
            "value_b": [100.0, 101.0, 101.5, 102.0],
        }
    )

    out = align([a, b], how="outer", freq="1m", method="ffill")

    assert out.height == 5
    assert out["timestamp"].is_sorted()
    assert out["timestamp"].is_duplicated().sum() == 0
    assert out["timestamp"][0] == datetime(2024, 1, 1, 9, 0, tzinfo=UTC)
    assert out["timestamp"][-1] == datetime(2024, 1, 1, 9, 4, tzinfo=UTC)
    assert out["value_a"][0] == 1.0
    assert out["value_b"][0] is None
    assert out["value_a"][2] == 2.0
    assert out["value_b"][2] == 101.5
    assert out["value_b"][3] == 101.5  # ffill from 9:02 (no b data at 9:03)
    assert out["value_a"][4] == 4.0
    assert out["value_b"][4] == 102.0


def test_align_inner_vs_outer_with_ffill() -> None:
    a = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
                datetime(2024, 1, 1, 9, 2, tzinfo=UTC),
                datetime(2024, 1, 1, 9, 3, tzinfo=UTC),
            ],
            "value_a": [1.0, 2.0, 3.0],
        }
    )
    b = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 9, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 9, 3, tzinfo=UTC),
                datetime(2024, 1, 1, 9, 4, tzinfo=UTC),
            ],
            "value_b": [10.0, 30.0, 40.0],
        }
    )

    outer = align([a, b], how="outer", freq="1m", method="ffill")
    inner = align([a, b], how="inner", freq="1m", method="ffill")

    assert outer.height == 5
    assert inner.height == 1
    assert inner["timestamp"].to_list() == [datetime(2024, 1, 1, 9, 3, tzinfo=UTC)]
    assert inner["value_a"][0] == 3.0
    assert inner["value_b"][0] == 30.0
