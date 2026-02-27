from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl


def plot_rolling_correlations(plot_path: Path, rolling: pl.DataFrame, top_features: list[str], config_windows: tuple[int, ...]) -> None:
    if rolling.is_empty() or not top_features:
        return
    filtered = rolling.filter(pl.col("feature").is_in(top_features))
    if filtered.is_empty():
        return
    pdf = filtered.to_pandas()
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 5))
    for feature in top_features:
        feature_df = pdf[pdf["feature"] == feature]
        for window in sorted(config_windows):
            window_df = feature_df[feature_df["window"] == window]
            if window_df.empty:
                continue
            ax.plot(window_df["timestamp"], window_df["correlation"], label=f"{feature} | w={window}")
    ax.axhline(0, color="black", linewidth=1, alpha=0.25)
    ax.set_title("Rolling correlations por ventana")
    ax.set_xlabel("timestamp")
    ax.set_ylabel("correlación")
    ax.legend(loc="best", fontsize="x-small")
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)


def plot_lag_profiles(plot_path: Path, lag_table: pl.DataFrame, top_features: list[str]) -> None:
    if lag_table.is_empty() or not top_features:
        return
    pdf = lag_table.to_pandas()
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 6))
    for feature in top_features:
        sub = pdf[pdf["feature"] == feature].sort_values("lag")
        if sub.empty:
            continue
        ax.plot(sub["lag"], sub["correlation"], marker="o", label=feature)
    ax.axvline(0, color="black", linewidth=1, alpha=0.35)
    ax.axhline(0, color="black", linewidth=1, alpha=0.35)
    ax.set_title("Perfil lead-lag (correlación por lag)")
    ax.set_xlabel("lag")
    ax.set_ylabel("correlación")
    ax.legend(loc="best", fontsize="x-small")
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
