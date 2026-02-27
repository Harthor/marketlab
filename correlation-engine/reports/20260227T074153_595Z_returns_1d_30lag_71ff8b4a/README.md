# Correlation Engine Run 20260227T074153_595Z_returns_1d_30lag_71ff8b4a

## Configuración

- run_id: `20260227T074153_595Z_returns_1d_30lag_71ff8b4a`
- status: `skipped`
- schema_version: `1.0`
- dataset: `../altdata-web-signals/data/datasets/BTC-USD/1d.parquet`
- dataset_hash: `71ff8b4aa623d9f3282b207354eab94de4ddbc5d8a5ebf2106a8ef27da47e9f8`
- timestamp_col: `ts_utc`
- target: `returns_1d`
- max_lag: `30`
- windows: `30, 90, 180`
- bootstrap: `0`
- seed: `42`
- min_effective_obs: `10`
- Fecha UTC: 2026-02-27T07:41:53.704309+00:00

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
