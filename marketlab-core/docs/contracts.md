# marketlab-core Contracts

Este documento fija un contrato mínimo para que los repos de investigación y forecast compartan
`timestamp`/`dataset`/`manifest` sin drift.

## 1) Esquema canónico de datos

`ts_utc` es la columna canónica de timestamp y debe estar en UTC.
Se aceptan alias legacy durante migración (`timestamp`), pero nuevos outputs deben
usar `ts_utc`.

### `prices`

Columnas mínimas:

- `ts_utc` (`Datetime[us, UTC]`)
- `symbol` (`Utf8`)
- `venue` (`Utf8`, opcional recomendado para multi-exchange)
- `timeframe` (`Utf8`)
- `open` (`Float`)
- `high` (`Float`)
- `low` (`Float`)
- `close` (`Float`)
- `volume` (`Float`)

Invariantes mínimas:

- `high >= low` por fila
- `open`, `high`, `low`, `close`, `volume` numéricos
- `close > 0`, `volume >= 0` (warning si se rompe)
- `ts_utc` único por (`symbol`, `venue`, `timeframe`) en datasets limpios

### `signals`

Columnas mínimas:

- `ts_utc` (`Datetime[us, UTC]`)
- `symbol` (`Utf8`)
- `signal_name` (`Utf8`)
- al menos uno de: `signal_value`, `score`, `prediction`

Invariantes mínimas:

- columna de señal numérica
- no nulos en `ts_utc`
- `signal_name` presente y estable por corrida

### `research_dataset`

Columnas mínimas:

- `ts_utc` (`Datetime[us, UTC]`)
- `symbol` (`Utf8`)
- `close` (`Float`)
- `returns_1d` (Float, simple o log explícito en nombre)
- `target` o `y` o `label` (Float)
- al menos una columna `signal_*` (cuando aplique)

Invariantes mínimas:

- `returns_1d`, target y `close` numéricos
- si existe `split`, debe ser una de `train`, `val`, `test`
- `ts_utc` ordenado ascendente preferiblemente

## 2) Definición de `returns_1d`

- `returns_1d_simple = close_t / close_{t-1} - 1`
- `returns_1d_log = ln(close_t) - ln(close_{t-1})`

El nombre debe ser explícito (`returns_1d_simple` o `returns_1d_log`) para evitar ambigüedad
entre repos.

## 3) Convención de outputs (directorios y filenames)

- `data/raw/prices/<symbol>/<timeframe>/part-00000.parquet`
- `data/clean/prices/<symbol>/<timeframe>/part-00000.parquet`
- `data/signals/<run_id>/<signal_name>/signals.parquet`
- `data/research/<run_id>/dataset.parquet`
- `data/research/<run_id>/targets.parquet`
- `data/runs/<run_id>/artifacts/manifest.json`

Nombres canónicos por etapa:

- `prices.parquet`
- `signals.parquet`
- `dataset.parquet`
- `features.parquet`
- `returns.parquet`

Recomendación de splits:

- `dataset.parquet` para train+val+test completo
- `dataset_train.parquet`, `dataset_val.parquet`, `dataset_test.parquet`

## 4) Semántica de lag en cross-corr

Definición de firma:

`corr_lag = corr(a_t, b_{t+lag})`

- `lag > 0`: `b` es lead respecto de `a` (se usa antes de `a`)
- `lag < 0`: `b` es lag respecto de `a` (se usa después de `a`)
- `lag = 0`: sincronía temporal

Regla de comunicación:

- siempre documentar el `corr_lag` y el orden de pares (`a`, `b`)
