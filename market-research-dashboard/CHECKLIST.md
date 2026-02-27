# market-research-dashboard — Checklist

## Frontend
- [x] install deps with lockfile strategy
- [x] build succeeds
- [x] demo mode (VITE_DEMO_MODE=1) shows runs and artifacts
- [x] front pages render status badge/failed errors/warnings from health contract in UI flow

## Backend
- [x] /api/runs lists runs by reading manifests only
  - `correlation-engine/reports/*/summary.json`
  - `forecasting-backtest/runs/*/run_summary.json`
- [x] /api/runs/<id> returns manifest-based fields: status/schema_version/error/artifacts
- [x] `/api/runs/<id>/health` added and returns `{status, missing_artifacts, warnings, error, schema_version}`
- [x] /api/runs/<id>/table and /plot read files via artifacts declared in manifest
- [x] missing artifact returns clear 404 message (e.g. `No artifacts declared...` / `Artifact ... is missing`)
- [ ] health + table/plot verified against a real workspace with both correlation and forecast manifests

## Workspace integration
- [x] scanner reads:
  - [x] <workspace>/correlation-engine/reports/*/summary.json
  - [x] <workspace>/forecasting-backtest/runs/*/run_summary.json
- [ ] MARKETLAB_WORKSPACE apunta al workspace padre con ambos repos y estructura esperada (correlation/forecast)

## Outcome
- [x] Status: BLOCKED (backend runtime blocked by environment, no network for pip install)

## Evidencia de ejecución
- Frontend: `cd /Users/carlaherrera/Desktop/market-sentiment-lab/market-research-dashboard && make frontend-install` (éxito, npm ci)
- Frontend: `cd /Users/carlaherrera/Desktop/market-sentiment-lab/market-research-dashboard && make frontend-build` (éxito)
- Demo mode contract (scripts rápidos):
  - `node - <<'NODE' ...` validó `DEMO_DATA.runs` (3 runs, 0 campos obligatorios faltantes de contrato en mock)
- Backend install/runtime:
  - `cd /Users/carlaherrera/Desktop/market-sentiment-lab/market-research-dashboard && make backend-install` **falló**: sin red para resolver `Django==5.1.2`
  - `cd /Users/carlaherrera/Desktop/market-sentiment-lab/market-research-dashboard && make backend-check` **falló**: `ModuleNotFoundError: No module named 'django'`
  - `cd /Users/carlaherrera/Desktop/market-sentiment-lab && ls -d correlation-engine forecasting-backtest` (estructura padre detectada, pero falta `correlation-engine/reports`)
  - `cd /Users/carlaherrera/Desktop/market-sentiment-lab && python3 - <<'PY' ...` contó manifestos:
    - `correlation-engine/reports` inexistente / 0 `summary.json`
    - `forecasting-backtest/runs` existe / 5 `run_summary.json`
