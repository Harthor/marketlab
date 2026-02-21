# Backtesting Realista y Reproducible (CLI)

Este setup separa claramente backtesting de UI/live.

- Configs UI existentes: **no modificadas**.
- Configs nuevas para backtest: `use_order_book=false` (fills más realistas con OHLCV, sin orderbook histórico inventado).

## Archivos clave

- Spot backtest config: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/configs/config.bt_spot.json`
- Futures backtest config: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/configs/config.bt_futures.json`
- Selector de pares: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/scripts/select_pairs.py`
- Data helper: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/scripts/ensure_data.py`
- Runner: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/scripts/run_bt.py`

## Nota de timeframe

Configs de sanity quedan con `timeframe = "5m"`.
Para sanity también podés correr en `1h` o `4h` pasando `--timeframe` en comandos de backtest.

## 1) Sanity backtest SPOT (ejemplo)

```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
source .env/bin/activate

freqtrade download-data -c user_data/configs/config.bt_spot.json --timeframes 5m 1h 4h 1d --timerange 20250101-20260201
freqtrade backtesting -c user_data/configs/config.bt_spot.json -s Strat03RSIBBMeanReversion --timerange 20250101-20260201
```

## 2) Multi-par SPOT con selección por score

```bash
python user_data/scripts/select_pairs.py --market spot --timeframe 5m --lookback-days 30 --top-n 80 --min-age-days 180 --out user_data/whitelists/whitelist.selected.json
```

El `run_bt.py multi` crea config temporal apuntando a esa whitelist y corre todo:

```bash
python user_data/scripts/run_bt.py multi --market spot --strategy Strat03RSIBBMeanReversion --timeframe 5m --timerange 20250101-20260201 --lookback-days 30 --top-n 80 --min-age-days 180 --out user_data/whitelists/whitelist.selected.json
```

También podés correr manual usando config temporal propia si querés inspección completa.

## 3) Sanity FUTURES (ejemplo)

```bash
freqtrade download-data -c user_data/configs/config.bt_futures.json --timeframes 5m 1h 4h 1d --timerange 20250101-20260201
freqtrade backtesting -c user_data/configs/config.bt_futures.json -s Strat02DonchianTurtle --timerange 20250101-20260201
```

## 4) Runner rápido

Sanity spot:

```bash
python user_data/scripts/run_bt.py sanity --market spot --strategy Strat03RSIBBMeanReversion --timeframe 5m --timerange 20250101-20260201
```

Sanity futures:

```bash
python user_data/scripts/run_bt.py sanity --market futures --strategy Strat02DonchianTurtle --timeframe 5m --timerange 20250101-20260201
```

## Cómo ayuda esto con el diagnóstico “no hay backtests positivos”

Permite separar tres causas:

1. **Problema de setup/fills**: se corrige al usar configs backtest sin orderbook.
2. **Mala selección de pares**: se aborda con `select_pairs.py` y ranking objetivo.
3. **Estrategia sin edge**: si aun con setup + pares buenos falla, el cuello de botella es la estrategia.

## Outputs del selector

- Whitelist seleccionada: `user_data/whitelists/whitelist.selected.json`
- Ranking completo: `user_data/whitelists/pair_ranking.csv`

CSV incluye: volumen, ATR%, wickiness, data completeness, edad estimada y score final.
