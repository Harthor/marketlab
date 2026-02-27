# MarketLab status report (LLM-friendly)

- generated_at_utc: 2026-02-26T20:30:39.732669+00:00
- root: /Users/carlaherrera/Desktop/market-sentiment-lab

## Workspace artifacts snapshot
- datasets: count=1 latest=/Users/carlaherrera/Desktop/market-sentiment-lab/altdata-web-signals/data/datasets/BTC-USD/1d.parquet mtime=2026-02-26T18:49:00.978502+00:00
- signals: count=4 latest=/Users/carlaherrera/Desktop/market-sentiment-lab/altdata-web-signals/data/signals/rss/nvidia/1d.parquet mtime=2026-02-26T18:49:00.969706+00:00
- processed_prices: count=1 latest=/Users/carlaherrera/Desktop/market-sentiment-lab/market-data-ingest/data/processed/DEMO/1d.parquet mtime=2026-02-26T19:18:30.547060+00:00
- corr_manifests: count=2 latest=/Users/carlaherrera/Desktop/market-sentiment-lab/correlation-engine/reports/20260226T194255_213Z_returns_1d_30lag_71ff8b4a_seed42/summary.json mtime=2026-02-26T19:42:55.251809+00:00
- forecast_manifests: count=8 latest=/Users/carlaherrera/Desktop/market-sentiment-lab/forecasting-backtest/runs/ridge_20260226-192002_527cf975/run_summary.json mtime=2026-02-26T19:20:03.271524+00:00

## marketlab-core
- path: /Users/carlaherrera/Desktop/market-sentiment-lab/marketlab-core
- git: none (no .git directory detected)
- checklist: 18/24 (75%)
- keyfiles: AGENTS.md, CHECKLIST.md, RUNBOOK.md, README.md, docs/contracts.md, docs/artifacts.md
- stack: {'has_pyproject': True, 'has_requirements': False, 'has_frontend': False, 'has_backend': False, 'has_makefile': False, 'has_docker_compose': False, 'has_venv': True}
- next_step: Ensure docs/contracts.md + docs/artifacts.md + manifest/dataset validators + tests.

## market-data-ingest
- path: /Users/carlaherrera/Desktop/market-sentiment-lab/market-data-ingest
- git: none (no .git directory detected)
- checklist: 4/10 (40%)
- keyfiles: AGENTS.md, CHECKLIST.md, RUNBOOK.md, README.md
- stack: {'has_pyproject': True, 'has_requirements': False, 'has_frontend': False, 'has_backend': False, 'has_makefile': False, 'has_docker_compose': False, 'has_venv': True}
- next_step: Close checklist items with highest leverage (contracts + golden-path offline).

## altdata-web-signals
- path: /Users/carlaherrera/Desktop/market-sentiment-lab/altdata-web-signals
- git: none (no .git directory detected)
- checklist: 11/13 (85%)
- keyfiles: AGENTS.md, CHECKLIST.md, RUNBOOK.md, README.md
- stack: {'has_pyproject': True, 'has_requirements': False, 'has_frontend': False, 'has_backend': False, 'has_makefile': False, 'has_docker_compose': False, 'has_venv': True}
- next_step: Review open checklist items and generate golden-path artifacts.

## correlation-engine
- path: /Users/carlaherrera/Desktop/market-sentiment-lab/correlation-engine
- git: none (no .git directory detected)
- checklist: 0/16 (0%)
- keyfiles: AGENTS.md, CHECKLIST.md, RUNBOOK.md, README.md
- stack: {'has_pyproject': True, 'has_requirements': False, 'has_frontend': False, 'has_backend': False, 'has_makefile': False, 'has_docker_compose': False, 'has_venv': True}
- next_step: Close checklist items with highest leverage (contracts + golden-path offline).

## forecasting-backtest
- path: /Users/carlaherrera/Desktop/market-sentiment-lab/forecasting-backtest
- git: none (no .git directory detected)
- checklist: 15/15 (100%)
- keyfiles: AGENTS.md, CHECKLIST.md, RUNBOOK.md, README.md, Makefile
- stack: {'has_pyproject': True, 'has_requirements': False, 'has_frontend': False, 'has_backend': False, 'has_makefile': True, 'has_docker_compose': False, 'has_venv': True}
- next_step: Run CI (ruff/mypy/pytest or npm build) and generate 1 real run.

## market-research-dashboard
- path: /Users/carlaherrera/Desktop/market-sentiment-lab/market-research-dashboard
- git: none (no .git directory detected)
- checklist: 13/15 (87%)
- keyfiles: AGENTS.md, CHECKLIST.md, RUNBOOK.md, README.md, Makefile, docker-compose.yml
- stack: {'has_pyproject': False, 'has_requirements': True, 'has_frontend': True, 'has_backend': True, 'has_makefile': True, 'has_docker_compose': True, 'has_venv': True}
- next_step: Run frontend in demo mode; then wire real mode reading manifests via MARKETLAB_WORKSPACE.
