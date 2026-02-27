# market-data-ingest — Runbook

#!/usr/bin/env bash

REPO_ROOT="/Users/carlaherrera/Desktop/market-sentiment-lab"

cd "$REPO_ROOT/market-data-ingest"
PYTHON_BIN="$("$REPO_ROOT/tools/python_select.sh")"

bash ../tools/bootstrap_venv.sh . --editable
source .venv/bin/activate
ruff check .
mypy .
pytest -q

# Golden path (BTC-USD, >= 2 años)

$PYTHON_BIN scripts/fetch_btcusd_prices.py \
  --symbol BTC-USD \
  --timeframe 1d \
  --start 2018-01-01 \
  --end 2026-01-01 \
  --source yfinance \
  --venue coinbase \
  --publish-canonical \
  --root .

# Golden path alternativo (si querés hacerlo desde altdata-web-signals con yfinance + gating append-only):
$PYTHON_BIN "$REPO_ROOT/altdata-web-signals/tools/fetch_btc_1d_yfinance.py" \
  --symbol BTC-USD \
  --start 2018-01-01 \
  --min-rows 365 \
  --max-staleness-days 3

# Luego, desde altdata-web-signals:
cd "$REPO_ROOT/altdata-web-signals"
$PYTHON_BIN -m altdata_web_signals.cli wiki \
  --topics "Bitcoin" \
  --freq 1d \
  --start 2018-01-01 \
  --end 2026-01-01 \
  --signals-root "$REPO_ROOT/altdata-web-signals/data/signals"
$PYTHON_BIN -m altdata_web_signals.cli build-dataset \
  --symbol BTC-USD \
  --freq 1d \
  --prices-root "$REPO_ROOT/altdata-web-signals/data/datasets" \
  --join how=outer \
  --fill-method none \
  --start 2018-01-01 \
  --end 2026-01-01

# 2) Verificar que hay filas suficientes y path esperado
$PYTHON_BIN - <<'PY'
import pandas as pd
from pathlib import Path
for p in [Path("data/processed/BTC-USD/1d.parquet")] + list(Path("data/processed/yfinance/BTC-USD/1d").glob("*.parquet")):
    if not p.exists():
        print(f"MISSING: {p}")
        continue
    frame = pd.read_parquet(p)
    print(f"{p}: rows={len(frame)}")
    if len(frame) > 0:
        print(f"  range={frame['ts_utc'].min()} -> {frame['ts_utc'].max()}")

if Path("data/processed/BTC-USD/1d.parquet").exists():
    frame = pd.read_parquet("data/processed/BTC-USD/1d.parquet")
    assert len(frame) >= 365, "dataset has <365 rows in canonical path"
PY
