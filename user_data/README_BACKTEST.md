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
python3 -m pip install -U pip freqtrade

python3 -m freqtrade download-data -c user_data/configs/config.bt_spot.json --timeframes 5m 1h 4h 1d --timerange 20250101-20260201
python3 -m freqtrade backtesting -c user_data/configs/config.bt_spot.json -s Strat03RSIBBMeanReversion --timerange 20250101-20260201
```

## 2) Multi-par SPOT con selección por score

```bash
python3 user_data/scripts/select_pairs.py --market spot --timeframe 5m --lookback-days 30 --top-n 80 --min-age-days 180 --out user_data/whitelists/whitelist.selected.json
```

El `run_bt.py multi` crea config temporal apuntando a esa whitelist y corre todo:

```bash
python3 user_data/scripts/run_bt.py multi --market spot --strategy Strat03RSIBBMeanReversion --timeframe 5m --timerange 20250101-20260201 --lookback-days 30 --top-n 80 --min-age-days 180 --out user_data/whitelists/whitelist.selected.json
```

También podés correr manual usando config temporal propia si querés inspección completa.

## 3) Sanity FUTURES (ejemplo)

```bash
python3 -m freqtrade download-data -c user_data/configs/config.bt_futures.json --timeframes 5m 1h 4h 1d --timerange 20250101-20260201
python3 -m freqtrade backtesting -c user_data/configs/config.bt_futures.json -s Strat02DonchianTurtle --timerange 20250101-20260201
```

## 4) Runner rápido

Sanity spot:

```bash
python3 user_data/scripts/run_bt.py sanity --market spot --strategy Strat03RSIBBMeanReversion --timeframe 5m --timerange 20250101-20260201
```

Sanity futures:

```bash
python3 user_data/scripts/run_bt.py sanity --market futures --strategy Strat02DonchianTurtle --timeframe 5m --timerange 20250101-20260201
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

## Research vs Backtest (separados)

- El motor de research descubre tickers y señales candidatas (por ejemplo social/YouTube/Reddit).
- El motor de backtesting valida estrategias con datos históricos de mercado.
- El bridge `generate_runtime_config_from_research.py` transforma candidatos en `pair_whitelist` para un runtime config de Freqtrade.

Comandos zsh-safe de una línea:

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && user_data/scripts/run_research_refresh.sh
```

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && user_data/scripts/run_backtest_batch_1h.sh
```

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && .env/bin/python user_data/scripts/summarize_last_backtest.py
```

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && user_data/scripts/run_daily_pipeline.sh
```

Si aparece prompt `>` o `bquote>`, presioná `Ctrl+C` y pegá de nuevo el comando completo.

## Errores de red / Binance

- El pipeline puede fallar por DNS o exchange (por ejemplo `api.binance.com`) aunque el código esté correcto.
- `run_backtest_batch_1h.sh` guarda estado en `user_data/reports/backtest_last_status.json` y log en `user_data/logs/`.
- Con `STRICT_BACKTEST=0` el pipeline diario sigue, ejecuta el resumen y deja status/logs para diagnóstico.
- Con `STRICT_BACKTEST=1` el pipeline propaga error no-cero cuando falla backtest.

Comandos zsh-safe:

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && STRICT_BACKTEST=0 user_data/scripts/run_daily_pipeline.sh
```

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && STRICT_BACKTEST=1 user_data/scripts/run_daily_pipeline.sh
```

## Dashboard de backtests

Genera un índice histórico de runs sin abrir JSON manualmente:

- `user_data/reports/backtest_index.csv`
- `user_data/reports/backtest_index.json`
- `user_data/reports/backtest_dashboard.md`

Comandos zsh-safe:

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && .env/bin/python user_data/scripts/build_backtest_index.py
```

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && cat user_data/reports/backtest_dashboard.md
```

## Walk-forward 1h

Ejecuta tres ventanas 1h (A/B/C) y luego arma un reporte comparativo tolerante a fallos de red/exchange.

Comandos zsh-safe:

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && user_data/scripts/run_walkforward_1h.sh
```

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && .env/bin/python user_data/scripts/build_walkforward_report.py
```

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && cat user_data/reports/walkforward_1h.md
```

## Deploy a VPS (systemd)

Comandos zsh-safe:

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && bash deploy/bootstrap_vps.sh
```

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && PROJECT_DIR=/opt/market-sentiment-lab bash deploy/systemd/install_systemd_units.sh
```

```bash
cd /Users/carlaherrera/Desktop/market-sentiment-lab && STRICT_BACKTEST=0 user_data/scripts/run_daily_pipeline.sh
```

Guia completa:

```bash
cat deploy/DEPLOY_VPS.md
```
