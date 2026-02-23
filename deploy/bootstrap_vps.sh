#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[bootstrap_vps] error: python3.11/python3 not found" >&2
  exit 1
fi

if [ ! -d .env ]; then
  echo "[bootstrap_vps] creating virtualenv with $PYTHON_BIN"
  "$PYTHON_BIN" -m venv .env
else
  echo "[bootstrap_vps] using existing .env"
fi

.env/bin/python -m pip install --upgrade pip setuptools wheel

if [ -f lab/requirements.txt ]; then
  echo "[bootstrap_vps] installing lab/requirements.txt"
  .env/bin/python -m pip install -r lab/requirements.txt
fi

if [ -f requirements.txt ]; then
  echo "[bootstrap_vps] installing requirements.txt"
  .env/bin/python -m pip install -r requirements.txt
fi

if [ -f user_data/requirements.txt ]; then
  echo "[bootstrap_vps] installing user_data/requirements.txt"
  .env/bin/python -m pip install -r user_data/requirements.txt
fi

echo "[bootstrap_vps] ensuring freqtrade CLI"
.env/bin/python -m pip install --upgrade freqtrade

.env/bin/freqtrade --version

mkdir -p user_data/logs user_data/reports

echo "[bootstrap_vps] done"
echo "project_dir=$PROJECT_DIR"
echo "logs_dir=$PROJECT_DIR/user_data/logs"
echo "reports_dir=$PROJECT_DIR/user_data/reports"
