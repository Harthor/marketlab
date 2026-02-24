# Deploy VPS (Ubuntu + systemd)

Guia para preparar y operar el proyecto en un VPS Linux sin ejecutar SSH remoto desde este repo.

## Prerequisitos

Instalar en el VPS:

```bash
sudo apt-get update
sudo apt-get install -y git python3.11 python3.11-venv python3-pip build-essential pkg-config libta-lib0 libta-lib0-dev
```

Nota: en algunas versiones de Ubuntu, el paquete de TA-Lib puede variar (`ta-lib` / `libta-lib-dev`).

## Clonacion del repo

```bash
cd /opt
git clone https://github.com/Harthor/market-sentiment-lab.git
cd /opt/market-sentiment-lab
```

## Bootstrap local del proyecto

```bash
cd /opt/market-sentiment-lab
bash deploy/bootstrap_vps.sh
```

Este script:
- crea `.env` si no existe
- actualiza `pip/setuptools/wheel`
- instala dependencias detectadas
- asegura `freqtrade`
- crea `user_data/logs` y `user_data/reports`

## Smoke tests

```bash
cd /opt/market-sentiment-lab
.env/bin/freqtrade --version
bash -n deploy/bootstrap_vps.sh
bash -n deploy/systemd/install_systemd_units.sh
```

Smoke funcional local (sin systemd):

```bash
cd /opt/market-sentiment-lab
STRICT_BACKTEST=0 user_data/scripts/run_daily_pipeline.sh
```

## Instalacion de timers systemd

```bash
cd /opt/market-sentiment-lab
PROJECT_DIR=/opt/market-sentiment-lab bash deploy/systemd/install_systemd_units.sh
```

El instalador:
- copia units/timers a `/etc/systemd/system/`
- crea `/etc/default/market-sentiment-lab` desde `deploy/systemd/market-sentiment-lab.env.example` solo si no existe
- no sobrescribe `/etc/default/market-sentiment-lab` si ya fue personalizado

Editar configuracion externa (recomendado):

```bash
sudo editor /etc/default/market-sentiment-lab
```

Ejemplo minimo:

```bash
PROJECT_DIR=/opt/market-sentiment-lab
STRICT_BACKTEST=0
PYTHONUNBUFFERED=1
```

Nota: `WorkingDirectory` y `ExecStart` quedan resueltos por `install_systemd_units.sh` al instalar las units.
Hardening aplicado en units/timers:
- `Restart=on-failure` y `RestartSec=30` en services
- `StartLimitIntervalSec` y `StartLimitBurst` para evitar loops
- `Persistent=true` + `RandomizedDelaySec` en timers (recupera corridas perdidas y evita picos exactos)

Opcional (usuario/grupo de servicio):

```bash
cd /opt/market-sentiment-lab
PROJECT_DIR=/opt/market-sentiment-lab SERVICE_USER=ubuntu SERVICE_GROUP=ubuntu bash deploy/systemd/install_systemd_units.sh
```

## Monitoreo con journalctl

Timers y proxima ejecucion:

```bash
sudo systemctl list-timers --all | grep -E 'market_research|market_backtest'
```

```bash
sudo journalctl -u market_research.service -n 200 --no-pager
sudo journalctl -u market_backtest.service -n 200 --no-pager
```

Seguimiento en vivo:

```bash
sudo journalctl -u market_research.service -f
sudo journalctl -u market_backtest.service -f
```

## Corrida manual recomendada (modo tolerante)

```bash
cd /opt/market-sentiment-lab
STRICT_BACKTEST=0 user_data/scripts/run_daily_pipeline.sh
```

Outputs esperados:
- logs: `user_data/logs/`
- reportes: `user_data/reports/`
- status backtest: `user_data/reports/backtest_last_status.json`

## Pre-flight checklist (no SSH)

Supuestos explicitos:
- reemplazar variables por tu repo/branch/commit antes de ejecutar en VPS
- estos comandos son de preparacion/verificacion; no ejecutan deploy remoto desde este documento

### A) Preparacion local

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab
python3 --version
test -x .env/bin/python && .env/bin/python --version
test -x .env/bin/freqtrade && .env/bin/freqtrade --version
```

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab
test -f deploy/bootstrap_vps.sh
test -f deploy/systemd/install_systemd_units.sh
test -f deploy/systemd/market_research.service
test -f deploy/systemd/market_research.timer
test -f deploy/systemd/market_backtest.service
test -f deploy/systemd/market_backtest.timer
test -f deploy/systemd/market-sentiment-lab.env.example
test -d user_data
test -d user_data/scripts
```

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab
bash -n deploy/bootstrap_vps.sh
bash -n deploy/systemd/install_systemd_units.sh
bash -n user_data/scripts/run_research_refresh.sh
bash -n user_data/scripts/run_backtest_batch_1h.sh
bash -n user_data/scripts/run_daily_pipeline.sh
bash -n user_data/scripts/run_walkforward_1h.sh
.env/bin/python -m py_compile user_data/scripts/social/generate_runtime_config_from_research.py user_data/scripts/summarize_last_backtest.py user_data/scripts/build_backtest_index.py user_data/scripts/build_walkforward_report.py
```

### B) Preparacion en VPS (comandos, no ejecutar aqui)

```bash
export PROJECT_DIR=/opt/market-sentiment-lab
export DEPLOY_REF=main
export SERVICE_USER=ubuntu
export SERVICE_GROUP=ubuntu
```

```bash
sudo mkdir -p /opt
cd /opt
if [ -d market-sentiment-lab/.git ]; then cd market-sentiment-lab && git fetch --all --prune; else git clone https://github.com/Harthor/market-sentiment-lab.git && cd market-sentiment-lab; fi
git checkout "$DEPLOY_REF"
git pull --ff-only
```

```bash
cd "$PROJECT_DIR"
bash deploy/bootstrap_vps.sh
```

```bash
if [ ! -f /etc/default/market-sentiment-lab ]; then sudo cp deploy/systemd/market-sentiment-lab.env.example /etc/default/market-sentiment-lab; fi
sudo editor /etc/default/market-sentiment-lab
```

```bash
cd "$PROJECT_DIR"
PROJECT_DIR="$PROJECT_DIR" SERVICE_USER="$SERVICE_USER" SERVICE_GROUP="$SERVICE_GROUP" bash deploy/systemd/install_systemd_units.sh
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now market_research.timer
sudo systemctl enable --now market_backtest.timer
sudo systemctl status market_research.timer market_backtest.timer --no-pager
sudo journalctl -u market_research.service -e --no-pager
sudo journalctl -u market_backtest.service -e --no-pager
sudo systemctl list-timers --all | grep market
```

### C) Rollback rapido (comandos, no ejecutar aqui)

```bash
sudo systemctl disable --now market_research.timer market_backtest.timer
sudo systemctl stop market_research.service market_backtest.service || true
sudo rm -f /etc/systemd/system/market_research.service /etc/systemd/system/market_research.timer /etc/systemd/system/market_backtest.service /etc/systemd/system/market_backtest.timer
sudo systemctl daemon-reload
sudo systemctl reset-failed
```

### Pitfalls comunes

- Permisos de `/etc/default/market-sentiment-lab`: crear/editar con `sudo` y validar owner/permisos.
- Working directory: `PROJECT_DIR` debe apuntar al root del repo real en VPS.
- PATH/venv: correr scripts con `.env/bin/python` y `.env/bin/freqtrade`.
- Logs: primero revisar `journalctl -u market_research.service` y `journalctl -u market_backtest.service`.
