"""Visualiza rápido el dataset research-ready."""

from __future__ import annotations

from pathlib import Path
import argparse

import polars as pl

def plot_dataset(dataset_path: str, output_dir: str = "reports") -> str:
    import matplotlib.pyplot as plt
    import pandas as pd

    frame = pl.read_parquet(dataset_path)
    if "returns_1d" not in frame.columns:
        raise ValueError("Dataset sin returns_1d")

    signal_cols = [c for c in frame.columns if c.startswith("signal_")]
    if not signal_cols:
        raise ValueError("No se encontraron señales en el dataset")

    df = frame.to_pandas()
    df["ts_utc"] = pd.to_datetime(df["ts_utc"])

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) precios + retorno
    plt.figure(figsize=(12, 4))
    ax1 = plt.gca()
    ax1.plot(df["ts_utc"], df["close"], color="#1f77b4", label="close")
    ax1.set_title("Precio y retorno diario")
    ax1.set_xlabel("ts_utc")
    ax1.set_ylabel("close")

    ax2 = ax1.twinx()
    ax2.plot(df["ts_utc"], df["returns_1d"], color="#ff7f0e", alpha=0.6, label="returns_1d")
    ax2.set_ylabel("returns_1d")
    plt.tight_layout()
    price_out = out_dir / "prices_and_returns.png"
    plt.savefig(price_out, dpi=150)
    plt.close()

    # 2) señales + retorno + señales
    for col in signal_cols:
        plt.figure(figsize=(12, 4))
        y = df[col].fillna(0)

        plt.plot(df["ts_utc"], df["returns_1d"], alpha=0.4, label="returns_1d")
        plt.plot(df["ts_utc"], y, label=col)
        plt.title(f"{col} vs returns_1d")
        plt.xlabel("ts_utc")
        plt.legend()
        plt.tight_layout()
        plt.savefig(out_dir / f"corr_{col}.png", dpi=150)
        plt.close()

    # 3) correlación por señal (global por dataset)
    corr_rows = []
    for col in signal_cols:
        corr_rows.append((col, float(df[["returns_1d", col]].corr().iloc[0, 1])))
    corr_df = pl.DataFrame({"signal": [c for c, _ in corr_rows], "corr_with_returns_1d": [v for _, v in corr_rows]})
    corr_csv = out_dir / "signal_correlations_global.csv"
    corr_df.write_csv(corr_csv)

    # return summary path
    return str(price_out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Graficar dataset de investigación")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out-dir", default="reports")
    args = parser.parse_args()
    path = plot_dataset(args.dataset, output_dir=args.out_dir)
    print(f"saved={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
