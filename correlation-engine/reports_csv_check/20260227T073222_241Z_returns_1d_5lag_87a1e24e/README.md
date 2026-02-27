# Correlation Engine Run 20260227T073222_241Z_returns_1d_5lag_87a1e24e

## Configuración

- run_id: `20260227T073222_241Z_returns_1d_5lag_87a1e24e`
- status: `complete`
- schema_version: `1.0`
- dataset: `reports/run_smoke_dataset.parquet`
- dataset_hash: `87a1e24e01a84e75cc2885fbd9ab63dbad3fd8457123960d3a66c3ab99024f54`
- timestamp_col: `ts_utc`
- target: `returns_1d`
- max_lag: `5`
- windows: `30, 90, 180`
- bootstrap: `0`
- seed: `42`
- min_effective_obs: `10`
- Fecha UTC: 2026-02-27T07:32:22.642613+00:00

## Qué incluye este run

- `summary.json`: contrato de manifest para lectura por dashboard.
- `tables/feature_summary.parquet` y `tables/feature_summary.csv`: resumen plano de métricas por feature.
- `tables/lag_profile.parquet` y `tables/lag_profile.csv` (si está disponible): perfil de lag feature/lag.
- `tables/correlations.parquet` y `tables/correlations.csv`: Pearson/Spearman + p-values + BH correction.
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
