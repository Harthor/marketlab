# altdata-web-signals

MVP para recolectar señales web (series temporales) y alinearlas con precios con foco en investigación.

## Qué hace

- Extrae señales de **Wikipedia Pageviews** por tópico.
- Extrae señales de **RSS/News** por keywords (contains o regex).
- (Opcional) Extrae señales de **Google Trends** con `pytrends` en modo best-effort.
- Guarda señales por `(source, topic, freq)` en `data/signals/` en Parquet.
- Construye un dataset `research-ready` con:
  - `ts_utc`
  - `close`
  - `returns_1d`
  - `symbol`
  - `signal_wiki_<topic>`
  - `signal_rss_<keyword>`
  - ...
- Incluye script de análisis rápido de correlación (rolling y lags).
- Incluye tests con fixtures sin red para parsing.

## Estructura

- `src/altdata_web_signals/`
  - `fetchers/wiki.py` -> Wikipedia
  - `fetchers/rss.py` -> RSS
  - `fetchers/trends.py` -> Google Trends (opcional)
  - `dataset.py` -> armado de dataset
  - `cli.py` -> comando `signals`
  - `storage.py` -> layout de archivos
- `reports/quick_signal_analysis.py` -> análisis rápido.
- `tests/fixtures/` y `tests/` -> fixtures y tests parser sin red.

## Dependencias clave

Depende de `marketlab-core` para:
- `normalize_timezone`
- `align`
- `compute_returns`
- `Cache`

Si `marketlab-core` no estuviera disponible en runtime, se usa un fallback local para no romper.

## Uso del CLI

### 1) Wikipedia

```bash
signals wiki \
  --topics "Bitcoin,Apple Inc.,Nvidia" \
  --start 2021-01-01 \
  --end 2025-12-31
```

Genera por ejemplo:
- `data/signals/wiki/bitcoin/1d.parquet`
- `data/signals/wiki/apple_inc/1d.parquet`
- `data/signals/wiki/nvidia/1d.parquet`

### 2) RSS

Archivo de entrada `feeds.yaml` con:

```yaml
feeds:
  - "https://.../feed.xml"
```

```bash
signals rss \
  --feeds-file feeds.yaml \
  --keywords "bitcoin,apple,nvidia" \
  --start 2021-01-01 \
  --end 2025-12-31
```

### 3) Build dataset

Por defecto busca precios en:
`$MARKETDATA_PROCESSED_DIR` o (fallback) en `<root>/data/processed/<symbol>/<freq>/*.parquet` y el layout histórico `<source>/<symbol>/<freq>/*.parquet`.

El dataset estable se guarda en:
`data/datasets/<symbol>/<freq>.parquet`

También genera metadata en:
`data/datasets/<symbol>/<freq>.meta.json`

- `sources` y `topics` usados
- `keywords` (normalizados por tópico)
- `date_range`
- `join_mode` y `fill_method`
- `code_version`
- `returns_1d` (definición aplicada)
- `dataset_hash` (sha256 del parquet generado)

```bash
signals build-dataset --symbol BTC-USD --join how=outer --freq 1d
```

### BTC 1d dataset (yfinance)

Script específico para resolver el caso de dataset muy corto (ej. filas `2`), con fetch incremental:

```bash
python3 tools/fetch_btc_1d_yfinance.py \
  --symbol BTC-USD \
  --start 2018-01-01 \
  --min-rows 365 \
  --max-staleness-days 3
```

Qué hace:
- Descarga `BTC-USD` en `1d` desde `yfinance`.
- Normaliza a columnas `ts_utc`, `open`, `high`, `low`, `close`, `volume`.
- Si el parquet ya existe, hace append-only (buffer de 3 días y dedupe por fecha).
- Gating duro:
  - no escribe si filas finales `< 365`,
  - no escribe si `max(ts_utc) < hoy_utc - 3 días`.
- Escribe de forma atómica `data/datasets/BTC-USD/1d.parquet`.
- Genera `data/datasets/BTC-USD/1d.meta.json` con `sha256`, `rows`, `rango fechas`, `provider`, etc.

### 4) (Opcional) Trends

```bash
signals trends --keywords "bitcoin,apple" --start 2021-01-01 --end 2025-12-31
```

Requiere instalar extras:

```bash
pip install .[trends]
```

## Qué significa cada señal

- `signal_wiki_<topic>`: pageviews diarios normalizados por fecha (0 si no hay actividad en la fecha).
- `signal_rss_<keyword>`: conteo de items RSS diarios donde el título o description coincide con la keyword.
- `signal_trends_<keyword>`: interés relativo (0-100) por día, si se habilita.

## Riesgos y sesgos

- **Lag de publicación**: las noticias pueden publicarse con delay y el conteo puede incluir re-etiquetado.
- **Sesgo de cobertura**: sólo se capturan fuentes incluidas en el feed/lista.
- **Términos ambiguos**: keywords simples pueden colisionar con otros contextos.
- **Look-ahead bias**: si se usa el mismo día de publicación para predecir retorno del mismo día.
  - Evitar usando retornos shiftados en validación temporal (ej. `returns_1d.shift(1)` para modelado).
- **Cambios de API**: especialmente en `pytrends`, endpoints no garantizan estabilidad.

## Análisis rápido

Script: `reports/quick_signal_analysis.py`

Genera:
- `reports/rolling_signal_correlations.csv`
- `reports/cross_correlation_lags.csv`

Incluye:
- rolling corr en ventanas 30 y 90 días entre señal y `returns_1d`
- cross-corr con lags de -7 a +7 días

## Testing sin red

Tests incluidos usan fixtures en `tests/fixtures/*` y no llaman red.

## TODOs explícitos

- [ ] Agregar tests de integración con caché en disco y manejo TTL.
- [ ] Agregar normalización de timezone por configuración de proyecto.
- [ ] Persistencia y escritura de señales de `trends` en `data/signals/`.
- [ ] Agregar `duckdb` opcional como catálogo de señales para consultas ad-hoc.

## Cómo extender a otra fuente

1. Agregar un módulo en `src/altdata_web_signals/fetchers/<nueva_fuente>.py`.
2. Exponer una función `fetch_<fuente>_signals(...)` que devuelva DataFrames con columnas `ts_utc` y `signal_<source>_<topic>`.
3. Guardar con `write_signal_frame(..., source='<fuente>', topic='<topic>', freq=...)`.
4. Agregar comando en `cli.py` y un fixture de parser en `tests/fixtures`.

## Instalación y ejecución recomendada

### Requisitos
- Python >= 3.11
- Entorno con acceso a internet para descargar dependencias (opcional si instalás paquetes manualmente)

### Instalación local (editable)

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab/altdata-web-signals
PYTHON_BIN="$(/Users/carlaherrera/Desktop/market-sentiment-lab/tools/python_select.sh)"
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install .[analysis]
```

Alternativa (bootstrap central con selector Python >= 3.11):

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab
bash tools/bootstrap_venv.sh altdata-web-signals --editable
```

Opcional (Google Trends):

```bash
python -m pip install .[trends]
```

Pruebas:

```bash
python -m pytest -q
```

### Demo sin red (fixtures + precios sintéticos)

```bash
python scripts/run_research_demo.py
```

Genera:
- `data/datasets/BTC-USD/1d.parquet`
- `data/datasets/BTC-USD/1d.meta.json`
- `reports/rolling_signal_correlations.csv`
- `reports/cross_correlation_lags.csv`
- `reports/prices_and_returns.png`
- `reports/corr_signal_*.png`

### Análisis y visualización del dataset

```bash
python reports/quick_signal_analysis.py --dataset data/datasets/BTC-USD/1d.parquet
python reports/visualize_dataset.py --dataset data/datasets/BTC-USD/1d.parquet --out-dir reports
```

## Qué entender en términos de producto

- Este repo se usa como **backend de investigación** de señales.
- La capa “visible” hoy no es una UI web automática, sino archivos parquet con salida de señales + dataset.
- Puedes consumir estos parquet desde un notebook (pandas/polars), tu propio dashboard o una BI.

Sugerencia de visualización rápida:
- Crear un notebook y graficar:
  - `close`, `returns_1d`
  - `signal_*` individualmente
  - `reports/quick_signal_analysis.py` (rolling 30/90 y lags)
- Subir esta lógica a `Streamlit/Plotly` cuando quieras un frontend para mostrarlo a otros.
