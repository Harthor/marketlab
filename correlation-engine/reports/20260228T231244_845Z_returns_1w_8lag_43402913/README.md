# Correlation Engine Run 20260228T231244_845Z_returns_1w_8lag_43402913

## Configuración

- run_id: `20260228T231244_845Z_returns_1w_8lag_43402913`
- status: `complete`
- schema_version: `1.0`
- dataset: `/Users/carlaherrera/Desktop/marketlab/.claude/worktrees/charming-germain/altdata-web-signals/data/datasets/BTC-USD/btc_weekly_signals.parquet`
- dataset_hash: `43402913602fb05661cddc5a4242719e4916ee48fde6b2a87bbda9929a9b2137`
- timestamp_col: `ts_utc`
- target: `returns_1w`
- max_lag: `8`
- windows: `8, 16, 26`
- bootstrap: `200`
- seed: `42`
- min_effective_obs: `10`
- Fecha UTC: 2026-02-28T23:12:45.977441+00:00

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
