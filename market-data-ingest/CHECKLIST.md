# market-data-ingest — Checklist
## Outcome (RUNBOOK execution)
- [ ] Status: BLOCKED

### Evidencia de ejecución
- `../tools/python_select.sh -V`: `Python 3.11+` (verificar antes de bootstrap).
- `bash ../tools/bootstrap_venv.sh .`: `.venv` existente.
- `source .venv/bin/activate && python -m pip install -U pip`: **OK** (`pip` actualizado de `21.2.4` a `26.0.1`).
- `source .venv/bin/activate && python -m pip install -e "[dev]" || python -m pip install -e .`:
  - **BLOCKED**: `Package 'market-data-ingest' requires a different Python: 3.9.6 not in '>=3.11'`.
- `source .venv/bin/activate && ruff check .`: **BLOCKED** (`ruff: command not found`).
- `source .venv/bin/activate && mypy .`: **BLOCKED** (`mypy: command not found`).
- `source .venv/bin/activate && pytest -q`: **BLOCKED** (`pytest: command not found`).
- Golden path (`scripts/make_demo_prices.py`):
  - `python scripts/make_demo_prices.py --symbols DEMO ...`: **BLOCKED** (`ModuleNotFoundError: No module named 'numpy'`).
- `quality-report` offline:
  - `python -m market_data_ingest.cli quality-report`: **BLOCKED** (`ModuleNotFoundError: No module named 'market_data_ingest'`).

## Golden path (OFFLINE)
- [x] `scripts/make_demo_prices.py` existe y acepta:
  - `--inject-gap`
  - `--inject-duplicate`
  - `--inject-null`
  - `--run-id`
  - `--publish-latest`
- [ ] Genera parquet canónico en `data/processed/...` con schema correcto → **BLOCKED en este run** por dependencia de entorno.
- [ ] Output layout alineado a contrato (`data/processed/...`) → **BLOCKED en este run** por bloqueo de entorno.

## QA / quality-report
- [ ] Detección de duplicados/gaps/nulos desde demo data → **BLOCKED en este run**.
- [ ] Test de integración `generate demo -> quality-report -> asserts` existe.
  - Archivo: `tests/test_quality_report_integration.py`
  - `tests/test_storage_atomic_write.py` valida que write atómico no deja archivo final parcial al fallar.

## Warehouse behavior
- [ ] `build-warehouse` idempotente con duckdb disponible: requiere correr en entorno con `duckdb` y deps instaladas.
- [x] fallback cuando falta duckdb está definido:
  - `src/market_data_ingest/warehouse.py` lanza `RuntimeError` explícito si no está instalado.

## Documentación
- [x] README: cómo generar demo prices (`python scripts/make_demo_prices.py`).
- [x] README: cómo apuntar altdata-web-signals (`MARKETDATA_PROCESSED_DIR`).

### Desbloqueo recomendado
- `../tools/python_select.sh` no encontró Python >=3.11 en este entorno.
- Reintentar con:
  1) instalar Python >=3.11
  2) `bash ../tools/bootstrap_venv.sh .`
  3) `source .venv/bin/activate`
  4) `python -m pip install -U pip`
  5) `python -m pip install -e ".[dev]"`
  6) `ruff check . && mypy . && pytest -q`
