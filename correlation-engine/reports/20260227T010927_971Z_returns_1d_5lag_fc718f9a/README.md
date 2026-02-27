# Correlation Engine Run 20260227T010927_971Z_returns_1d_5lag_fc718f9a

## Configuración

- run_id: `20260227T010927_971Z_returns_1d_5lag_fc718f9a`
- status: `complete`
- schema_version: `1.0`
- dataset: `/tmp/synthetic_corr.parquet`
- dataset_hash: `fc718f9a44a5d599d74432ec1e844239de388eea94e5b4e7b6125ba511cb14f3`
- timestamp_col: `ts_utc`
- target: `returns_1d`
- max_lag: `5`
- windows: `3, 5, 8`
- bootstrap: `0`
- seed: `42`
- min_effective_obs: `10`
- Fecha UTC: 2026-02-27T01:09:28.235754+00:00

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
