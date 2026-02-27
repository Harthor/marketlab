# Correlation Engine Run 20260227T155346_635Z_returns_1d_5lag_2b7f0314

## Configuración

- run_id: `20260227T155346_635Z_returns_1d_5lag_2b7f0314`
- status: `complete`
- schema_version: `1.0`
- dataset: `/Users/carlaherrera/Desktop/market-sentiment-lab/altdata-web-signals/data/datasets/BTC-USD/1d_research_ready.parquet`
- dataset_hash: `2b7f03145cae06aca391abdfeca89b584810875df09cbaf5a04499bcf8be76ce`
- timestamp_col: `ts_utc`
- target: `returns_1d`
- max_lag: `5`
- windows: `10, 20, 40`
- bootstrap: `0`
- seed: `42`
- min_effective_obs: `10`
- Fecha UTC: 2026-02-27T15:53:48.020894+00:00

## Qué incluye este run

- `summary.json`: contrato de manifest para lectura por dashboard.
- `tables/feature_summary.parquet` y `tables/feature_summary.csv`: resumen plano de métricas por feature.
- `tables/lag_profile.parquet` y `tables/lag_profile.csv` (si está disponible): perfil de lag feature/lag.
- `tables/correlations.parquet` y `tables/correlations.csv`: Pearson/Spearman + p-values + BH correction.
- `tables/top_correlations.parquet` y `tables/top_correlations.csv`: top correlations ordenadas por |corr|.
- `tables/rolling_corr.parquet` y `tables/rolling_corr.csv`: rolling corr por ventanas.
- `tables/lag.parquet` y `tables/lag.csv`: alias de lag_profile.
- `tables/lag_summary.parquet` y `tables/lag_summary.csv`: resumen de best lag por feature.
- `tables/mi.parquet` y `tables/mi.csv`: Mutual information.
- `tables/distance_correlation.parquet` (si se habilita).
- `tables/bootstrap_ci.parquet` (si bootstrap>0): intervalos de confianza.
- `plots/rolling_corr.png`, `plots/lag_profiles.png`: visualizaciones.

## Reproducibilidad

- Se guardan dataset_hash, config y config_hash.
- La corrida escribe summary con status (`running`, `complete`, `failed`).
