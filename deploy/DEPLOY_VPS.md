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

Opcional (usuario/grupo de servicio):

```bash
cd /opt/market-sentiment-lab
PROJECT_DIR=/opt/market-sentiment-lab SERVICE_USER=ubuntu SERVICE_GROUP=ubuntu bash deploy/systemd/install_systemd_units.sh
```

## Monitoreo con journalctl

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
