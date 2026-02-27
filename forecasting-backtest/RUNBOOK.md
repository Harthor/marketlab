# forecasting-backtest — Runbook

bash ../tools/bootstrap_venv.sh . --editable
source .venv/bin/activate
python -m pip install -e ".[dev]" || python -m pip install -e .
ruff check .
mypy .
pytest -q

# Offline demo (expected)
python run_demo.py
