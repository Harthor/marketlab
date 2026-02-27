# forecasting-backtest — Checklist

## Output contract
- [x] runs/<run_id>/run_summary.json contains:
  - [x] run_id, created_at_utc, kind="forecast"
  - [x] dataset_path, dataset_hash
  - [x] model_name, config/config_hash, seed
  - [x] metrics (regression + trading)
  - [x] artifacts[] with stable (type,name,path)
- [x] tables/predictions.parquet exists (ts_utc,y_true,y_pred,position,pnl)
- [x] tables/equity.parquet exists (ts_utc,equity,drawdown)

## No-leakage
- [x] unit test ensures train/test non-overlap
- [x] backtest uses out-of-sample predictions

## Offline demo
- [x] run_demo.py generates synthetic dataset and produces a run (tables+plots+summary)

## Gates
- [x] ruff check .
- [x] mypy .
- [x] pytest -q

## Outcome
- [x] Status: OK
