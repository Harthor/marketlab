from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


def plot_equity_curve(timestamps: Any, equity: Any, out_path: str | Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(timestamps, equity, color="#1f77b4")
    ax.set_title("Equity Curve")
    ax.set_xlabel("timestamp")
    ax.set_ylabel("equity")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def plot_pred_vs_true(y_true: Sequence[float], y_pred: Sequence[float], out_path: str | Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(y_true, y_pred, s=12, alpha=0.5)
    ax.set_xlabel("true return")
    ax.set_ylabel("predicted return")
    ax.set_title("Pred vs True")
    lim = np.nanmax(np.abs(np.r_[np.asarray(y_true), np.asarray(y_pred)]))
    if np.isfinite(lim) and lim > 0:
        pad = float(lim) * 0.05
        ax.set_xlim(-lim - pad, lim + pad)
        ax.set_ylim(-lim - pad, lim + pad)
        ax.plot([-lim, lim], [-lim, lim], "k--", alpha=0.4)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def plot_feature_importance(
    features: Sequence[str],
    scores: Sequence[float],
    out_path: str | Path,
    top_n: int = 20,
) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pairs = sorted(zip(features, scores), key=lambda x: abs(x[1]), reverse=True)[:top_n]
    if not pairs:
        return

    labels, values = zip(*pairs)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(range(len(labels)), values)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_title("Feature Importance")
    ax.set_xlabel("importance")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
