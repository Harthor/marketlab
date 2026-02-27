#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---fast}"

ROOT="$(pwd)"
REPORT="$ROOT/marketlab_status_report.md"

REPOS=(
  "marketlab-core"
  "market-data-ingest"
  "altdata-web-signals"
  "correlation-engine"
  "forecasting-backtest"
  "market-research-dashboard"
)

checkbox_stats() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo "checklist: none"
    return
  fi
  local done total
  done=$(grep -E "^\s*-\s*\[[xX]\]" "$f" | wc -l | tr -d ' ')
  total=$(grep -E "^\s*-\s*\[[ xX]\]" "$f" | wc -l | tr -d ' ')
  if [[ "$total" == "0" ]]; then
    echo "checklist: 0/0"
  else
    echo "checklist: ${done}/${total} ($(python3 - <<PY
d=$done
t=$total
print(int(round(100*d/t)))
PY
)%)"
  fi
}

git_info() {
  local dir="$1"
  if [[ ! -d "$dir/.git" ]]; then
    echo "git: none"
    return
  fi
  local branch commit dirty
  branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")
  commit=$(git -C "$dir" rev-parse --short HEAD 2>/dev/null || echo "?")
  if [[ -n "$(git -C "$dir" status --porcelain 2>/dev/null)" ]]; then dirty="dirty"; else dirty="clean"; fi
  echo "git: ${branch} @ ${commit} (${dirty})"
}

run_ci_hint() {
  local dir="$1"
  if [[ -f "$dir/Makefile" ]] && grep -qE "^\s*ci:" "$dir/Makefile"; then
    echo "ci_cmd: make ci"
  elif [[ -f "$dir/pyproject.toml" ]]; then
    echo "ci_cmd: ruff check . && mypy . && pytest -q"
  elif [[ -f "$dir/frontend/package.json" ]] || [[ -f "$dir/package.json" ]]; then
    echo "ci_cmd: npm run build (frontend)"
  else
    echo "ci_cmd: (unknown)"
  fi
}

echo "# MarketLab status report" > "$REPORT"
echo "" >> "$REPORT"
echo "- generated_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$REPORT"
echo "- root: $ROOT" >> "$REPORT"
echo "- mode: $MODE" >> "$REPORT"
echo "" >> "$REPORT"

for r in "${REPOS[@]}"; do
  dir="$ROOT/$r"
  echo "## $r" >> "$REPORT"
  if [[ ! -d "$dir" ]]; then
    echo "- status: MISSING (dir not found)" >> "$REPORT"
    echo "" >> "$REPORT"
    continue
  fi

  echo "- path: $dir" >> "$REPORT"
  echo "- $(git_info "$dir")" >> "$REPORT"
  echo "- $(checkbox_stats "$dir/CHECKLIST.md")" >> "$REPORT"

  keyfiles=()
  [[ -f "$dir/AGENTS.md" ]] && keyfiles+=("AGENTS.md")
  [[ -f "$dir/CHECKLIST.md" ]] && keyfiles+=("CHECKLIST.md")
  [[ -f "$dir/RUNBOOK.md" ]] && keyfiles+=("RUNBOOK.md")
  [[ -f "$dir/docs/contracts.md" ]] && keyfiles+=("docs/contracts.md")
  [[ -f "$dir/docs/artifacts.md" ]] && keyfiles+=("docs/artifacts.md")
  if [[ "${#keyfiles[@]}" -gt 0 ]]; then
    echo "- keyfiles: ${keyfiles[*]}" >> "$REPORT"
  else
    echo "- keyfiles: (none detected)" >> "$REPORT"
  fi

  echo "- $(run_ci_hint "$dir")" >> "$REPORT"

  if [[ "$MODE" == "--ci" ]]; then
    echo "" >> "$REPORT"
    echo "### CI run output (best-effort)" >> "$REPORT"
    echo '```' >> "$REPORT"
    (
      cd "$dir"
      if [[ -f Makefile ]] && grep -qE "^\s*ci:" Makefile; then
        make ci
      elif [[ -f pyproject.toml ]]; then
        ruff check . || true
        mypy . || true
        pytest -q || true
      elif [[ -f frontend/package.json ]]; then
        cd frontend
        if [[ -f package-lock.json ]]; then npm ci; else npm install; fi
        npm run build || true
      elif [[ -f package.json ]]; then
        if [[ -f package-lock.json ]]; then npm ci; else npm install; fi
        npm run build || true
      else
        echo "No CI recipe found."
      fi
    ) 2>&1 | tail -n 120
    echo '```' >> "$REPORT"
  fi

  echo "" >> "$REPORT"
done

echo "Wrote: $REPORT"
