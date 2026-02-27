# altdata-web-signals — Runbook

#!/usr/bin/env bash

REPO_ROOT="/Users/carlaherrera/Desktop/market-sentiment-lab"

cd "$REPO_ROOT/altdata-web-signals"
PYTHON_BIN="$("$REPO_ROOT/tools/python_select.sh")"

if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: No se encontró python >=3.11. Revisitá tools/python_select.sh" >&2
  exit 1
fi

bash ../tools/bootstrap_venv.sh . --requirements requirements.txt --editable
source .venv/bin/activate
ruff check .
mypy .
pytest -q

# Golden path (BTC-USD research dataset)
# 0) Generar/actualizar base de precios BTC-USD en 1d (append-only + validaciones)
$PYTHON_BIN "$REPO_ROOT/altdata-web-signals/tools/fetch_btc_1d_yfinance.py" \
  --symbol BTC-USD \
  --start 2018-01-01 \
  --min-rows 365 \
  --max-staleness-days 3 \
  --out "data/datasets/BTC-USD/1d.parquet"

cd "$REPO_ROOT/altdata-web-signals"
# 1) Construir señales (opcional) y usar build-dataset
$PYTHON_BIN -m altdata_web_signals.cli wiki \
  --topics "Bitcoin" \
  --freq 1d \
  --start 2023-01-01 \
  --end 2025-01-01 \
  --signals-root data/signals

# Opcional: RSS si tenés un feed estable en un archivo YAML
# signals rss \
#   --feeds-file "$REPO_ROOT/market-data-ingest/feeds.example.yaml" \
#   --keywords "bitcoin,apple,nvidia" \
#   --start 2023-01-01 \
#   --end 2025-01-01 \
#   --signals-root data/signals

# 2) Build dataset (incluye close + returns_1d + signal_*)
$PYTHON_BIN -m altdata_web_signals.cli build-dataset \
  --symbol BTC-USD \
  --freq 1d \
  --prices-root "$REPO_ROOT/altdata-web-signals/data/datasets" \
  --price-source yfinance \
  --join how=outer \
  --fill-method none \
  --start 2023-01-01 \
  --end 2025-01-01

# 3) Validaciones mínimas del dataset
$PYTHON_BIN - <<'PY'
from pathlib import Path
import polars as pl
import json

path = Path("data/datasets/BTC-USD/1d.parquet")
frame = pl.read_parquet(path)
print("dataset_rows", frame.height)
print("dataset_columns", frame.columns)
assert frame.height >= 365, "dataset_rows < 365"
for required in ["ts_utc", "close", "returns_1d"]:
    assert required in frame.columns, f"missing {required}"
meta = json.loads((path.with_suffix(".meta.json")).read_text(encoding="utf-8"))
assert meta["rows"] >= 365, "meta rows < 365"
assert "dataset_hash" in meta, "meta must include dataset_hash"
assert meta.get("returns_def"), "meta must include returns_def"
signal_cols = [c for c in frame.columns if c.startswith("signal_")]
coverage_cols = [c for c in frame.columns if c.startswith("coverage_signal_")]
assert len(coverage_cols) == len(signal_cols), "coverage columns mismatch"
print("dataset_ok=1")
PY

# 4) Corr engine sobre el dataset de BTC-USD
cd "$REPO_ROOT/correlation-engine"
corr run \
  --dataset "$REPO_ROOT/altdata-web-signals/data/datasets/BTC-USD/1d.parquet" \
  --target returns_1d \
  --timestamp ts_utc \
  --max-lag 30 \
  --windows 30,90,180

# 5) Validar manifiesto sin NaN/Inf
$PYTHON_BIN - <<'PY'
import json
from pathlib import Path
import math

reports = Path("reports")
latest = max([p for p in reports.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime)
summary = json.loads((latest / "summary.json").read_text(encoding="utf-8"))

def contains_nonfinite(value):
    if isinstance(value, dict):
        return any(contains_nonfinite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_nonfinite(v) for v in value)
    if isinstance(value, (float, int)):
        return not math.isfinite(float(value))
    return False

if contains_nonfinite(summary):
    raise SystemExit("summary has non-finite values")
print(f"summary_ok run_id={summary['run_id']} dataset_rows={summary['dataset_rows']}")
PY
