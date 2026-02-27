#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
STRATEGIES_DIR = REPO_ROOT / "user_data" / "strategies"
DEFAULT_OUT_DIR = REPO_ROOT / "user_data" / "tmp" / "ab_social"


@dataclass
class RunResult:
    label: str
    strategy_class: str
    run_dir: Path
    log_path: Path
    metrics: dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run A/B backtests with social signals OFF vs ON.")
    parser.add_argument("--strategy", required=True, help="Base strategy class name (e.g. Strat03RSIBBMeanReversion_v3c)")
    parser.add_argument("--timerange", required=True, help="Freqtrade timerange, e.g. 20250101-20260201")
    parser.add_argument("--config", required=True, help="Path to freqtrade config json")
    args = parser.parse_args()

    out_root = DEFAULT_OUT_DIR
    out_root.mkdir(parents=True, exist_ok=True)
    run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = out_root / run_tag
    wrappers_dir = run_root / "strategy_wrappers"
    wrappers_dir.mkdir(parents=True, exist_ok=True)

    strategy_file = _find_strategy_file(args.strategy)
    freqtrade_cmd = _resolve_freqtrade_cmd()

    baseline_class = f"{args.strategy}_AB_OFF"
    social_class = f"{args.strategy}_AB_ON"
    wrapper_path = wrappers_dir / f"{args.strategy}_ab_wrapper.py"
    _write_wrapper_strategy(
        wrapper_path=wrapper_path,
        base_strategy_file=strategy_file,
        base_strategy_class=args.strategy,
        baseline_class=baseline_class,
        social_class=social_class,
    )

    baseline = _run_backtest(
        freqtrade_cmd=freqtrade_cmd,
        run_root=run_root,
        label="baseline",
        strategy_class=baseline_class,
        strategy_path=wrappers_dir,
        config_path=Path(args.config),
        timerange=args.timerange,
    )
    social = _run_backtest(
        freqtrade_cmd=freqtrade_cmd,
        run_root=run_root,
        label="social",
        strategy_class=social_class,
        strategy_path=wrappers_dir,
        config_path=Path(args.config),
        timerange=args.timerange,
    )

    summary = {
        "run_tag": run_tag,
        "strategy_base": args.strategy,
        "config": str(Path(args.config).resolve()),
        "timerange": args.timerange,
        "baseline": _serialize_result(baseline),
        "social": _serialize_result(social),
        "delta": _compute_delta(baseline.metrics, social.metrics),
    }
    summary_path = run_root / "ab_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    _print_executive_summary(baseline, social, summary_path)
    return 0


def _find_strategy_file(strategy_class: str) -> Path:
    for path in STRATEGIES_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if f"class {strategy_class}(" in text:
            return path.resolve()
    raise FileNotFoundError(f"Strategy class not found in {STRATEGIES_DIR}: {strategy_class}")


def _resolve_freqtrade_cmd() -> list[str]:
    local_python = REPO_ROOT / ".env" / "bin" / "python3"
    if local_python.exists():
        return [str(local_python), "-m", "freqtrade"]
    return [sys.executable, "-m", "freqtrade"]


def _write_wrapper_strategy(
    wrapper_path: Path,
    base_strategy_file: Path,
    base_strategy_class: str,
    baseline_class: str,
    social_class: str,
) -> None:
    content = f"""from __future__ import annotations
import importlib.util
from pathlib import Path

_SRC = Path(r\"{str(base_strategy_file)}\")
_SPEC = importlib.util.spec_from_file_location(\"ab_base_strategy_mod\", _SRC)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f\"Unable to load strategy from {{_SRC}}\")
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
BaseStrategy = getattr(_MOD, \"{base_strategy_class}\")

class {baseline_class}(BaseStrategy):
    use_social_signals = False
    debug_social = False

class {social_class}(BaseStrategy):
    use_social_signals = True
    debug_social = False
"""
    wrapper_path.write_text(content, encoding="utf-8")


def _run_backtest(
    freqtrade_cmd: list[str],
    run_root: Path,
    label: str,
    strategy_class: str,
    strategy_path: Path,
    config_path: Path,
    timerange: str,
) -> RunResult:
    run_dir = run_root / label
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "backtest.log"
    cmd = [
        *freqtrade_cmd,
        "backtesting",
        "--config",
        str(config_path),
        "--strategy-path",
        str(strategy_path),
        "--strategy",
        strategy_class,
        "--timerange",
        timerange,
        "--backtest-directory",
        str(run_dir),
    ]

    with log_path.open("w", encoding="utf-8") as logf:
        logf.write("$ " + " ".join(cmd) + "\n")
        proc = subprocess.run(cmd, stdout=logf, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Backtest failed for {label}. See log: {log_path}")

    metrics = _extract_metrics_from_backtest_dir(run_dir, strategy_class)
    return RunResult(label=label, strategy_class=strategy_class, run_dir=run_dir, log_path=log_path, metrics=metrics)


def _extract_metrics_from_backtest_dir(run_dir: Path, strategy_class: str) -> dict[str, Any]:
    zips = sorted(run_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        return {"profit_total": None, "max_drawdown": None, "sharpe": None, "trades": None}

    latest_zip = zips[-1]
    with zipfile.ZipFile(latest_zip, "r") as zf:
        json_members = [n for n in zf.namelist() if n.endswith(".json") and "_config" not in n]
        if not json_members:
            return {"profit_total": None, "max_drawdown": None, "sharpe": None, "trades": None}
        stats = json.loads(zf.read(json_members[0]).decode("utf-8"))

    strategy_stats = stats.get("strategy", {}).get(strategy_class, {})
    return {
        "profit_total": _as_float(strategy_stats.get("profit_total")),
        "max_drawdown": _as_float(strategy_stats.get("max_drawdown_account")),
        "sharpe": _as_float(strategy_stats.get("sharpe")),
        "trades": _as_int(strategy_stats.get("total_trades")),
        "zip_file": str(latest_zip),
    }


def _as_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _as_int(v: Any) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except Exception:
        return None


def _serialize_result(result: RunResult) -> dict[str, Any]:
    return {
        "label": result.label,
        "strategy_class": result.strategy_class,
        "run_dir": str(result.run_dir),
        "log_path": str(result.log_path),
        "metrics": result.metrics,
    }


def _compute_delta(baseline: dict[str, Any], social: dict[str, Any]) -> dict[str, Any]:
    def d(key: str) -> float | None:
        b = baseline.get(key)
        s = social.get(key)
        if b is None or s is None:
            return None
        return float(s) - float(b)

    return {
        "profit_total": d("profit_total"),
        "max_drawdown": d("max_drawdown"),
        "sharpe": d("sharpe"),
        "trades": d("trades"),
    }


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:.3f}%"


def _fmt_num(v: float | int | None, ndigits: int = 4) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, int):
        return str(v)
    return f"{v:.{ndigits}f}"


def _print_executive_summary(baseline: RunResult, social: RunResult, summary_path: Path) -> None:
    bm = baseline.metrics
    sm = social.metrics
    dp = _compute_delta(bm, sm)

    print("\nResumen ejecutivo")
    print(
        f"- Baseline ({baseline.strategy_class}): "
        f"profit_total={_fmt_pct(bm.get('profit_total'))}, "
        f"max_drawdown={_fmt_pct(bm.get('max_drawdown'))}, "
        f"sharpe={_fmt_num(bm.get('sharpe'))}, trades={_fmt_num(bm.get('trades'))}"
    )
    print(
        f"- Social ({social.strategy_class}): "
        f"profit_total={_fmt_pct(sm.get('profit_total'))}, "
        f"max_drawdown={_fmt_pct(sm.get('max_drawdown'))}, "
        f"sharpe={_fmt_num(sm.get('sharpe'))}, trades={_fmt_num(sm.get('trades'))}"
    )
    print(
        f"- Delta (social - baseline): "
        f"profit_total={_fmt_pct(dp.get('profit_total'))}, "
        f"max_drawdown={_fmt_pct(dp.get('max_drawdown'))}, "
        f"sharpe={_fmt_num(dp.get('sharpe'))}, trades={_fmt_num(dp.get('trades'))}"
    )
    print(f"- Summary JSON: {summary_path}")
    print(f"- Baseline log: {baseline.log_path}")
    print(f"- Social log: {social.log_path}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
