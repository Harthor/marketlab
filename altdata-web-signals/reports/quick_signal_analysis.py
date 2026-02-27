"""Análisis rápido de señales contra retornos.

Genera:
- correlación rolling (30 y 90 días) entre returns_1d y cada signal_*.
- cross-correlation con lags de -7 a +7 días.
"""

from __future__ import annotations

from pathlib import Path
import argparse

import pandas as pd


def run_analysis(dataset_path: str, output_dir: str = "reports") -> None:
    frame = pd.read_parquet(dataset_path)
    if "returns_1d" not in frame.columns:
        raise ValueError("El dataset no tiene returns_1d")

    signal_cols = [c for c in frame.columns if c.startswith("signal_")]
    if not signal_cols:
        raise ValueError("No se encontraron columnas de señal en el dataset")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    base = frame.set_index("ts_utc")

    # simplificación robusta: correlación por signal y ventana
    rolling_out = []
    for col in signal_cols:
        for window in (30, 90):
            corr = base["returns_1d"].rolling(window).corr(base[col]).reset_index()
            df = corr.rename(columns={0: "rolling_corr", "index": "ts_utc"})
            df["signal"] = col
            df["window"] = window
            rolling_out.append(df)
    rolling_df = pd.concat(rolling_out, ignore_index=True)
    rolling_df = rolling_df.dropna()

    cc_rows = []
    for col in signal_cols:
        for lag in range(-7, 8):
            ser = base[col].shift(lag)
            corr = base["returns_1d"].corr(ser)
            cc_rows.append({"signal": col, "lag": lag, "corr": float(corr) if pd.notna(corr) else None})
    cross_df = pd.DataFrame(cc_rows)

    rolling_path = out_dir / "rolling_signal_correlations.csv"
    cross_path = out_dir / "cross_correlation_lags.csv"
    rolling_df.to_csv(rolling_path, index=False)
    cross_df.to_csv(cross_path, index=False)
    print(f"rolling_corr={rolling_path}")
    print(f"cross_corr={cross_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Análisis rápido de señales contra retornos")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out-dir", default="reports")
    args = parser.parse_args()

    run_analysis(args.dataset, output_dir=args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
