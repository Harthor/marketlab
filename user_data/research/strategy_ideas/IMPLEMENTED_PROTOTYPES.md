# Implemented Prototypes (No backtest run yet)

Se implementaron dos prototipos iniciales para sanity tests, sin modificar estrategias existentes.

## 1) Strat06VolCompressionBreakout_v1
- Archivo: `user_data/strategies/Strat06VolCompressionBreakout_v1.py`
- Idea: breakout después de compresión de volatilidad (BB width bajo) en régimen alcista.
- Filtro: close > EMA200, slope EMA200 > 0, ADX > 18.
- Entrada: compresión + ruptura de high(20) previo.
- Salida: close < EMA20 o close < BB mid.
- Riesgo: stop custom ATR.

## 2) Strat07DonchianPullbackTrend_v1
- Archivo: `user_data/strategies/Strat07DonchianPullbackTrend_v1.py`
- Idea: primero breakout Donchian, luego entrada en pullback a EMA20 para evitar chase.
- Filtro: close > EMA200, EMA20 > EMA50, ADX > 18.
- Entrada: breakout reciente + pullback + cierre alcista.
- Salida: close < EMA20 o close < Donchian low(10).
- Riesgo: stop custom ATR.

## Comandos sugeridos para luego (no ejecutados)

```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/freqtrade backtesting \
  -c user_data/configs/config.bt_spot_1h_top10.json \
  -s Strat06VolCompressionBreakout_v1 \
  --timerange 20250101-20260201
```

```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/freqtrade backtesting \
  -c user_data/configs/config.bt_spot_1h_top10.json \
  -s Strat07DonchianPullbackTrend_v1 \
  --timerange 20250101-20260201
```
