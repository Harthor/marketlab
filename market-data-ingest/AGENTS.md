# market-data-ingest — AGENTS.md

## Non-negotiables
- Do not edit files outside this repository.
- Keep unit tests offline (no network).
- Outputs must follow marketlab-core contracts (schema + layout).
- Idempotency: re-running must not duplicate rows.

## Setup
Requires Python >= 3.11
- bash ../tools/bootstrap_venv.sh . --editable

## Gates
ruff check .
mypy .
pytest -q

## Definition of Done
- scripts/make_demo_prices.py exists and produces canonical parquet
- quality-report works on demo data
- tests include a light integration test (demo -> quality-report)
