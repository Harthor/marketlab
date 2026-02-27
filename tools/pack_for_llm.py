#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT  = ROOT / "llm_pack"
ZIP  = ROOT / "llm_pack.zip"

MAX_RECENT_OK = int(os.environ.get("PACK_MAX_RECENT_OK", "3"))
NONFINITE_RE = re.compile(r"NaN|Infinity|-Infinity")
EMPTY_PATH_RE = re.compile(r'"path"\s*:\s*""')

def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

def newest(paths: list[Path], n: int) -> list[Path]:
    paths = [p for p in paths if p.exists()]
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[:n]

def zip_dir(src_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in src_dir.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(ROOT))

def _manifest_name(prefix: str, path: Path, base: Path) -> str:
    rel = path.relative_to(base)
    safe = "__".join(rel.as_posix().split("/"))
    return f"{prefix}__{safe}"

def _contains_match(path: Path, pattern: re.Pattern[str]) -> bool:
    try:
        return pattern.search(path.read_text("utf-8", errors="ignore")) is not None
    except Exception:
        return False

def main() -> int:
    # reset
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifests").mkdir(exist_ok=True)
    (OUT / "code").mkdir(exist_ok=True)
    (OUT / "next_prompts").mkdir(exist_ok=True)

    # always include status files
    for f in ["marketlab_status.json", "marketlab_status_plus.json", "marketlab_status_report.md", "OPEN_ISSUES.md"]:
        fp = ROOT / f
        if fp.exists():
            copy_file(fp, OUT / fp.name)

    # include next_prompts
    np = ROOT / "next_prompts"
    if np.is_dir():
        for p in np.glob("*.md"):
            copy_file(p, OUT / "next_prompts" / p.name)

    # load status_plus to decide what to copy
    sp_path = ROOT / "marketlab_status_plus.json"
    if not sp_path.exists():
        raise SystemExit("marketlab_status_plus.json not found. Run ./tools/marketlab_cycle.sh first.")

    sp = json.loads(sp_path.read_text("utf-8"))
    bad_corr = [Path(x["path"]) for x in sp.get("corr_manifests_checked", []) if not x.get("ok", True)]
    bad_fc   = [Path(x["path"]) for x in sp.get("forecast_manifests_checked", []) if not x.get("ok", True)]

    # copy bad manifests explicitly
    for p in bad_corr:
        if p.exists():
            copy_file(p, OUT / "manifests" / f"BAD__corr__{p.parent.name}__summary.json")
    for p in bad_fc:
        if p.exists():
            copy_file(p, OUT / "manifests" / f"BAD__fc__{p.parent.name}__run_summary.json")

    # also include a few recent OK manifests for reference
    ok_corr = [Path(x["path"]) for x in sp.get("corr_manifests_checked", []) if x.get("ok", False)]
    ok_fc   = [Path(x["path"]) for x in sp.get("forecast_manifests_checked", []) if x.get("ok", False)]

    for p in newest(ok_corr, MAX_RECENT_OK):
        if p.exists():
            copy_file(p, OUT / "manifests" / f"OK__corr__{p.parent.name}__summary.json")
    for p in newest(ok_fc, MAX_RECENT_OK):
        if p.exists():
            copy_file(p, OUT / "manifests" / f"OK__fc__{p.parent.name}__run_summary.json")

    # best-effort scans not limited by status_plus entries
    corr_reports = ROOT / "correlation-engine" / "reports"
    if corr_reports.is_dir():
        for p in corr_reports.rglob("summary.json"):
            if _contains_match(p, NONFINITE_RE):
                copy_file(p, OUT / "manifests" / _manifest_name("FOUND_NONFINITE", p, corr_reports))

    fc_runs = ROOT / "forecasting-backtest" / "runs"
    if fc_runs.is_dir():
        for p in fc_runs.rglob("run_summary.json"):
            if _contains_match(p, EMPTY_PATH_RE):
                copy_file(p, OUT / "manifests" / _manifest_name("FOUND_EMPTY_PATH", p, fc_runs))

    

    # --- scan best-effort for known bad patterns (even if status_plus didn't include them) ---
    import re as _re
    _NONFINITE = _re.compile(r"\bNaN\b|\bInfinity\b|\b-Infinity\b")
    _EMPTY_PATH = _re.compile(r"\"path\"\s*:\s*\"\"")

    corr_reports = ROOT / "correlation-engine" / "reports"
    if corr_reports.is_dir():
        for f in corr_reports.rglob("summary.json"):
            try:
                s = f.read_text("utf-8", errors="ignore")
            except Exception:
                continue
            if _NONFINITE.search(s):
                rid = f.parent.name
                copy_file(f, OUT / "manifests" / f"FOUND_NONFINITE__corr__{rid}__summary.json")

    fc_runs = ROOT / "forecasting-backtest" / "runs"
    if fc_runs.is_dir():
        for f in fc_runs.rglob("run_summary.json"):
            try:
                s = f.read_text("utf-8", errors="ignore")
            except Exception:
                continue
            if _EMPTY_PATH.search(s):
                rid = f.parent.name
                copy_file(f, OUT / "manifests" / f"FOUND_EMPTY_PATH__fc__{rid}__run_summary.json")

# dashboard backend code (explicit allowlist)
    allow = [
        ROOT / "market-research-dashboard" / "backend" / "api" / "views.py",
        ROOT / "market-research-dashboard" / "backend" / "api" / "utils.py",
        ROOT / "market-research-dashboard" / "backend" / "api" / "services.py",
        ROOT / "market-research-dashboard" / "backend" / "api" / "serializers.py",
        ROOT / "market-research-dashboard" / "backend" / "api" / "urls.py",
        ROOT / "market-research-dashboard" / "backend" / "marketlab_backend" / "settings.py",
        ROOT / "market-research-dashboard" / "backend" / "marketlab_backend" / "urls.py",
    
        ROOT / "correlation-engine" / "src" / "correngine" / "runner.py",
        ROOT / "forecasting-backtest" / "src" / "forecasting_backtest" / "pipeline.py",]
    for p in allow:
        if p.exists():
            rel = p.relative_to(ROOT)
            copy_file(p, OUT / "code" / rel)

    # writer code (explicit “likely” paths; copy if exist)
    writer_globs = [
        ROOT / "correlation-engine",
        ROOT / "forecasting-backtest",
    ]
    for base in writer_globs:
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            # exclude venv/node_modules/user_data/data
            s = str(p)
            if "/.venv/" in s or "\\.venv\\" in s:
                continue
            if "/node_modules/" in s:
                continue
            if "/user_data/" in s:
                continue
            if "/data/" in s:
                continue
            # keep files that mention manifest writing keywords
            try:
                txt = p.read_text("utf-8", errors="ignore")
            except Exception:
                continue
            if ("summary.json" in txt or "run_summary.json" in txt or "allow_nan" in txt or "n_effective" in txt):
                rel = p.relative_to(ROOT)
                copy_file(p, OUT / "code" / rel)

    # zip it
    zip_dir(OUT, ZIP)

    if not ZIP.exists() or ZIP.stat().st_size < 5000:
        raise SystemExit("llm_pack.zip not created or too small (sanity check).")

    print(f"Wrote pack: {ZIP}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
