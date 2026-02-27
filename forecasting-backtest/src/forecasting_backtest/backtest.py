from __future__ import annotations

import numpy as np
import pandas as pd


def run_simple_backtest(
    timestamps: np.ndarray | pd.Index,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    threshold: float = 0.0,
    transaction_cost: float = 0.0004,
    slippage: float = 0.0002,
    initial_capital: float = 1.0,
    annualize_sharpe_days: int = 252,
) -> dict[str, object]:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must share length")
    if len(y_true) == 0:
        return {
            "equity_curve": [initial_capital],
            "equity_drawdown": [0.0],
            "signals": [],
            "positions": [],
            "pnl": [],
            "stats": {"n_rows": 0},
        }

    returns = np.asarray(y_true, dtype=float)
    preds = np.asarray(y_pred, dtype=float)

    signal = np.where(preds > threshold, 1, np.where(preds < -threshold, -1, 0))
    position = np.r_[0.0, signal[:-1]]
    traded = np.abs(np.diff(np.r_[0.0, position]))
    gross = position * returns
    costs = traded * (transaction_cost + slippage)
    net = gross - costs

    equity = [initial_capital]
    current = float(initial_capital)
    for value in net:
        if np.isnan(value):
            value = 0.0
        current *= float(1.0 + value)
        equity.append(current)

    equity_arr = np.asarray(equity, dtype=float)
    trade_mask = position != 0

    if len(net) <= 1 or np.isnan(net).all():
        sharpe = float("nan")
    else:
        sigma = np.nanstd(net)
        sharpe = float(np.nanmean(net) / sigma * np.sqrt(annualize_sharpe_days)) if sigma and sigma > 0 else float("nan")

    total_return = float(equity_arr[-1] / initial_capital - 1.0)
    if len(equity_arr) > 1:
        horizon_days = (pd.to_datetime(timestamps[-1]) - pd.to_datetime(timestamps[0])).days
        years = max(horizon_days / 365.25, 1e-9)
        cagr = float((equity_arr[-1] / initial_capital) ** (1.0 / years) - 1.0)
    else:
        cagr = 0.0

    cumulative_max = np.maximum.accumulate(equity_arr)
    max_drawdown = float(np.nanmin(equity_arr / cumulative_max - 1.0))

    signal_ret = returns * position
    hit_mask = signal != 0
    hit_rate = float(np.mean(signal_ret[hit_mask] > 0)) if hit_mask.any() else float("nan")
    avg_conditional = float(np.mean(signal_ret[hit_mask])) if hit_mask.any() else float("nan")

    return {
        "equity_curve": equity_arr.tolist(),
        "equity_drawdown": (equity_arr / cumulative_max - 1.0).tolist(),
        "signals": signal.tolist(),
        "positions": position.tolist(),
        "pnl": net.tolist(),
        "stats": {
            "n_rows": int(len(y_true)),
            "trades": int(trade_mask.sum()),
            "hit_rate": hit_rate,
            "avg_conditional_return": avg_conditional,
            "total_return": total_return,
            "cagr": cagr,
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "gross_return_sum": float(np.nansum(gross)),
            "cost_sum": float(np.nansum(costs)),
        },
    }
