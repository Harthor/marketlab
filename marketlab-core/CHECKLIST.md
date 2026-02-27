# marketlab-core — Checklist (Release Captain)

## Contract & docs
- [x] `docs/contracts.md` exists.
- [x] `docs/contracts.md` includes canonical `ts_utc` naming (with migration fallback to `timestamp`) for required rows in prices/signals/research dataset schema.
- [x] `docs/contracts.md` includes explicit schema for:
  - `signals`: `signal_*` contract
  - `research_dataset`: `returns_1d` + `close` requirement
- [x] `docs/contracts.md` output conventions include requested structure for signals/datasets/reports/runs.
- [x] `docs/artifacts.md` defines required keys for `summary.json` and `run_summary.json`.
- [x] `docs/artifacts.md` defines stable artifact naming for tables/plots and paths.

## Validators
- [x] `marketlab_core/contracts.py` exists and implements:
  - [x] `validate_prices_df`
  - [x] `validate_signals_df`
  - [x] `validate_dataset_df`
- [x] Unit tests for validators exist in `tests/test_contracts.py`.

## Time-series hardening
- [x] `tests/test_timeseries.py` incluye regresiones de `align(freq=...)`:
  - [x] mixed tz + duplicates
  - [x] gaps + inner/outer
  - [x] ffill behavior explícito
- [x] `docs/artifacts.md` clarifica `returns_1d_simple` / `returns_1d_log`.
- [x] `docs/contracts.md` y `docs/artifacts.md` clarifican sign convention de `lag` en cross-corr.

## CLI/Examples
- [ ] `examples/quickstart.py` runs without error.
- [ ] `CLI` smoke-test command runs without environment/runtime errors.

## Gates
- [ ] `ruff check .`
- [ ] `mypy .`
- [ ] `pytest -q`

## Outcome
- [ ] Status: BLOCKED (si no hay Python 3.11 local).
- [x] Bloque principal identificado: Python debe ser 3.11+ (`requires-python >= 3.11`).
