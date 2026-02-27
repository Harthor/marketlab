# Correlation Engine Run 20260227T013535_077Z_returns_1d_5lag_87a1e24e

## Configuración

- run_id: `20260227T013535_077Z_returns_1d_5lag_87a1e24e`
- status: `complete`
- schema_version: `1.0`
- dataset: `/Users/carlaherrera/Desktop/market-sentiment-lab/correlation-engine/reports/run_smoke_dataset.parquet`
- dataset_hash: `87a1e24e01a84e75cc2885fbd9ab63dbad3fd8457123960d3a66c3ab99024f54`
- timestamp_col: `ts_utc`
- target: `returns_1d`
- max_lag: `5`
- windows: `10, 20, 40`
- bootstrap: `0`
- seed: `42`
- min_effective_obs: `10`
- Fecha UTC: 2026-02-27T01:35:35.699908+00:00

## Qué incluye este run

- `summary.json`: contrato de manifest para lectura por dashboard.
- `tables/feature_summary.parquet`: resumen plano de métricas por feature.
- `tables/lag_profile.parquet`: perfil de lag feature/lag.
- `tables/correlations.parquet`: Pearson/Spearman + p-values + BH correction.
- `tables/rolling_corr.parquet`: rolling corr por ventanas.
- `tables/lag.parquet`: alias de lag_profile
- `tables/mi.parquet`: Mutual information.
- `tables/distance_correlation.parquet` (si se habilita).
- `tables/bootstrap_ci.parquet` (si bootstrap>0): intervalos de confianza.
- `plots/rolling_corr.png`, `plots/lag_profiles.png`: visualizaciones.

## Reproducibilidad

- Se guardan dataset_hash, config y config_hash.
- La corrida escribe summary con status (`running`, `complete`, `failed`).
