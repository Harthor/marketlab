#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

mkdir -p user_data/logs
TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_PATH="user_data/logs/daily_pipeline_${TS_UTC}.log"
STRICT_BACKTEST="${STRICT_BACKTEST:-0}"
RUNTIME_CFG="user_data/configs/runtime.config.bt_spot_1h_from_research.json"
STATUS_JSON="user_data/reports/backtest_last_status.json"
SUMMARY_JSON="user_data/reports/backtest_last_summary.json"
SUMMARY_MD="user_data/reports/backtest_last_summary.md"
DASHBOARD_MD="user_data/reports/backtest_dashboard.md"

log() {
  echo "$1" | tee -a "$LOG_PATH"
}

research_status="ok"
backtest_status="ok"
summary_status="ok"
dashboard_status="ok"
exit_code=0

log "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] daily_pipeline start"
log "strict_backtest=$STRICT_BACKTEST"

if ! user_data/scripts/run_research_refresh.sh >>"$LOG_PATH" 2>&1; then
  research_status="error"
fi

if ! STRICT_BACKTEST="$STRICT_BACKTEST" user_data/scripts/run_backtest_batch_1h.sh >>"$LOG_PATH" 2>&1; then
  backtest_status="error"
  if [ "$STRICT_BACKTEST" = "1" ]; then
    exit_code=1
  fi
fi

if [ -f "$STATUS_JSON" ]; then
  status_value="$(.env/bin/python - <<'PY'
import json
from pathlib import Path
path = Path("user_data/reports/backtest_last_status.json")
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(payload.get("status", "unknown"))
except Exception:
    print("unknown")
PY
)"
  if [ "$status_value" = "error" ]; then
    backtest_status="error"
    if [ "$STRICT_BACKTEST" = "1" ]; then
      exit_code=1
    fi
  elif [ "$status_value" = "ok" ]; then
    backtest_status="ok"
  else
    backtest_status="error"
  fi
fi

if ! .env/bin/python user_data/scripts/summarize_last_backtest.py >>"$LOG_PATH" 2>&1; then
  summary_status="error"
  exit_code=1
fi

if ! .env/bin/python user_data/scripts/build_backtest_index.py >>"$LOG_PATH" 2>&1; then
  dashboard_status="error"
  exit_code=1
fi

# Optional hook (disabled by default):
# RUN_WALKFORWARD_1H=1 user_data/scripts/run_walkforward_1h.sh
# .env/bin/python user_data/scripts/build_walkforward_report.py
if [ "${RUN_WALKFORWARD_1H:-0}" = "1" ]; then
  if ! user_data/scripts/run_walkforward_1h.sh >>"$LOG_PATH" 2>&1; then
    exit_code=1
  fi
  if ! .env/bin/python user_data/scripts/build_walkforward_report.py >>"$LOG_PATH" 2>&1; then
    exit_code=1
  fi
fi

log "research_status=$research_status"
log "backtest_status=$backtest_status"
log "summary_status=$summary_status"
log "dashboard_status=$dashboard_status"
log "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] daily_pipeline done"

if [ "${exit_code:-0}" -ne 0 ]; then
  log "daily_pipeline_exit=error"
else
  log "daily_pipeline_exit=ok"
fi
log "log_path=$LOG_PATH"
log "runtime_config=$RUNTIME_CFG"
log "status_json=$STATUS_JSON"
log "summary_json=$SUMMARY_JSON"
log "summary_md=$SUMMARY_MD"
log "dashboard_md=$DASHBOARD_MD"

if [ "${exit_code:-0}" -ne 0 ]; then
  exit "$exit_code"
fi
