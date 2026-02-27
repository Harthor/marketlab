#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== Collect bundle =="
echo "ROOT=$ROOT"

# 1) Estado MarketLab
(cd "$ROOT" && ./tools/marketlab_cycle.sh)

# 2) Correlation-engine: checklist + tests (si existen)
if [ -d "$ROOT/correlation-engine" ]; then
  echo
  echo "== correlation-engine =="
  if [ -f "$ROOT/correlation-engine/CHECKLIST.md" ]; then
    echo "-- CHECKLIST (first 80 lines)"
    sed -n '1,80p' "$ROOT/correlation-engine/CHECKLIST.md" || true
  fi
  if [ -f "$ROOT/correlation-engine/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$ROOT/correlation-engine/.venv/bin/activate"
    (cd "$ROOT/correlation-engine" && pytest -q) || true
    deactivate || true
  fi
fi

# 3) market-data-ingest: checklist/tests (si existen)
if [ -d "$ROOT/market-data-ingest" ]; then
  echo
  echo "== market-data-ingest =="
  if [ -f "$ROOT/market-data-ingest/CHECKLIST.md" ]; then
    sed -n '1,80p' "$ROOT/market-data-ingest/CHECKLIST.md" || true
  fi
fi

# 4) Pack
(cd "$ROOT" && ./tools/pack_for_llm.sh)

echo
ls -la "$ROOT/llm_pack.zip" || true
echo "DONE."
