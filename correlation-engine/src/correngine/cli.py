from __future__ import annotations

import argparse
import json
import numpy as np
import warnings
from pathlib import Path

try:
    from marketlab_core.contracts import TIMESTAMP_COL
except Exception:
    TIMESTAMP_COL = "ts_utc"
    warnings.warn("marketlab-core.contracts unavailable; using fallback timestamp default ts_utc")

from .config import RunConfig, parse_windows
from .runner import find_latest_run, run_correlation


def _build_run_config(args: argparse.Namespace) -> RunConfig:
    return RunConfig(
        dataset=args.dataset,
        target=args.target,
        timestamp=args.timestamp,
        max_lag=int(args.max_lag),
        windows=parse_windows(args.windows),
        seed=int(args.seed),
        bootstrap=int(args.bootstrap),
        top=int(args.top),
        distance_corr=bool(args.distance_corr),
        output_root=args.out,
        cache_root=args.cache_root,
    )


def _print_summary(result):
    print(f"run_id={result.run_id}")
    print(f"report_dir={result.run_dir}")
    print(f"features={result.correlation_table.height}")
    print("summary_saved=summary.json")


def _load_summary(reports_dir: Path, run_id: str | None) -> tuple[str, dict]:
    if run_id is not None:
        run_dir = reports_dir / run_id
    else:
        _latest = find_latest_run(reports_dir)
        if _latest is None:
            raise FileNotFoundError(f"No hay runs en {reports_dir}")
        run_dir = _latest
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"No existe summary en {run_dir}")
    return str(run_dir), json.loads(summary_path.read_text(encoding="utf-8"))


def cmd_rank(args: argparse.Namespace) -> int:
    run_path, summary = _load_summary(Path(args.reports), args.run_id)
    top = int(args.top)
    metric = args.metric
    top_features = summary.get("top_features", {}).get(metric)
    if top_features is None:
        raise KeyError(
            f"Metric '{metric}' no existe. Métricas disponibles: {', '.join(sorted(summary.get('top_features', {}).keys()))}"
        )
    print(f"run={Path(run_path).name}")
    for i, row in enumerate(top_features[:top], 1):
        value_key = next((k for k in row.keys() if k != "feature"), None)
        value = row.get(value_key)
        if isinstance(value, (int, float, np.floating, np.integer)) and value is not None:
            print(f"{i:>3} | {row.get('feature'):<40} | {value: .6f}")
        else:
            print(f"{i:>3} | {row.get('feature'):<40} | {value}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = _build_run_config(args)
    result = run_correlation(cfg)
    _print_summary(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="corr", description="Engine de correlación para señales x target")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run de correlación con persistencia de reporte")
    run.add_argument("--dataset", required=True, help="Ruta de CSV o Parquet")
    run.add_argument("--target", default="returns_1d", help="Columna target (returns_1d o close)")
    run.add_argument("--timestamp", default=TIMESTAMP_COL, help=f"Columna timestamp (default: {TIMESTAMP_COL})")
    run.add_argument("--max-lag", type=int, default=30, help="Máximo lag absoluto")
    run.add_argument("--windows", default="30,90,180", help="Windows para rolling corr")
    run.add_argument("--seed", type=int, default=42, help="Semilla para MI/bootstrap")
    run.add_argument("--bootstrap", type=int, default=0, help="Bootstraps para IC de Pearson")
    run.add_argument("--top", type=int, default=50, help="Top en ranking del summary")
    run.add_argument("--distance-corr", action="store_true", help="Incluir distance correlation")
    run.add_argument("--out", default="reports", help="Directorio de reportes")
    run.add_argument("--cache-root", default="~/.cache/correlation-engine", help="Root de cache marketlab-core")
    run.set_defaults(func=cmd_run)

    rank = sub.add_parser("rank", help="Mostrar top features por métrica desde un run")
    rank.add_argument("--metric", required=True, help="Métrica en summary.json (ej: spearman_abs)")
    rank.add_argument("--top", type=int, default=50, help="Top N features")
    rank.add_argument("--reports", default="reports", help="Directorio de reportes")
    rank.add_argument("--run-id", default=None, help="run_id objetivo")
    rank.set_defaults(func=cmd_rank)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
