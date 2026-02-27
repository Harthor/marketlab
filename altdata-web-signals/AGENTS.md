# altdata-web-signals — AGENTS.md

## Non-negotiables
- Do not edit files outside this repo.
- Provide an offline golden path (no network required).
- Dataset builder output must be stable and consumable by corr-engine and forecasting-backtest.
- Signals naming: signal_<source>_<topic_slug>

## Setup
Requires Python >= 3.11
- bash ../tools/bootstrap_venv.sh . --editable

## Gates
ruff check .
mypy .
pytest -q

## Definition of Done
- signals build-dataset produces stable parquet + meta.json
- demo runs offline end-to-end and produces plots/reports
