# Liquid Pairs Workflow (Conservative High-Trade)

Rutas detectadas en este repo:

- Config principal: `/Users/carlaherrera/Desktop/codex/freqtrade/config.json`
- Estrategias: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/strategies/`
- Data: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/data/`
- Whitelists: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/whitelists/`
- Scripts: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/scripts/`

## 1) Construir whitelists líquidas

Genera dos archivos:

- `user_data/whitelists/liquid_spot_top20.json`
- `user_data/whitelists/liquid_futures_top20.json`

```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
source .env/bin/activate
python user_data/scripts/build_liquid_pairs.py
```

Opciones útiles:

```bash
python user_data/scripts/build_liquid_pairs.py \
  --top 20 \
  --min-count 100000 \
  --min-quote-volume 10000000 \
  --max-abs-change-pct 20
```

## 2) Descargar data para whitelist

Descarga por defecto: `1m,3m,5m,1h,1d`, con warmup de `+600` velas.

```bash
python user_data/scripts/download_liquid_data.py \
  --whitelist-file user_data/whitelists/liquid_spot_top20.json \
  --timerange 20260101-20260219
```

Ejemplo futures:

```bash
python user_data/scripts/download_liquid_data.py \
  --whitelist-file user_data/whitelists/liquid_futures_top20.json \
  --market futures \
  --timerange 20260101-20260219
```

## 3) Backtesting usando whitelist

El runner soporta `--whitelist-file`:

```bash
python user_data/scripts/run_backtests.py \
  --non-interactive \
  --strategies Strat03RSIBBMeanReversion \
  --timeframe 1h \
  --timerange 20260101-20260219 \
  --exchange binance \
  --market spot \
  --whitelist-file user_data/whitelists/liquid_spot_top20.json
```

Resumen reportado:

- `profit %`
- `drawdown %`
- `winrate`
- `trades`
- `trades/day`
- `expectancy`
- `profit factor`

## 3.1) Verlo en FreqUI (todo UI-ready)

Se agregaron configs listas para UI:

- Spot: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/config.ui_liquid_spot.json`
- Futures: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/config.ui_liquid_futures.json`

Levantar UI Spot (puerto 8080):

```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
source .env/bin/activate
freqtrade webserver --config /Users/carlaherrera/Desktop/codex/freqtrade/user_data/config.ui_liquid_spot.json
```

Levantar UI Futures (puerto 8081):

```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
source .env/bin/activate
freqtrade webserver --config /Users/carlaherrera/Desktop/codex/freqtrade/user_data/config.ui_liquid_futures.json
```

Abrir:

- Spot: `http://127.0.0.1:8080`
- Futures: `http://127.0.0.1:8081`

## 4) Backtest directo manual (sin runner)

```bash
freqtrade backtesting \
  -c /Users/carlaherrera/Desktop/codex/freqtrade/config.json \
  -s Strat03RSIBBMeanReversion \
  -i 1h \
  --timerange 20260101-20260219 \
  --pairs BTC/USDT ETH/USDT SOL/USDT
```

## Notas

- El scoring prioriza liquidez (quote volume) y actividad (count de trades).
- Se excluyen stables/fiat y tokens leveraged (UP/DOWN/BULL/BEAR).
- Se filtran outliers por variación diaria absoluta (`max_abs_change_pct`).
