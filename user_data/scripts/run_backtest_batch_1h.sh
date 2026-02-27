#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

BASE_CFG="${BASE_CFG:-user_data/configs/config.bt_spot_1h_top10_mr1h_effective.json}"
STRAT="${STRAT:-Strat03RSIBBMeanReversion_v3c}"
TIMERANGE="${TIMERANGE:-20250101-20260201}"
CANDIDATES="${CANDIDATES:-user_data/research/out/candidates_latest.csv}"
RUNTIME_CFG="${RUNTIME_CFG:-user_data/configs/runtime.config.bt_spot_1h_from_research.json}"
STRICT_BACKTEST="${STRICT_BACKTEST:-0}"

mkdir -p user_data/logs user_data/reports
TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_PATH="user_data/logs/backtest_1h_${TS_UTC}.log"
STATUS_JSON="user_data/reports/backtest_last_status.json"

write_status() {
  local status="$1"
  local stage="$2"
  local error_type="$3"
  local message="$4"
  STATUS_VALUE="$status" \
  STAGE_VALUE="$stage" \
  ERROR_TYPE_VALUE="$error_type" \
  MESSAGE_VALUE="$message" \
  RUNTIME_CFG_VALUE="$RUNTIME_CFG" \
  LOG_PATH_VALUE="$LOG_PATH" \
  STATUS_JSON_VALUE="$STATUS_JSON" \
  .env/bin/python - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

payload = {
    "status": os.environ["STATUS_VALUE"],
    "stage": os.environ["STAGE_VALUE"],
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "error_type": os.environ["ERROR_TYPE_VALUE"],
    "message": os.environ["MESSAGE_VALUE"],
    "runtime_config": os.environ["RUNTIME_CFG_VALUE"],
    "log_path": os.environ["LOG_PATH_VALUE"],
}
path = Path(os.environ["STATUS_JSON_VALUE"])
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

{
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] backtest_batch_1h start"
echo "base_cfg=$BASE_CFG"
echo "strategy=$STRAT"
echo "timerange=$TIMERANGE"
echo "candidates=$CANDIDATES"
echo "runtime_cfg=$RUNTIME_CFG"
echo "strict_backtest=$STRICT_BACKTEST"

.env/bin/python user_data/scripts/social/generate_runtime_config_from_research.py \
  --base-config "$BASE_CFG" \
  --candidates-csv "$CANDIDATES" \
  --output-config "$RUNTIME_CFG" \
  --top-n 10 \
  --quote USDT

if .env/bin/freqtrade backtesting -c "$RUNTIME_CFG" -s "$STRAT" --timerange "$TIMERANGE"; then
  write_status "ok" "backtest" "none" "backtest_completed"
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] backtest_batch_1h done"
else
  write_status "error" "backtest" "network_or_exchange" "freqtrade_backtesting_failed_check_log"
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] backtest_batch_1h failed"
  if [ "$STRICT_BACKTEST" = "1" ]; then
    exit 1
  fi
fi
} 2>&1 | tee -a "$LOG_PATH"

echo "backtest_log=$LOG_PATH"
echo "runtime_config=$RUNTIME_CFG"
echo "status_json=$STATUS_JSON"
