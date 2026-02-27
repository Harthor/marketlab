#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <repo_dir> [--requirements requirements.txt] [--editable]" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SELECTOR="$ROOT/tools/python_select.sh"
PY_BIN="$($SELECTOR)"

REPO_DIR="$1"
shift
REQ_PATH=""
EDITABLE=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --requirements)
      if [ "$#" -lt 2 ]; then
        echo "--requirements expects a file path" >&2
        exit 1
      fi
      REQ_PATH="$2"
      shift 2
      ;;
    --editable)
      EDITABLE=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 <repo_dir> [--requirements requirements.txt] [--editable]" >&2
      exit 1
      ;;
  esac
done

REPO_DIR="$(cd "$REPO_DIR" && pwd)"
VENV_DIR="$REPO_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  "$PY_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

python -m pip install -U pip

if [ -z "$REQ_PATH" ]; then
  if [ -f "$REPO_DIR/requirements.txt" ]; then
    REQ_PATH="$REPO_DIR/requirements.txt"
  fi
else
  if [ -f "$REQ_PATH" ]; then
    REQ_PATH="$(cd "$(dirname "$REQ_PATH")" && pwd)/$(basename "$REQ_PATH")"
  elif [ -f "$REPO_DIR/$REQ_PATH" ]; then
    REQ_PATH="$REPO_DIR/$REQ_PATH"
  else
    echo "requirements file not found: $REQ_PATH" >&2
    exit 1
  fi
fi

if [ -n "$REQ_PATH" ] && [ -f "$REQ_PATH" ]; then
  python -m pip install -r "$REQ_PATH"
fi

if [ "$EDITABLE" -eq 1 ]; then
  if [ -f "$REPO_DIR/pyproject.toml" ] || [ -f "$REPO_DIR/setup.py" ] || [ -f "$REPO_DIR/setup.cfg" ]; then
    python -m pip install -e "$REPO_DIR" || true
  fi
fi

python -V
which python
pip -V
