# Artifacts

Este documento fija la salida esperada de engines para evitar cambios implícitos entre repos.

## `summary.json` (correlation)

Campos obligatorios:

- `run_id` (`str`)
- `created_at_utc` (`str`, ISO-8601 UTC)
- `contract_version` (`str`)
- `schema_version` (`str`, e.g. `1.0`)
- `kind` (`str`, `"correlation"`)
- `status` (`str`, `"complete"` o `"partial"` o `"running"`)
- `assets` (`list[str]`)
- `lags` (`list[int]`)
- `method` (`str`, e.g. `"pearson"`/`"spearman"`)
- `results` (`list[object]`) con al menos:
  - `pair` (`list[str]`, largo 2)
  - `lag` (`int`)
  - `correlation` (`float`)
  - `n` (`int`)

Rutas esperadas:

- `runs/<run_id>/summary.json`
- `runs/<run_id>/correlation_matrix.parquet`
- `runs/<run_id>/cross_corr_by_lag.parquet`
- `runs/<run_id>/correlation_top_pairs.parquet`

## `run_summary.json` (forecast)

Campos obligatorios:

- `run_id` (`str`)
- `created_at_utc` (`str`, ISO-8601 UTC)
- `contract_version` (`str`)
- `schema_version` (`str`, e.g. `1.0`)
- `kind` (`str`, `"forecast"`)
- `status` (`str`, `"complete"` o `"partial"` o `"running"`)
- `model` (`str`)
- `target` (`str`)
- `horizon` (`int`)
- `split` (`str`, e.g. `all`, `test`)
- `rows` (`int`)
- `n_features` (`int`)
- `metrics` (`dict[str, float]`)

Rutas esperadas:

- `runs/<run_id>/run_summary.json`
- `runs/<run_id>/forecast_predictions.parquet`
- `runs/<run_id>/forecast_features.parquet`
- `runs/<run_id>/forecast_metrics.parquet`

## Tablas esperadas por engine y columnas mínimas

### Correlación

- `correlation_matrix.parquet`
  - `run_id`
  - `pair_left`
  - `pair_right`
  - `lag`
  - `correlation`
  - `n`
- `cross_corr_by_lag.parquet`
  - `run_id`
  - `pair_left`
  - `pair_right`
  - `lag`
  - `correlation`
  - `n`
- `correlation_top_pairs.parquet`
  - `run_id`
  - `pair`
  - `lag`
  - `correlation`
  - `n`
  - `rank`

### Forecast

- `forecast_predictions.parquet`
  - `run_id`
  - `ts_utc`
  - `symbol`
  - `y_true`
  - `y_pred`
  - `split`
- `forecast_features.parquet`
  - `run_id`
  - `ts_utc`
  - `symbol`
  - `feature_*`
- `forecast_metrics.parquet`
  - `run_id`
  - `split`
  - `metric`
  - `value`

## Plots esperados por engine

- `correlation_heatmap.png`
- `cross_correlation_lags.png`
- `forecast_coverage.png`
- `forecast_vs_actual.png`
- `residuals_hist.png`
- `forecast_feature_importance.png`

## Semántica de lag (sign convention)

`corr_lag = corr(a_t, b_{t+lag})`

- `lag > 0`: `b` va adelantado (lead) respecto de `a`
- `lag < 0`: `b` va atrasado (lag) respecto de `a`
- `lag = 0`: alineación en el mismo timestamp
