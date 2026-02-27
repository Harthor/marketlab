# altdata-web-signals — Checklist

## Dataset builder
- [x] signals build-dataset outputs: data/datasets/<symbol>/<freq>.parquet.
- [x] dataset schema: ts_utc, symbol, close, returns_1d, signal_*. Cobrado en demo y tests (`demo` escribe `data/datasets/BTC-USD/1d.parquet` con señales + coverage flags).
- [x] signals naming normalized: signal_<source>_<topic_slug>. Confirmado por columnas del dataset (`signal_rss_*`, `signal_wiki_*`).
- [x] meta written: data/datasets/<symbol>/<freq>.meta.json (sources/topics/join/fill/range/returns_def/missingness/dataset_hash/coverage_columns). Confirmado en `data/datasets/BTC-USD/1d.meta.json`.

## Offline golden path
- [x] run_research_demo.py runs 100% offline (synthetic prices+signals).
- [x] produces dataset parquet + meta.json. Paths generadas: `data/datasets/BTC-USD/1d.parquet`, `data/datasets/BTC-USD/1d.meta.json`.
- [x] runs quick_signal_analysis and outputs plots/reports (`reports/rolling_signal_correlations.csv`, `reports/cross_correlation_lags.csv`, `reports/signal_correlations_global.csv`, `reports/prices_and_returns.png`, `reports/corr_*.png`).

## Tests
- [x] offline fixtures for parsers. Los fixtures existen y se ejecutan.
- [x] schema validation test for research dataset: `tests/test_dataset_builder.py::test_build_dataset_stable_schema_and_meta` y `test_dataset_builder_graceful_without_signals` pasan (incluyen checks de meta y coverage_*).

## Gates
- [x] ruff check . (pass).
- [ ] mypy . (fallas de typings: import stubs faltantes y 2 advertencias de tipado en análisis/reportes).
- [x] pytest -q (4 passed, warnings por LibreSSL en numpy/urllib3).

## Outcome
- [ ] Status: BLOCKED por entorno de runtime (`python --version` = 3.9.6, proyecto requiere Python >=3.11).
