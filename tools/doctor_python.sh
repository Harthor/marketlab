#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SELECT_BIN="$ROOT/tools/python_select.sh"
SELECTED="$($SELECT_BIN)"

printf 'SELECTED_PYTHON=%s\n' "$SELECTED"
"$SELECTED" -V

BAD=0

check_venv() {
  local name="$1"
  local venv_path="$2"

  local py="$venv_path/bin/python"
  if [ ! -x "$py" ]; then
    return 0
  fi

  local ok
  ok="$($py -c 'import sys; print(1 if sys.version_info >= (3, 11) else 0)')"
  if [ "$ok" != "1" ]; then
    echo "WARN: $name venv has python <$name (not >=3.11): $($py -V | tr -d '\r\n')"
    BAD=1
  fi
}

check_venv "marketlab-core" "$ROOT/marketlab-core/.venv"
check_venv "market-data-ingest" "$ROOT/market-data-ingest/.venv"
check_venv "altdata-web-signals" "$ROOT/altdata-web-signals/.venv"
check_venv "correlation-engine" "$ROOT/correlation-engine/.venv"
check_venv "forecasting-backtest" "$ROOT/forecasting-backtest/.venv"
check_venv "market-research-dashboard/backend" "$ROOT/market-research-dashboard/backend/.venv"

if [ "$BAD" -eq 1 ]; then
  echo "Action: recreate flagged venv(s) with tools/bootstrap_venv.sh <repo_dir>"
  exit 1
fi

if [ -x "$ROOT/market-research-dashboard/backend/.venv/bin/python" ]; then
  "${ROOT}/market-research-dashboard/backend/.venv/bin/python" -V
fi

exit 0
