#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT/market-research-dashboard/backend"
VENV_DIR="$BACKEND_DIR/.venv"

cd "$BACKEND_DIR"

"$ROOT/tools/bootstrap_venv.sh" "$BACKEND_DIR" --requirements requirements.txt

source "$VENV_DIR/bin/activate"

export MARKETLAB_WORKSPACE="$HOME/Desktop/market-sentiment-lab"

python manage.py runserver 8000
