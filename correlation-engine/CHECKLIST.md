# correlation-engine — Checklist

Status: BLOCKED

## Output contract (RUN-time validation)
- [x] `reports/<run_id>/summary.json` se produce via writer dedicado (`write_corr_manifest_atomic`)
- [x] manifest includes campos mínimos de contrato (`run_id`, `created_at_utc`, `kind`, `status`, `dataset_path`, `dataset_hash`, `config`, `config_hash`, `seed`, `artifacts`)
- [x] `top_features` queda dentro de manifest por corrida y `table/plot` listados en `artifacts`
- [ ] tablas/plots estables aparecen siempre en `tables` y `plots` del manifest (parcialmente dependiente de outputs)

Evidence:
- Bloqueado por `setup`: no fue posible instalar dependencias ni importar el paquete con este runtime.
- `../tools/python_select.sh -V`: `Python 3.11+`.

## Lag semantics
- [ ] README documents lag sign meaning (positive/negative/zero)
- [ ] synthetic test validates lag sign convention (lead 3d and lag3 cases)

Evidence:
- No se pudo correr `pytest -q` porque el entorno está bloqueado por versión de Python y sin deps instaladas.

## Offline smoke
- [ ] `scripts/run_smoke.py` generates synthetic research-ready dataset (`signal_*`)
- [ ] run produces a full report in `reports/`

Evidence:
- `python run_smoke.py`: `can't open file .../run_smoke.py`
- `python scripts/run_smoke.py`: `ModuleNotFoundError: No module named 'numpy'`.

## Gates
- [ ] ruff check .
- [ ] mypy .
- [ ] pytest -q

Evidence:
- `ruff check .`: `command not found: ruff`
- `mypy .`: `command not found: mypy`
- `pytest -q`: `command not found: pytest`

## Environment
- [ ] Python >= 3.11
- [ ] venv + deps instalables en este runtime

- Evidence:
- `../tools/python_select.sh -V`: `Python 3.11+`
- `bash ../tools/bootstrap_venv.sh . --requirements requirements.txt --editable`: OK
- `python -m pip install -U pip`: OK
- `python -m pip install -e ".[dev]"` y fallback `python -m pip install -e .`: `ERROR: Package 'correlation-engine' requires a different Python: 3.9.6 not in '>=3.11'`

## Contract stability gates
- [x] `test_manifest_is_json_strict_and_has_required_fields`: valida contrato base y `json.dumps(..., allow_nan=False)`
- [x] `test_manifest_sanitizes_nonfinite_to_null`: valida serialización estricta con `NaN/Inf -> null`
- [x] `write_corr_manifest_atomic` usa `sanitize_for_json` y `allow_nan=False`
- [ ] `pytest -q` / `ruff` / `mypy` en runtime activo
