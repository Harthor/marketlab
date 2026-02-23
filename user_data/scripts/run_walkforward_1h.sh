#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

BASE_CFG="${BASE_CFG:-user_data/configs/config.bt_spot_1h_top10_mr1h_effective.json}"
STRAT="${STRAT:-Strat03RSIBBMeanReversion_v3c}"
CANDIDATES="${CANDIDATES:-user_data/research/out/candidates_latest.csv}"
RUNTIME_CFG="${RUNTIME_CFG:-user_data/configs/runtime.config.bt_spot_1h_walkforward.json}"
STATUS_JSON="user_data/reports/walkforward_status_1h.json"
WINDOWS="${WINDOWS:-A=20250101-20250601,B=20250601-20251001,C=20251001-20260201}"

mkdir -p user_data/logs user_data/reports user_data/configs
TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
MASTER_LOG="user_data/logs/walkforward_1h_${TS_UTC}.log"

log() {
  echo "$1" | tee -a "$MASTER_LOG"
}

init_status() {
  STATUS_JSON_VALUE="$STATUS_JSON" \
  STRAT_VALUE="$STRAT" \
  BASE_CFG_VALUE="$BASE_CFG" \
  WINDOWS_VALUE="$WINDOWS" \
  .env/bin/python - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["STATUS_JSON_VALUE"])
payload = {
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "strategy": os.environ["STRAT_VALUE"],
    "base_config": os.environ["BASE_CFG_VALUE"],
    "windows_spec": os.environ["WINDOWS_VALUE"],
    "bridge_mode": "base_config",
    "runtime_config": os.environ["BASE_CFG_VALUE"],
    "windows": [],
}
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

update_header_status() {
  BRIDGE_MODE_VALUE="$1" \
  RUNTIME_CFG_VALUE="$2" \
  STATUS_JSON_VALUE="$STATUS_JSON" \
  .env/bin/python - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["STATUS_JSON_VALUE"])
payload = {}
if path.exists():
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
payload["bridge_mode"] = os.environ["BRIDGE_MODE_VALUE"]
payload["runtime_config"] = os.environ["RUNTIME_CFG_VALUE"]
path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

append_window_status() {
  WINDOW_NAME_VALUE="$1" \
  TIMERANGE_VALUE="$2" \
  STATUS_VALUE="$3" \
  LOG_PATH_VALUE="$4" \
  RUNTIME_CFG_VALUE="$5" \
  META_FILE_VALUE="$6" \
  ERROR_TYPE_VALUE="$7" \
  MESSAGE_VALUE="$8" \
  STRAT_VALUE="$STRAT" \
  STATUS_JSON_VALUE="$STATUS_JSON" \
  .env/bin/python - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["STATUS_JSON_VALUE"])
payload = {}
if path.exists():
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
if not isinstance(payload.get("windows"), list):
    payload["windows"] = []
payload["windows"] = [
    w for w in payload["windows"]
    if isinstance(w, dict) and w.get("window_name") != os.environ["WINDOW_NAME_VALUE"]
]
payload["windows"].append(
    {
        "window_name": os.environ["WINDOW_NAME_VALUE"],
        "timerange": os.environ["TIMERANGE_VALUE"],
        "strategy": os.environ["STRAT_VALUE"],
        "status": os.environ["STATUS_VALUE"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_config": os.environ["RUNTIME_CFG_VALUE"],
        "log_path": os.environ["LOG_PATH_VALUE"],
        "meta_file": os.environ["META_FILE_VALUE"] or None,
        "error_type": os.environ["ERROR_TYPE_VALUE"] or None,
        "message": os.environ["MESSAGE_VALUE"] or None,
    }
)
path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

latest_meta_file() {
  ls -1t user_data/backtest_results/backtest-result-*.meta.json 2>/dev/null | head -n 1 || true
}

init_status
log "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] walkforward_1h start"
log "strategy=$STRAT"
log "windows=$WINDOWS"

BT_CFG="$BASE_CFG"
if [ -f "$CANDIDATES" ]; then
  if .env/bin/python user_data/scripts/social/generate_runtime_config_from_research.py \
    --base-config "$BASE_CFG" \
    --candidates-csv "$CANDIDATES" \
    --output-config "$RUNTIME_CFG" \
    --top-n 10 \
    --quote USDT >>"$MASTER_LOG" 2>&1; then
    BT_CFG="$RUNTIME_CFG"
    update_header_status "research_bridge" "$BT_CFG"
  else
    BT_CFG="$BASE_CFG"
    update_header_status "bridge_failed_fallback_base" "$BT_CFG"
    log "bridge_status=error fallback_to_base_config=$BASE_CFG"
  fi
else
  update_header_status "base_config_no_candidates" "$BT_CFG"
fi

IFS=',' read -r -a window_items <<< "$WINDOWS"
for item in "${window_items[@]}"; do
  window_name="${item%%=*}"
  timerange="${item#*=}"
  window_name="$(echo "$window_name" | tr -d '[:space:]')"
  timerange="$(echo "$timerange" | tr -d '[:space:]')"
  if [ -z "$window_name" ] || [ -z "$timerange" ] || [ "$window_name" = "$timerange" ]; then
    append_window_status "$window_name" "$timerange" "error" "$MASTER_LOG" "$BT_CFG" "" "invalid_window_spec" "invalid_window_item"
    log "window=$item status=error reason=invalid_window_spec"
    continue
  fi

  WINDOW_LOG="user_data/logs/walkforward_1h_${window_name}_${TS_UTC}.log"
  BEFORE_META="$(latest_meta_file)"
  if .env/bin/freqtrade backtesting -c "$BT_CFG" -s "$STRAT" --timerange "$timerange" >>"$WINDOW_LOG" 2>&1; then
    AFTER_META="$(latest_meta_file)"
    META_FILE=""
    if [ -n "$AFTER_META" ] && [ "$AFTER_META" != "$BEFORE_META" ]; then
      META_FILE="$AFTER_META"
    fi
    append_window_status "$window_name" "$timerange" "ok" "$WINDOW_LOG" "$BT_CFG" "$META_FILE" "" "backtest_completed"
    log "window=$window_name timerange=$timerange status=ok log=$WINDOW_LOG"
  else
    append_window_status "$window_name" "$timerange" "error" "$WINDOW_LOG" "$BT_CFG" "" "network_or_exchange" "freqtrade_backtesting_failed_check_log"
    log "window=$window_name timerange=$timerange status=error log=$WINDOW_LOG"
  fi
done

log "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] walkforward_1h done"
log "status_json=$STATUS_JSON"
log "master_log=$MASTER_LOG"
