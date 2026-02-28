"""Event study: measure returns after trigger events."""
from __future__ import annotations

import polars as pl


def run_event_study(
    features: pl.DataFrame,
    targets: pl.DataFrame,
    trigger_col: str,
    trigger_threshold: float,
    trigger_op: str = "gt",
    target_cols: list[str] | None = None,
) -> dict[str, float | int]:
    """Measure average/median returns after a trigger event fires.

    Args:
        features: DataFrame with ts_utc, asset_uid, and trigger column.
        targets: DataFrame with ts_utc, asset_uid, and target columns.
        trigger_col: Column name for the trigger signal.
        trigger_threshold: Threshold value.
        trigger_op: "gt" (greater than) or "lt" (less than).
        target_cols: Target columns. Default: returns_1h, returns_4h.

    Returns:
        Dict with event_count, mean/median returns for each target.
    """
    if target_cols is None:
        target_cols = ["returns_1h", "returns_4h"]

    merged = features.join(targets, on=["ts_utc", "asset_uid"], how="inner")

    if trigger_col not in merged.columns:
        return {"event_count": 0, "error": f"column {trigger_col} not found"}

    # Find trigger events
    if trigger_op == "gt":
        events = merged.filter(pl.col(trigger_col) > trigger_threshold)
    elif trigger_op == "lt":
        events = merged.filter(pl.col(trigger_col) < trigger_threshold)
    else:
        return {"event_count": 0, "error": f"unknown operator {trigger_op}"}

    # Control: non-event rows
    if trigger_op == "gt":
        control = merged.filter(pl.col(trigger_col) <= trigger_threshold)
    else:
        control = merged.filter(pl.col(trigger_col) >= trigger_threshold)

    result: dict[str, float | int] = {"event_count": len(events), "control_count": len(control)}

    for tgt in target_cols:
        if tgt not in events.columns:
            continue
        evt_vals = events[tgt].drop_nulls()
        ctl_vals = control[tgt].drop_nulls()

        if len(evt_vals) > 0:
            result[f"{tgt}_mean"] = round(evt_vals.mean(), 6)
            result[f"{tgt}_median"] = round(evt_vals.median(), 6)
        if len(ctl_vals) > 0:
            result[f"{tgt}_control_mean"] = round(ctl_vals.mean(), 6)
            result[f"{tgt}_control_median"] = round(ctl_vals.median(), 6)
        if len(evt_vals) > 0 and len(ctl_vals) > 0:
            result[f"{tgt}_uplift_pp"] = round(
                (evt_vals.mean() - ctl_vals.mean()) * 100, 4
            )

    return result
