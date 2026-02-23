#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
SERVICE_USER="${SERVICE_USER:-$(id -un)}"
SERVICE_GROUP="${SERVICE_GROUP:-$(id -gn)}"

SRC_DIR="$PROJECT_DIR/deploy/systemd"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

for unit in market_research.service market_research.timer market_backtest.service market_backtest.timer; do
  if [ ! -f "$SRC_DIR/$unit" ]; then
    echo "[install_systemd_units] missing $SRC_DIR/$unit" >&2
    exit 1
  fi
done

prepare_service() {
  local name="$1"
  local exec_path="$2"
  sed \
    -e "s|^WorkingDirectory=.*|WorkingDirectory=$PROJECT_DIR|" \
    -e "s|^ExecStart=.*|ExecStart=$exec_path|" \
    -e "s|^User=.*|User=$SERVICE_USER|" \
    -e "s|^Group=.*|Group=$SERVICE_GROUP|" \
    "$SRC_DIR/$name" > "$TMP_DIR/$name"
}

prepare_service "market_research.service" "$PROJECT_DIR/user_data/scripts/run_research_refresh.sh"
prepare_service "market_backtest.service" "$PROJECT_DIR/user_data/scripts/run_backtest_batch_1h.sh"
cp "$SRC_DIR/market_research.timer" "$TMP_DIR/market_research.timer"
cp "$SRC_DIR/market_backtest.timer" "$TMP_DIR/market_backtest.timer"

echo "[install_systemd_units] installing units into $SYSTEMD_DIR"
sudo install -m 0644 "$TMP_DIR/market_research.service" "$SYSTEMD_DIR/market_research.service"
sudo install -m 0644 "$TMP_DIR/market_research.timer" "$SYSTEMD_DIR/market_research.timer"
sudo install -m 0644 "$TMP_DIR/market_backtest.service" "$SYSTEMD_DIR/market_backtest.service"
sudo install -m 0644 "$TMP_DIR/market_backtest.timer" "$SYSTEMD_DIR/market_backtest.timer"

sudo systemctl daemon-reload
sudo systemctl enable --now market_research.timer
sudo systemctl enable --now market_backtest.timer

echo "[install_systemd_units] timers status"
sudo systemctl status market_research.timer --no-pager -n 20 || true
sudo systemctl status market_backtest.timer --no-pager -n 20 || true

echo "[install_systemd_units] done"
echo "project_dir=$PROJECT_DIR"
echo "service_user=$SERVICE_USER"
echo "service_group=$SERVICE_GROUP"
