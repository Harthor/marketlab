# marketlab-core — AGENTS.md

## Non-negotiables
- Do not edit files outside this repository.
- Prefer small, reviewable diffs. If the task is large, write a plan first.
- Every behavior change must include tests.
- Keep APIs deterministic and documented. Avoid hidden magic.

## Setup (macOS/Linux)
- Python: 3.11+
- Create venv:
  - bash ../tools/bootstrap_venv.sh . --editable
- Install:
  - `bootstrap_venv.sh` installs pip and project deps automatically (editable mode)

## Quality gates (must pass before "done")
- ruff check .
- mypy .
- pytest -q

## Definition of Done
- docs/contracts.md exists and is up-to-date.
- docs/artifacts.md exists and is up-to-date.
- validators exist + tests exist.
- align(freq=...) regression tests exist.
