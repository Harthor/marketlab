#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SYMBOL="BTC-USD"
FREQ="1d"
MIN_ROWS="365"
MAX_STALENESS_DAYS="10"
TARGET="returns_1d"
TIMESTAMP="ts_utc"

MODEL="ridge"
RUN_ID="ridge_btc1d_tsutc_$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_ROOT="runs"

MAX_LAG="5"
WINDOWS="10,20,40"
TOP="25"

DO_PACK="0"

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --symbol BTC-USD
  --freq 1d
  --min-rows 365
  --max-staleness-days 10
  --target returns_1d
  --timestamp ts_utc
  --model ridge
  --run-id <id>
  --max-lag 5
  --windows 10,20,40
  --top 25
  --pack   (run marketlab_cycle.sh + pack_for_llm.sh at the end)
EOF
}

# Parse args
while [ $# -gt 0 ]; do
  case "$1" in
    --symbol) SYMBOL="$2"; shift 2 ;;
    --freq) FREQ="$2"; shift 2 ;;
    --min-rows) MIN_ROWS="$2"; shift 2 ;;
    --max-staleness-days) MAX_STALENESS_DAYS="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --timestamp) TIMESTAMP="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --max-lag) MAX_LAG="$2"; shift 2 ;;
    --windows) WINDOWS="$2"; shift 2 ;;
    --top) TOP="$2"; shift 2 ;;
    --pack) DO_PACK="1"; shift 1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 2 ;;
  esac
done

ALT="$ROOT/altdata-web-signals"
CORR="$ROOT/correlation-engine"
FORE="$ROOT/forecasting-backtest"

require_venv() {
  local repo="$1"
  if [ ! -f "$repo/.venv/bin/activate" ]; then
    echo "ERROR: Missing venv: $repo/.venv"
    echo "Fix: create it (python3.11 -m venv .venv) and install deps."
    exit 2
  fi
}

run_in_venv() {
  local repo="$1"; shift
  ( cd "$repo"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    echo "== $(basename "$repo") =="

    python -V
    "$@"
  )
}

echo "== MarketLab Golden Path =="
echo "ROOT=$ROOT"
echo "SYMBOL=$SYMBOL  FREQ=$FREQ"
echo "TARGET=$TARGET  TIMESTAMP=$TIMESTAMP"
echo "MODEL=$MODEL    RUN_ID=$RUN_ID"
echo

require_venv "$ALT"
require_venv "$CORR"
require_venv "$FORE"

# 1) Build research-ready dataset
echo "[1/3] Build research-ready dataset"
run_in_venv "$ALT" python tools/build_research_ready.py --min-rows "$MIN_ROWS" --max-staleness-days "$MAX_STALENESS_DAYS"

DATASET_DIR="$ALT/data/datasets/$SYMBOL"
DATASET_RR="$DATASET_DIR/${FREQ}_research_ready.parquet"

# fallback auto-detect
if [ ! -f "$DATASET_RR" ]; then
  CANDIDATE="$(ls -1 "$DATASET_DIR"/*research_ready*.parquet 2>/dev/null | head -n 1 || true)"
  if [ -n "$CANDIDATE" ]; then
    DATASET_RR="$CANDIDATE"
  fi
fi

if [ ! -f "$DATASET_RR" ]; then
  echo "ERROR: research-ready dataset not found under: $DATASET_DIR"
  echo "Expected: ${FREQ}_research_ready.parquet or *research_ready*.parquet"
  exit 2
fi

echo "DATASET_RR=$DATASET_RR"

# quick validation: ensure required cols exist
run_in_venv "$ALT" python - <<PY
import pandas as pd
p=r"$DATASET_RR"
df=pd.read_parquet(p)
need={"$TIMESTAMP","$TARGET"}
missing=need-set(df.columns)
print("rows:", len(df))
print("min_ts:", pd.to_datetime(df["$TIMESTAMP"]).min(), "max_ts:", pd.to_datetime(df["$TIMESTAMP"]).max())
print("missing_cols:", sorted(missing))
if missing:
    raise SystemExit(2)
PY

# 2) Correlation smoke
echo
echo "[2/3] Correlation smoke"
run_in_venv "$CORR" python scripts/run_smoke.py "$DATASET_RR" \
  --target "$TARGET" --timestamp "$TIMESTAMP" \
  --max-lag "$MAX_LAG" --windows "$WINDOWS" --top "$TOP"

# 3) Forecast train
echo
echo "[3/3] Forecast train"
run_in_venv "$FORE" python -m forecasting_backtest.cli train \
  --dataset "$DATASET_RR" \
  --target "$TARGET" \
  --model "$MODEL" \
  --timestamp "$TIMESTAMP" \
  --run-id "$RUN_ID" \
  --output-root "$OUTPUT_ROOT"

echo
echo "== Outputs (latest) =="

if [ -d "$CORR/reports" ]; then
  echo "-- correlation-engine/reports (latest 3):"
  ls -1dt "$CORR"/reports/* 2>/dev/null | head -n 3 || true
fi

if [ -d "$FORE/$OUTPUT_ROOT" ]; then
  echo "-- forecasting-backtest/$OUTPUT_ROOT (latest 3):"
  ls -1dt "$FORE"/"$OUTPUT_ROOT"/* 2>/dev/null | head -n 3 || true
fi

# Optional pack
if [ "$DO_PACK" = "1" ]; then
  echo
  echo "== Running marketlab cycle + pack =="
  ( cd "$ROOT"
    ./tools/marketlab_cycle.sh
    ./tools/pack_for_llm.sh
    ls -la llm_pack.zip || true
  )
fi

echo
echo "DONE."
