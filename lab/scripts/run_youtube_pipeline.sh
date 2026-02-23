#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"

cd "$REPO"

# Si no está OPENAI_API_KEY, la levantamos desde el .env de OpenClaw (no se imprime)
if [[ -z "${OPENAI_API_KEY:-}" && -f "$HOME/apps/openclaw/.env" ]]; then
  export OPENAI_API_KEY="$(sed -n 's/^OPENAI_API_KEY=//p' "$HOME/apps/openclaw/.env" | head -n1)"
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: OPENAI_API_KEY not set (and not found in ~/apps/openclaw/.env)" >&2
  exit 1
fi

python3 -m venv "$ROOT/.venv" >/dev/null 2>&1 || true
source "$ROOT/.venv/bin/activate"
pip -q install -U pip
pip -q install -r "$ROOT/requirements.txt"

PYTHONPATH="$ROOT/src" python -m msl.pipeline.run_youtube \
  --channels "$ROOT/configs/channels.yaml" \
  --config "$ROOT/configs/pipeline.yaml"
