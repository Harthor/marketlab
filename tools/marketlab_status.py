#!/usr/bin/env python3
import argparse, json, os, re, subprocess
from pathlib import Path
from datetime import datetime, timezone

REPOS = [
    "marketlab-core",
    "market-data-ingest",
    "altdata-web-signals",
    "correlation-engine",
    "forecasting-backtest",
    "market-research-dashboard",
]

CHECK_RE = re.compile(r"^\s*-\s*\[([ xX])\]\s+", re.M)

def sh(cmd, cwd=None):
    try:
        out = subprocess.check_output(cmd, cwd=cwd, stderr=subprocess.STDOUT, text=True)
        return out.strip(), 0
    except subprocess.CalledProcessError as e:
        return (e.output or "").strip(), e.returncode
    except FileNotFoundError:
        return "", 127

def git_info(repo: Path):
    if not (repo / ".git").exists():
        return {"present": False}
    branch, _ = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    commit, _ = sh(["git", "rev-parse", "--short", "HEAD"], cwd=repo)
    status, _ = sh(["git", "status", "--porcelain"], cwd=repo)
    return {
        "present": True,
        "branch": branch or "?",
        "commit": commit or "?",
        "dirty": bool(status.strip()),
        "dirty_files": status.splitlines()[:50],
    }

def checklist_info(path: Path):
    if not path.exists():
        return {"present": False}
    txt = path.read_text(encoding="utf-8", errors="replace")
    marks = CHECK_RE.findall(txt)
    if not marks:
        return {"present": True, "total": 0, "done": 0, "percent": None, "parse_error": True}
    total = len(marks)
    done = sum(1 for m in marks if m.lower() == "x")
    percent = int(round(100 * done / total)) if total else None
    return {"present": True, "total": total, "done": done, "percent": percent, "parse_error": False}

def detect_stack(repo: Path):
    return {
        "has_pyproject": (repo / "pyproject.toml").exists(),
        "has_requirements": (repo / "requirements.txt").exists() or (repo / "backend" / "requirements.txt").exists(),
        "has_frontend": (repo / "frontend" / "package.json").exists() or (repo / "package.json").exists(),
        "has_backend": (repo / "backend").exists(),
        "has_makefile": (repo / "Makefile").exists(),
        "has_docker_compose": (repo / "docker-compose.yml").exists(),
        "has_venv": (repo / ".venv").exists() or (repo / "backend" / ".venv").exists() or (repo / "frontend" / "node_modules").exists(),
    }

def glob_latest(repo: Path, pattern: str):
    files = list(repo.glob(pattern))
    if not files:
        return {"count": 0, "latest": None}
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = files[0]
    return {
        "count": len(files),
        "latest": str(latest),
        "latest_mtime_utc": datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc).isoformat(),
    }

def artifacts(repo_root: Path):
    return {
        "corr_manifests": glob_latest(repo_root / "correlation-engine", "reports/*/summary.json"),
        "forecast_manifests": glob_latest(repo_root / "forecasting-backtest", "runs/*/run_summary.json"),
        "datasets": glob_latest(repo_root / "altdata-web-signals", "data/datasets/*/*.parquet"),
        "signals": glob_latest(repo_root / "altdata-web-signals", "data/signals/*/*/*.parquet"),
        "processed_prices": glob_latest(repo_root / "market-data-ingest", "data/processed/*/*.parquet"),
    }

def next_step(repo_name: str, info: dict):
    ck = info.get("checklist", {})
    pct = ck.get("percent")
    if pct is None and ck.get("parse_error"):
        return "Fix CHECKLIST.md format: use '- [ ]' and '- [x]' items."
    if repo_name in ("correlation-engine", "forecasting-backtest"):
        # prefer manifest existence
        man = info.get("observability", {}).get("manifests", {})
        if man.get("count", 0) == 0:
            return "Run offline smoke/demo to generate first manifest + artifacts."
    if repo_name == "market-research-dashboard":
        return "Run frontend in demo mode; then wire real mode reading manifests via MARKETLAB_WORKSPACE."
    if repo_name == "marketlab-core":
        return "Ensure docs/contracts.md + docs/artifacts.md + manifest/dataset validators + tests."
    if pct is not None and pct < 60:
        return "Close checklist items with highest leverage (contracts + golden-path offline)."
    if pct is not None and pct >= 90:
        return "Run CI (ruff/mypy/pytest or npm build) and generate 1 real run."
    return "Review open checklist items and generate golden-path artifacts."

def to_markdown(data: dict) -> str:
    lines = []
    lines.append("# MarketLab status report (LLM-friendly)")
    lines.append("")
    lines.append(f"- generated_at_utc: {data['generated_at_utc']}")
    lines.append(f"- root: {data['root']}")
    lines.append("")
    lines.append("## Workspace artifacts snapshot")
    a = data["workspace_artifacts"]
    def fmt(x): 
        return f"count={x['count']} latest={x.get('latest')} mtime={x.get('latest_mtime_utc')}"
    lines.append(f"- datasets: {fmt(a['datasets'])}")
    lines.append(f"- signals: {fmt(a['signals'])}")
    lines.append(f"- processed_prices: {fmt(a['processed_prices'])}")
    lines.append(f"- corr_manifests: {fmt(a['corr_manifests'])}")
    lines.append(f"- forecast_manifests: {fmt(a['forecast_manifests'])}")
    lines.append("")
    for r in data["repos"]:
        lines.append(f"## {r['name']}")
        lines.append(f"- path: {r['path']}")
        g = r["git"]
        if g.get("present"):
            lines.append(f"- git: {g.get('branch')} @ {g.get('commit')} ({'dirty' if g.get('dirty') else 'clean'})")
        else:
            lines.append("- git: none (no .git directory detected)")
        ck = r["checklist"]
        if not ck.get("present"):
            lines.append("- checklist: none")
        elif ck.get("parse_error"):
            lines.append("- checklist: present but parse_error (no '- [ ]' items found)")
        else:
            lines.append(f"- checklist: {ck['done']}/{ck['total']} ({ck['percent']}%)")
        lines.append(f"- keyfiles: {', '.join(r['keyfiles']) if r['keyfiles'] else '(none)'}")
        lines.append(f"- stack: {r['stack']}")
        lines.append(f"- next_step: {r['next_step']}")
        lines.append("")
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path.cwd()))
    ap.add_argument("--out_md", default="marketlab_status_report.md")
    ap.add_argument("--out_json", default="marketlab_status.json")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    ws_art = artifacts(root)

    repos_out = []
    for name in REPOS:
        repo = root / name
        if not repo.exists():
            repos_out.append({"name": name, "path": str(repo), "missing": True})
            continue

        keyfiles = []
        for k in ["AGENTS.md", "CHECKLIST.md", "RUNBOOK.md", "README.md", "Makefile", "docker-compose.yml"]:
            p = repo / k
            if p.exists():
                keyfiles.append(k)
        # docs
        for k in ["docs/contracts.md", "docs/artifacts.md"]:
            p = repo / k
            if p.exists():
                keyfiles.append(k)

        # per-repo manifest discovery
        manifests = {"count": 0}
        if name == "correlation-engine":
            manifests = glob_latest(repo, "reports/*/summary.json")
        elif name == "forecasting-backtest":
            manifests = glob_latest(repo, "runs/*/run_summary.json")

        info = {
            "name": name,
            "path": str(repo),
            "git": git_info(repo),
            "checklist": checklist_info(repo / "CHECKLIST.md"),
            "keyfiles": keyfiles,
            "stack": detect_stack(repo),
            "observability": {"manifests": manifests},
        }
        info["next_step"] = next_step(name, info)
        repos_out.append(info)

    data = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "workspace_artifacts": ws_art,
        "repos": repos_out,
    }

    Path(args.out_json).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.out_md).write_text(to_markdown(data), encoding="utf-8")
    print(f"Wrote: {args.out_md}")
    print(f"Wrote: {args.out_json}")

if __name__ == "__main__":
    main()
