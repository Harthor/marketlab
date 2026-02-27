# market-data-ingest

Proyecto MVP para ingestar OHLCV (acciones, ETFs y crypto), normalizarlo y persistir en un data lake local:
- `data/raw/` con descargas originales
- `data/processed/` con parquet normalizado (`ts_utc, symbol, venue, timeframe, open, high, low, close, volume, source, ingestion_ts, checksum`)
- `data/warehouse.duckdb` con tabla `prices`

## Setup

```bash
Requires Python >= 3.11
bash ../tools/bootstrap_venv.sh . --editable
```

Si tenés `marketlab-core` en editable:

```bash
pip install -e /ruta/a/marketlab-core
```

Dependencias opcionales:
- `ccxt` para crypto (`pip install .[ccxt]`)
- calendarios de trading (`pip install .[trading-calendar]`)

## Uso

### Descargar desde yfinance

```bash
ingest download \
  --symbols AAPL,MSFT \
  --start 2020-01-01 \
  --end 2025-12-31 \
  --timeframe 1d \
  --source yfinance
```

### Fetch BTC-USD histórico para research (dos años)

```bash
python scripts/fetch_btcusd_prices.py \
  --symbol BTC-USD \
  --timeframe 1d \
  --start 2023-01-01 \
  --end 2025-01-01 \
  --source yfinance \
  --publish-canonical
```

Con `--publish-canonical` también se publica `data/processed/BTC-USD/1d.parquet` para consumo directo.

### Construir/actualizar warehouse

```bash
ingest build-warehouse
```

### Reporte de calidad

```bash
ingest quality-report
```

## Generar precios demo (sin red)

Para pruebas rápidas de extremo a extremo:

```bash
python scripts/make_demo_prices.py
```

Opciones útiles:

```bash
python scripts/make_demo_prices.py \
  --symbols AAPL,MSFT \
  --start 2024-01-01 \
  --end 2024-01-15 \
  --timeframe 1d \
  --inject-gap \
  --inject-null \
  --inject-duplicate
```

El script genera parquet normalizado en:

- `data/processed/<symbol>/<timeframe>.parquet` dentro del `--root`
- y, si activás `--write-contract-layout`, en:
  - `data/clean/prices/<symbol>/<timeframe>/part-00000.parquet`

Por cada escritura también se generan metadatos de trazabilidad:

- `data/processed/<symbol>/<timeframe>.meta.json` con:
  - `schema_version`
  - `provider`
  - `rows`
  - `min_ts_utc`
  - `max_ts_utc`
  - `sha256`
  - `generated_at_utc`
- `data/processed/ingest_summary.json` con `kind`, `status` y artefactos por símbolo.

Para escenarios con procesos concurrentes:

- Podés usar `--run-id <id>` para escribir primero en `data/processed/runs/<run-id>/<symbol>/<timeframe>.parquet`.
- Cuando querés refrescar el path canónico `data/processed/<symbol>/<timeframe>.parquet` de forma atómica, agregá `--publish-latest`.

El layout contrato también puede parametrizarse con:

- `MARKETLAB_DATA_ROOT` (default: `<root>/data/clean/prices`)
- `--contract-root` (si querés apuntar otra carpeta)

### quality-report con data demo

Con datos demo generados, corré:

```bash
ingest quality-report
```

Si no tenés `duckdb`, el comando sigue funcionando en fallback sobre `data/processed`.

### Pipeline MVP de extremo a extremo

1) Descargar 2 símbolos (ej. `AAPL,MSFT`) en diario:
```bash
ingest download --symbols AAPL,MSFT --start 2020-01-01 --end 2025-12-31 --timeframe 1d --source yfinance
```
2) Generar/actualizar `data/warehouse.duckdb`:
```bash
ingest build-warehouse
```
3) Verificar calidad:
```bash
ingest quality-report
```

## Observabilidad

La CLI usa logging estructurado (JSON) en stdout para cada etapa (`download_complete`, `warehouse_build_complete`, `quality_symbol_report`), incluyendo:
- filas procesadas
- rango de fechas
- gaps sospechosos, duplicados y outliers por símbolo

## Idempotencia

La carga a DuckDB usa UPSERT lógico:
- la clave lógica es `(ts_utc, symbol, timeframe)`
- si corrés la misma descarga otra vez, no se duplican filas en `prices`

## ¿Cómo apuntar altdata-web-signals a este output?

- Si consume `data/processed`, apuntá tu loader a:
  - `<repo>/data/processed/<symbol>/<timeframe>.parquet`
- Si consume el layout de contratos, usá:
  - `MARKETLAB_DATA_ROOT=<repo>/data/clean/prices`

Ejemplo sugerido:

```bash
export ALT_DATA_PRICES_PATH=$(pwd)/market-data-ingest/data/processed
export MARKETDATA_PROCESSED_DIR=$(pwd)/market-data-ingest/data/processed
```

Si no usás la estrategia de run-dir, evitá correr en paralelo el mismo
`symbol/timeframe` sobre el mismo `--root` para no pisar archivos en camino.

## ¿Cómo agregar un nuevo conector?

1) Crear un módulo en `src/market_data_ingest/connectors/` e implementar `PriceConnector` con:
   - `source` (string)
   - `fetch_ohlcv(symbol, timeframe, start, end)` -> `pd.DataFrame`
2) Asegurar que la DataFrame traiga columnas base (`open, high, low, close, volume`) y `DatetimeIndex`.
3) Registrar el conector en `src/market_data_ingest/connectors/__init__.py` dentro de `get_connector()`.
4) Si requiere API key, documentarlo y dejar fallback/`TODO` con mensaje explícito.

## Notas

- `source=ccxt` queda opcional; para endpoints públicos suele funcionar sin clave.
- Si un exchange/mercado requiere autenticación para ese endpoint, dejar el TODO/documentación del conector.
