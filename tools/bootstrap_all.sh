#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOOTSTRAP="$ROOT/tools/bootstrap_venv.sh"

TARGET_REPOS=(
  "market-research-dashboard/backend"
  "altdata-web-signals"
  "correlation-engine"
  "forecasting-backtest"
  "marketlab-core"
  "market-data-ingest"
)

OK=()
FAIL=()
SKIP=()

venv_has_python311() {
  local repo_path="$1"
  local py_bin="$repo_path/.venv/bin/python"

  if [ ! -x "$py_bin" ]; then
    return 1
  fi

  if "$py_bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    return 0
  fi

  return 1
}

run_bootstrap() {
  local repo_path="$1"
  local flags=()

  if [ -f "$repo_path/requirements.txt" ]; then
    flags+=("--requirements" "requirements.txt")
  fi

  if [ -f "$repo_path/pyproject.toml" ]; then
    flags+=("--editable")
  fi

  if ! "$BOOTSTRAP" "$repo_path" "${flags[@]}"; then
    echo "ERROR: bootstrap failed for $repo_path" >&2
    return 1
  fi
}

for repo in "${TARGET_REPOS[@]}"; do
  REPO_DIR="$ROOT/$repo"

  if [ ! -d "$REPO_DIR" ]; then
    if [ "$repo" = "market-data-ingest" ]; then
      SKIP+=("$repo")
      echo "SKIP: $repo (missing, optional repo)"
      continue
    fi
    FAIL+=("$repo")
    echo "FAIL: $repo (missing directory $REPO_DIR)"
    continue
  fi

  echo "Bootstrapping: $repo"
  if [ -d "$REPO_DIR/.venv" ] && ! venv_has_python311 "$REPO_DIR"; then
    echo "WARN: existing venv for $repo is not Python >= 3.11; recreating."
    rm -rf "$REPO_DIR/.venv"
  fi
  if run_bootstrap "$REPO_DIR"; then
    if venv_has_python311 "$REPO_DIR"; then
      PY_VER="$($REPO_DIR/.venv/bin/python -V 2>&1)"
      OK+=("$repo")
      echo "OK: $repo - $PY_VER"
    else
      FAIL+=("$repo")
      echo "FAIL: $repo - missing .venv/bin/python"
    fi
  else
    FAIL+=("$repo")
  fi

done

echo ""
echo "Bootstrap summary:"
echo "-----------------"
for repo in "${OK[@]}"; do
  PY_VER="n/a"
  if [ -x "$ROOT/$repo/.venv/bin/python" ]; then
    PY_VER="$($ROOT/$repo/.venv/bin/python -V 2>&1)"
  fi
  printf '%-30s %s (%s)\n' "$repo" "OK" "$PY_VER"
done

for repo in "${FAIL[@]}"; do
  printf '%-30s %s\n' "$repo" "FAIL"
done

for repo in "${SKIP[@]}"; do
  printf '%-30s %s\n' "$repo" "SKIP"
done
