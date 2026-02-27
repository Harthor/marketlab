# Market Research Dashboard

Dashboard para explorar datasets, corridas de análisis de correlación y corridas de backtests desde archivos del filesystem.

## Estructura

- `backend/`: API de Django + Django REST Framework.
- `backend/api/`: serializadores, vistas y lectura de filesystem.
- `frontend/`: UI React + Vite.
- `market-sentiment-lab` (tu workspace, configurable con `MARKETLAB_WORKSPACE`):
  - `correlation-engine/reports`
  - `forecasting-backtest/runs`

La app no usa base de datos pesada inicialmente; toda la información se lee desde disco.

## Requisitos

- Python 3.11+
- Node.js 18+

## Variables de entorno

Backend:

- `MARKETLAB_WORKSPACE`: raíz del monorepo con los resultados (ej. `/Users/<usuario>/Desktop/market-sentiment-lab`).
- `MARKETLAB_DEBUG`: `1` para habilitar CORS permisivo en desarrollo.
- `MARKETLAB_CORS_ORIGINS`: origenes extra de CORS en formato CSV. Ej: `http://localhost:5173,http://127.0.0.1:5173`.

Frontend:

- `VITE_API_BASE_URL`: base URL del backend. Ej: `http://localhost:8000/api`.
- `VITE_DEMO_MODE`: si es `1`, la UI usa un dataset de ejemplo y permite ver layout sin backend.

## Setup local

Desde la raíz `market-research-dashboard`:

1) Backend

```bash
cd backend
../tools/bootstrap_venv.sh . --requirements requirements.txt --editable
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# editar variables según tu workspace
python manage.py check
python manage.py runserver
```

2) Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

3) Arranque conjunto

```bash
cd ..
make dev
```

4) Opción reproducible con Docker Compose (opcional)

```bash
cd ..
make docker-up
```

Se asume que el backend responde en `http://localhost:8000/api` y el frontend en `http://localhost:5173`.

Con Docker Compose, el backend levanta directamente contra el workspace de la raíz (`/workspace/market-sentiment-lab`) y busca manifestos:
- `correlation-engine/reports/*/summary.json`
- `forecasting-backtest/runs/*/run_summary.json`

`make docker-down` corta los servicios y `make docker-logs` sigue la salida.

Para levantar solo el frontend con mocks:

```bash
cd frontend
VITE_DEMO_MODE=1 npm run dev:demo
```

## Verificación backend (modo real)

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab/market-research-dashboard/backend
../tools/bootstrap_venv.sh . --requirements requirements.txt --editable
source .venv/bin/activate
python -m pip install -r requirements.txt
python -c "import django; print(django.get_version())"
python manage.py migrate
export MARKETLAB_WORKSPACE="$HOME/Desktop/market-sentiment-lab"
python manage.py runserver 8000
```

En otra terminal:

```bash
curl -s http://127.0.0.1:8000/api/runs | head -n 40
```

La respuesta debe ser JSON (`[]` o lista de corridas), no HTML de error.

## Endpoints expuestos

- `GET /api/datasets`
- `GET /api/runs`
- `GET /api/runs/<run_id>`
- `GET /api/runs/<run_id>/health`
- `GET /api/runs/<run_id>/table?name=<archivo>&page=<n>&page_size=<m>`
- `GET /api/runs/<run_id>/plot?name=<archivo>`

`<run_id>` es un id estable generado por el backend a partir del path del run.

Las respuestas de `/api/runs` y `/api/runs/<run_id>` incluyen:
- `run_id`
- `kind`
- `created_at_utc`
- `dataset_hash`
- `label` (`model_name`, `top_features` o métrica principal del run)
- `model_name` y `top_features` cuando aplica
- `status` (`complete | running | partial | failed`)
- `schema_version`
- `error`
- `artifacts` con `tables` y `plots`
- `table_names` y `plot_names`
- `paths` con rutas absolutas del run y artifacts declarados

La respuesta de `/api/runs/<run_id>/health` incluye:
- `status`
- `schema_version`
- `missing_artifacts`
- `warnings`
- `error`

## Decisiones de diseño

- Descubrimiento por manifiesto:
  - `correlation-engine/reports/*/summary.json`
  - `forecasting-backtest/runs/*/run_summary.json`
- Cada corrida expone un contrato unificado con campos comunes:
  - `run_id`
  - `kind` (`correlation` | `forecast`)
  - `created_at_utc`
  - `dataset_hash`
  - `model_name` (solo forecast, cuando aplica)
  - `top_features` (solo correlation, cuando aplica)
- El backend valida que `table`/`plot` consultados vengan declarados en el manifiesto antes de abrir archivo. Si el artefacto falta, responde 404 con mensaje explícito.
- Las tablas se exponen con paginación para permitir datasets grandes.
- La seguridad inicial es mínima (`AllowAny`) y CORS habilitado para desarrollo.

## Instalación determinística de frontend

El repo detecta gestor por lockfile:
- `package-lock.json` -> `npm ci`
- `pnpm-lock.yaml` -> `pnpm i --frozen-lockfile`
- `yarn.lock` -> `yarn install --frozen-lockfile`

Comandos:

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab/market-research-dashboard
make install
make frontend-build
```
