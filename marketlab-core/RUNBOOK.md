# marketlab-core — Runbook

## Standard run
bash ../tools/bootstrap_venv.sh . --editable
source .venv/bin/activate
ruff check .
mypy .
pytest -q
