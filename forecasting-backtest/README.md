# forecasting-backtest

Repo minimal para baselines de forecasting de series temporales con validación walk-forward y un backtest muy simple, pensado para retornar

- regresión de `returns_1d`
- clasificación direccional de up/down a partir de `pred > 0 / pred < 0`
- métrica de trading con costos transaccionales y slippage

## Requisitos

- Python `>=3.11`
- Dependencia local de [`marketlab-core`](../marketlab-core)
- Instalación editable de este repo desde el raíz de `forecasting-backtest`

En entornos nuevos:

```bash
pip install -e ../marketlab-core
pip install -e .
```

## Instalación rápida (recomendada)

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab/forecasting-backtest
make bootstrap
```

Si hay problemas de entorno de Python, revisá `tools/python_select.sh`
para verificar que devuelve un intérprete >=3.11.

Si querés usar `xgboost` o `lightgbm`:

```bash
pip install -e ".[dev,boosting]"
```

## Bootstrap manual (sin Make)

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab/forecasting-backtest
bash scripts/bootstrap.sh
```

## Tests rápidos

```bash
make test
```

## Demo de validación rápida

Con entorno ya armado:

```bash
make bootstrap
source .venv/bin/activate
make demo
```

El demo:
1) genera `./.demo_data/synthetic_research_ready.parquet` con señal débil,
2) entrena `ridge`,
3) muestra `leaderboard` con el run nuevo.

### Nota de timestamp

El timestamp canónico del stack es `marketlab_core.contracts.TIMESTAMP_COL` (hoy `ts_utc`).
`forecast train` lo usa como default vía ese contrato y conserva `dataset.timestamp_col` en el `run_summary` para trazabilidad.

También podés correrlo directo:

```bash
python scripts/run_demo.py
```

Comandos útiles:

```bash
make train_ridge
make train_naive
make leaderboard
```

## Estructura

- `src/forecasting_backtest/cli.py` -> comando `forecast`
- `src/forecasting_backtest/pipeline.py` -> entrenamiento, walk-forward y generación de artefactos
- `src/forecasting_backtest/backtest.py` -> simulador de señal long/short/flat
- `src/forecasting_backtest/validation.py` -> splits `TimeSeriesSplit` por ventanas de tiempo (2 años / 3 meses por defecto)
- `src/forecasting_backtest/plots.py` -> equity, scatter pred-vs-true, importancia de features
- `runs/<run_id>/` -> salida de cada experimento

## Comandos CLI

```bash
forecast train --dataset data.parquet --target returns_1d --model ridge --config configs/default.yaml
forecast backtest --run-id ridge_20260101-120000_abcd1234
forecast leaderboard
```

Nota de timestamp:
- `forecast train` usa `--timestamp` con default `ts_utc` (desde `marketlab_core.contracts.TIMESTAMP_COL`, con fallback a `ts_utc`).
- Si el dataset viene con `ts`/`timestamp`, se normaliza internamente a `ts_utc` en los artefactos.

### `forecast train`

Ejecuta:

1. carga de dataset (`ts`, `close`, `returns_1d`, features)
2. partición walk-forward (`train_window_days`, `test_window_days`, `step_days`)
3. entrenamiento por fold
4. evaluación:
   - regresión: `MAE`, `RMSE`, `correlación pred-true`
   - clasificación (`up/down`): `accuracy`, `precision`, `recall`, `AUC`
   - info: `hit_rate`, retorno condicional medio
5. backtest simple long/short/flat con costos y slippage
6. guarda artefactos en `runs/<run_id>/`

### Contrato de `run_summary.json` para dashboard

El contrato mínimo esperado por el dashboard es:

- `run_id`
- `created_at_utc`
- `kind` (valor fijo: `"forecast"`)
- `dataset_path`
- `dataset_hash`
- `model_name`
- `config`
- `config_hash`
- `seed`
- `metrics.regression`
- `metrics.trading`
- `artifacts` (lista de objetos con `type`, `name`, `path`)

Además se guardan dos tablas dentro de `tables/`:

- `tables/predictions.parquet` con columnas: `ts_utc`, `y_true`, `y_pred`, `position`, `pnl`
- `tables/equity.parquet` con columnas: `ts_utc`, `equity`, `drawdown`
- `tables/backtest_equity.parquet` se mantiene como alias legacy

### Artefactos por run

- `config_resolved.yaml`
- `run_summary.json`
- `tables/predictions.parquet`
- `tables/equity.parquet`
- `tables/backtest_equity.parquet` (legacy)
- `equity_curve.png`
- `pred_vs_true.png`
- `feature_importance.png` (si aplica)
- `artifacts/model.joblib`

## Evitar leakage

Regla práctica para que el experimento no se contamine:

1. Ordená siempre por `ts` y no mezcles shuffle.
2. No generes features con `shift(-n)` o agregados que usen el futuro.
3. El split walk-forward usa sólo historial pasado en cada fold; revisá que el mínimo de `train_rows` se cumpla.
4. El backtest ejecuta la posición del día `t` con señal de `t` pero aplicado al retorno siguiente (`position` se corrige por 1 fila para evitar look-ahead en la serie).
5. No rellenes faltantes con métodos que introduzcan información futura (solo `ffill`, `bfill`, `interpolate` cuando corresponda y documentado).

## Añadir un modelo nuevo

Agregar un modelo en `src/forecasting_backtest/models.py`:

1. Extender `MODEL_ALIASES` con el nuevo nombre.
2. En `make_model` devolver un estimator de sklearn compatible (`fit/predict`).
3. Si aplica, extender `feature_importance` para extraer importancia de variables.

Ejemplo (skeleton):

```python
if normalized == "mi_modelo":
    return MySklearnCompatibleRegressor(...)
```

Con eso ya queda cubierto por todo el stack de entrenamiento/evaluación.

## Tests

Ver `tests/test_forecast_pipeline.py`:

- dataset sintético con señal débil controlada
- corrida end-to-end de `execute_train`
- test del backtest con costos
- test de splits walk-forward (no overlap + avance temporal)
