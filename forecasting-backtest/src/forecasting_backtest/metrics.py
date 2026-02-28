from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    roc_auc_score,
)


def regression_scores(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    if len(y_true) == 0:
        return {"mae": float("nan"), "rmse": float("nan"), "corr": float("nan")}

    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    corr = (
        float("nan")
        if np.std(y_true) == 0 or np.std(y_pred) == 0
        else float(np.corrcoef(y_true, y_pred)[0, 1])
    )
    return {"mae": mae, "rmse": rmse, "corr": corr}


def classification_scores(y_true: np.ndarray, y_pred: np.ndarray, *, threshold: float = 0.0) -> dict[str, Any]:
    if len(y_true) == 0:
        return {
            "accuracy": float("nan"),
            "precision": float("nan"),
            "recall": float("nan"),
            "auc": float("nan"),
        }

    y_true_label = (y_true > 0).astype(int)
    y_pred_label = (y_pred > threshold).astype(int)

    accuracy = float(accuracy_score(y_true_label, y_pred_label))
    precision = float(precision_score(y_true_label, y_pred_label, zero_division=0))
    recall = float(recall_score(y_true_label, y_pred_label, zero_division=0))

    auc = float("nan")
    if len(np.unique(y_true_label)) > 1:
        try:
            auc = float(roc_auc_score(y_true_label, y_pred))
        except Exception:
            auc = float("nan")

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "auc": auc,
    }


def information_scores(y_true: np.ndarray, y_pred: np.ndarray, *, threshold: float = 0.0) -> dict[str, float]:
    if len(y_true) == 0:
        return {"hit_rate": float("nan"), "average_return_conditional": float("nan"), "trades": 0}

    signal = np.where(y_pred > threshold, 1, np.where(y_pred < -threshold, -1, 0))
    # The backtest applies decision with a one-bar lag.
    position = np.r_[0.0, signal[:-1]]
    trade_mask = position != 0
    if not trade_mask.any():
        return {"hit_rate": float("nan"), "average_return_conditional": float("nan"), "trades": 0}

    trade_returns = y_true[trade_mask] * position[trade_mask]
    hit_rate = float(np.mean(trade_returns > 0))
    avg_return = float(np.mean(trade_returns))
    return {
        "hit_rate": hit_rate,
        "average_return_conditional": avg_return,
        "trades": int(trade_mask.sum()),
    }


def rolling_ic(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    window: int = 26,
) -> list[float | None]:
    """Rolling Pearson correlation (Information Coefficient).

    Returns a list with the same length as *y_true*.  The first
    ``window - 1`` positions are ``None``.
    """
    n = len(y_true)
    result: list[float | None] = [None] * n
    if n < window:
        return result

    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)

    for i in range(window - 1, n):
        start = i - window + 1
        t_slice = yt[start : i + 1]
        p_slice = yp[start : i + 1]
        if np.std(t_slice) == 0 or np.std(p_slice) == 0:
            result[i] = 0.0
        else:
            result[i] = float(np.corrcoef(t_slice, p_slice)[0, 1])
    return result


def regime_hit_rate(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    threshold: float = 0.0,
) -> dict[str, float | int]:
    """Directional hit rate split by bull (return > 0) vs bear (return <= 0)."""
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)

    signal = np.where(yp > threshold, 1, 0)
    correct = (signal == (yt > 0).astype(int))

    bull_mask = yt > 0
    bear_mask = ~bull_mask

    bull_n = int(bull_mask.sum())
    bear_n = int(bear_mask.sum())
    bull_hit = float(correct[bull_mask].mean()) if bull_n > 0 else float("nan")
    bear_hit = float(correct[bear_mask].mean()) if bear_n > 0 else float("nan")

    return {
        "bull_hit_rate": bull_hit,
        "bear_hit_rate": bear_hit,
        "bull_n": bull_n,
        "bear_n": bear_n,
    }
