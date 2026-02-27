# Correlation Engine Run 20260227T010513_780Z_returns_1d_5lag_bcebc7df

## Configuración

- run_id: `20260227T010513_780Z_returns_1d_5lag_bcebc7df`
- status: `skipped`
- schema_version: `1.0`
- dataset: `/tmp/small_corr.parquet`
- dataset_hash: `bcebc7dfcb31a9cf13da5f32e74095f5ab103455d75084b0548b70fa8c0f8789`
- timestamp_col: `ts_utc`
- target: `returns_1d`
- max_lag: `5`
- windows: `3`
- bootstrap: `0`
- seed: `7`
- min_effective_obs: `10`
- Fecha UTC: 2026-02-27T01:05:13.803289+00:00

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
