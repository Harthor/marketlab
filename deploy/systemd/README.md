# systemd Deployment (Ubuntu VPS)

This folder contains example `systemd` units for a VPS install at:

- `/opt/market-sentiment-lab`

These templates are for Linux VPS (Ubuntu).  
On macOS, use `cron` or `launchd` instead of `systemd timers`.

## 1) Copy unit files

```bash
cd /opt/market-sentiment-lab
sudo cp deploy/systemd/market_research.service /etc/systemd/system/
sudo cp deploy/systemd/market_research.timer /etc/systemd/system/
sudo cp deploy/systemd/market_backtest.service /etc/systemd/system/
sudo cp deploy/systemd/market_backtest.timer /etc/systemd/system/
```

## 2) Reload systemd

```bash
sudo systemctl daemon-reload
```

## 3) Enable and start timers

```bash
sudo systemctl enable --now market_research.timer
sudo systemctl enable --now market_backtest.timer
```

## 4) Check status

```bash
sudo systemctl status market_research.timer
sudo systemctl status market_backtest.timer
```

## 5) View logs

```bash
sudo journalctl -u market_research.service -n 200 --no-pager
sudo journalctl -u market_backtest.service -n 200 --no-pager
```

Follow logs in real time:

```bash
sudo journalctl -u market_research.service -f
sudo journalctl -u market_backtest.service -f
```

