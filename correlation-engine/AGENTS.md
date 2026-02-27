# correlation-engine — AGENTS.md

## Non-negotiables
- Do not edit outside this repo.
- Reports must be consumable by dashboard via summary.json manifest alone.
- Lag sign convention must be documented and enforced by tests.

## Setup
Requires Python >= 3.11
- bash ../tools/bootstrap_venv.sh . --requirements requirements.txt --editable

## Gates
ruff check .
mypy .
pytest -q

## Definition of Done
- reports/<run_id>/summary.json includes artifacts list and required keys
- smoke run produces a complete report offline
