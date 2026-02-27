# forecasting-backtest — AGENTS.md

## Non-negotiables
- Do not edit outside this repo.
- Run artifacts must be consumable by dashboard via run_summary.json manifest.
- Ensure no leakage: train/test must not overlap, and backtest uses out-of-sample predictions.

## Setup
Requires Python >= 3.11
- bash ../tools/bootstrap_venv.sh . --editable

## Gates
ruff check .
mypy .
pytest -q

## Definition of Done
- runs/<run_id>/run_summary.json includes artifacts and required keys
- tables/predictions.parquet + tables/equity.parquet exist with stable schema
- offline demo produces a full run
