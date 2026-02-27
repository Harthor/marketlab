#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATASET="$ROOT/altdata-web-signals/data/datasets/BTC-USD/1d.parquet"

echo "ROOT=$ROOT"
echo "DATASET=$DATASET"

if [ ! -f "$DATASET" ]; then
  echo "ERROR: dataset not found: $DATASET"
  exit 1
fi

echo ""
echo "Step 1: generate correlation manifest (first run)"
cd "$ROOT/correlation-engine"

"$ROOT/tools/bootstrap_venv.sh" "$ROOT/correlation-engine" --editable >/tmp/bootstrap_correlation.log 2>&1
source .venv/bin/activate

set +e
python run_smoke.py "$DATASET"
RC=$?
set -e

if [ "$RC" -ne 0 ]; then
  echo "run_smoke.py failed (rc=$RC). Trying without args..."
  python run_smoke.py
fi

deactivate

echo ""
echo "Step 2: show manifests snapshot"
echo "Correlation manifests:"
ls -1 "$ROOT/correlation-engine/reports"/*/summary.json 2>/dev/null | tail -n 5 || true
echo "Forecast manifests:"
ls -1 "$ROOT/forecasting-backtest/runs"/*/run_summary.json 2>/dev/null | tail -n 5 || true

echo ""
echo "Step 3: next commands (dashboard real mode)"
echo "Backend:"
echo "cd $ROOT/market-research-dashboard/backend"
echo "export MARKETLAB_WORKSPACE=\"$ROOT\""
echo "$ROOT/tools/bootstrap_venv.sh \"$ROOT/market-research-dashboard/backend\" --requirements requirements.txt"
echo "cd $ROOT/market-research-dashboard/backend"
echo "source .venv/bin/activate"
echo "python manage.py runserver 8000"
echo ""
echo "Frontend (no demo):"
echo "cd $ROOT/market-research-dashboard/frontend"
echo "rm -f .env.local"
echo "npm install"
echo "npm run dev"
