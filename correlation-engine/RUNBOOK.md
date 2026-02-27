# correlation-engine — Runbook

Requires Python >= 3.11
bash ../tools/bootstrap_venv.sh . --editable
source .venv/bin/activate
ruff check .
mypy .
pytest -q

# Offline smoke (expected)
python scripts/run_smoke.py
