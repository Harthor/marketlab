#!/usr/bin/env python3
import json, glob, math
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.cwd()

def mtime(p: Path):
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()

def latest(pattern: str, n=3):
    files = [Path(p) for p in glob.glob(str(ROOT / pattern))]
    files = [p for p in files if p.exists()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:n]

def resolve_artifact_path(manifest_path: Path, artifact_path: str) -> Path:
    ap = Path(artifact_path)
    if ap.is_absolute():
        return ap
    return (manifest_path.parent / ap).resolve()

def has_nonfinite(x) -> bool:
    return isinstance(x, float) and (not math.isfinite(x))

def walk_nonfinite(x, p=""):
    found = []
    if has_nonfinite(x):
        found.append(p or "<root>")
    elif isinstance(x, dict):
        for k, v in x.items():
            found.extend(walk_nonfinite(v, f"{p}.{k}" if p else str(k)))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            found.extend(walk_nonfinite(v, f"{p}[{i}]"))
    return found

def check_manifest(path: Path):
    out = {
        "path": str(path),
        "mtime_utc": mtime(path),
        "ok": True,
        "errors": [],
        "duplicate_artifact_ids": [],
        "duplicate_type_path_pairs": [],
        "kind": None,
        "status": None,
        "schema_version": None,
        "run_id": None,
        "artifacts_count": 0,
        "missing_artifacts_count": 0,
        "missing_artifacts": [],
        "nonfinite_values": [],
    }
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        out["ok"] = False
        out["errors"].append(f"json_parse_error: {e}")
        return out

    out["kind"] = d.get("kind")
    out["status"] = d.get("status")
    out["schema_version"] = d.get("schema_version")
    out["run_id"] = d.get("run_id")

    for k in ["kind", "status", "schema_version", "run_id", "artifacts"]:
        if k not in d:
            out["ok"] = False
            out["errors"].append(f"missing_field:{k}")

    arts = d.get("artifacts") or []
    out["artifacts_count"] = len(arts)

    missing = []
    artifact_ids = set()
    paths = set()

    for a in arts:
        if not isinstance(a, dict):
            missing.append({"artifact": a, "reason": "invalid_entry"})
            continue

        artifact_id = a.get("artifact_id")
        if isinstance(artifact_id, str) and artifact_id.strip():
            if artifact_id in artifact_ids:
                out["duplicate_artifact_ids"].append(artifact_id)
            else:
                artifact_ids.add(artifact_id)

        artifact_type = a.get("type")
        ap = a.get("path")
        if artifact_type and ap:
            path_key = (str(artifact_type), str(ap))
            if path_key in paths:
                out["duplicate_type_path_pairs"].append({"type": str(artifact_type), "path": str(ap)})
            else:
                paths.add(path_key)

        ap = a.get("path")
        if not ap:
            missing.append({"artifact": a, "reason": "no_path"})
            continue
        rp = resolve_artifact_path(path, ap)
        if not rp.exists():
            missing.append({"path": ap, "resolved": str(rp)})
    out["missing_artifacts_count"] = len(missing)
    out["missing_artifacts"] = missing[:25]
    if missing:
        out["ok"] = False
        out["errors"].append("missing_artifacts")

    if out["duplicate_artifact_ids"]:
        out["ok"] = False
        out["errors"].append("duplicate_artifact_ids")

    if out["duplicate_type_path_pairs"]:
        out["ok"] = False
        out["errors"].append("duplicate_type_path_pairs")

    nf = walk_nonfinite(d)
    out["nonfinite_values"] = nf[:50]
    if nf:
        out["ok"] = False
        out["errors"].append("nonfinite_values_in_manifest")

    return out

def main():
    corr = latest("correlation-engine/reports/*/summary.json", n=5)
    fc = latest("forecasting-backtest/runs/*/run_summary.json", n=5)

    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "corr_manifests_checked": [check_manifest(p) for p in corr],
        "forecast_manifests_checked": [check_manifest(p) for p in fc],
    }

    out_json = ROOT / "marketlab_status_plus.json"
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote: {out_json}")

if __name__ == "__main__":
    main()
