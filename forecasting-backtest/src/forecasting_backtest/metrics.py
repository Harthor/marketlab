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
    if np.std(y_true) == 0 or np.std(y_pred) == 0:
        corr = float("nan")
    else:
        corr = float(np.corrcoef(y_true, y_pred)[0, 1])
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
