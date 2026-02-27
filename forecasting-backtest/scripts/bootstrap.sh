#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="${ROOT_DIR}/../marketlab-core"
VENV_DIR="${ROOT_DIR}/.venv"

if [ -x "${ROOT_DIR}/../tools/python_select.sh" ]; then
  PY_BIN="$("${ROOT_DIR}/../tools/python_select.sh")"
else
  echo "[error] Python >=3.11 is required. Could not find a compatible interpreter."
  echo "Tips:"
  echo "  - install with brew: brew install python@3.11"
  echo "  - or via pyenv: pyenv install 3.11 && pyenv local 3.11"
  echo "  - or in an existing environment: conda create -n fb3.11 python=3.11"
  exit 1
fi

echo "[info] using ${PY_BIN}"
"${PY_BIN}" - <<'PY'
import sys
print(sys.version)
PY

if ! "${PY_BIN}" -m venv "${VENV_DIR}" ; then
  echo "[error] cannot create virtualenv at ${VENV_DIR}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip

if [ -d "${CORE_DIR}" ]; then
  python -m pip install -e "${CORE_DIR}" --no-build-isolation
else
  echo "[warn] marketlab-core not found at ${CORE_DIR}, skipping"
fi

python -m pip install -e "${ROOT_DIR}[dev]" --no-build-isolation

cat <<MSG

Bootstrap complete.

Run:
  source ${VENV_DIR}/bin/activate
  forecast --help
MSG
