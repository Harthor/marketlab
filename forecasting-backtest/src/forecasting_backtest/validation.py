from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TimeSplit:
    fold: int
    train_idx: np.ndarray
    test_idx: np.ndarray
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def iter_time_splits(
    df: pd.DataFrame,
    *,
    ts_col: str = "ts",
    train_window_days: int = 730,
    test_window_days: int = 92,
    step_days: int = 92,
    min_train_rows: int = 260,
    min_test_rows: int = 30,
) -> Iterator[TimeSplit]:
    if df.empty:
        return

    if not df[ts_col].is_monotonic_increasing:
        df = df.sort_values(ts_col).reset_index(drop=True)

    times = pd.to_datetime(df[ts_col], utc=True)
    if times.isna().any():
        raise ValueError("timestamp column cannot be parsed")
    times = times.dt.tz_localize(None)

    if train_window_days <= 0 or test_window_days <= 0 or step_days <= 0:
        raise ValueError("window values must be positive")

    n = len(times)
    start_pos = 0
    fold = 0

    while start_pos < n:
        train_start = times.iloc[start_pos]
        train_end_cut = train_start + pd.Timedelta(days=train_window_days)
        train_end_pos = int(np.searchsorted(times.to_numpy(), train_end_cut.to_numpy(), side="right"))

        test_start_pos = train_end_pos + 1
        if test_start_pos >= n:
            break

        test_end_cut = times.iloc[test_start_pos] + pd.Timedelta(days=max(test_window_days - 1, 1))
        test_end_pos = int(np.searchsorted(times.to_numpy(), test_end_cut.to_numpy(), side="right"))

        if test_end_pos <= test_start_pos:
            break

        if train_end_pos - start_pos < min_train_rows or test_end_pos - test_start_pos < min_test_rows:
            start_candidate = start_pos + 1
            if start_candidate >= n:
                break
            start_pos = start_candidate
            continue

        split = TimeSplit(
            fold=fold,
            train_idx=np.arange(start_pos, train_end_pos, dtype=int),
            test_idx=np.arange(test_start_pos, test_end_pos, dtype=int),
            train_start=train_start.to_pydatetime(),
            train_end=(
                times.iloc[min(train_end_pos - 1, n - 1)].to_pydatetime()
                if train_end_pos <= n
                else times.iloc[-1].to_pydatetime()
            ),
            test_start=times.iloc[test_start_pos].to_pydatetime(),
            test_end=(
                times.iloc[min(test_end_pos - 1, n - 1)].to_pydatetime()
                if test_end_pos <= n
                else times.iloc[-1].to_pydatetime()
            ),
        )
        yield split

        fold += 1
        next_start = train_start + pd.Timedelta(days=step_days)
        next_pos = int(np.searchsorted(times.to_numpy(), next_start.to_numpy(), side="left"))
        if next_pos <= start_pos:
            next_pos = start_pos + 1
        if next_pos >= n:
            break
        start_pos = next_pos


def iter_expanding_splits(
    df: pd.DataFrame,
    *,
    ts_col: str = "ts",
    min_train_rows: int = 26,
    test_rows: int = 1,
    step_rows: int = 1,
) -> Iterator[TimeSplit]:
    """Expanding-window walk-forward splits (observation-index based).

    Train always starts at index 0 and grows each fold.
    Test is the next ``test_rows`` observations after the train window.
    """
    if df.empty:
        return

    if not df[ts_col].is_monotonic_increasing:
        df = df.sort_values(ts_col).reset_index(drop=True)

    times = pd.to_datetime(df[ts_col], utc=True)
    if times.isna().any():
        raise ValueError("timestamp column cannot be parsed")
    times = times.dt.tz_localize(None)

    n = len(times)
    fold = 0
    train_end_pos = min_train_rows  # exclusive upper bound of train

    while train_end_pos + test_rows <= n:
        test_start_pos = train_end_pos
        test_end_pos = min(test_start_pos + test_rows, n)

        if test_end_pos <= test_start_pos:
            break

        split = TimeSplit(
            fold=fold,
            train_idx=np.arange(0, train_end_pos, dtype=int),
            test_idx=np.arange(test_start_pos, test_end_pos, dtype=int),
            train_start=times.iloc[0].to_pydatetime(),
            train_end=times.iloc[train_end_pos - 1].to_pydatetime(),
            test_start=times.iloc[test_start_pos].to_pydatetime(),
            test_end=times.iloc[test_end_pos - 1].to_pydatetime(),
        )
        yield split

        fold += 1
        train_end_pos += step_rows
