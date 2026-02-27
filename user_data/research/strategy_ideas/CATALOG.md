# Strategy Research Catalog

Objetivo: catálogo práctico de estrategias candidatas para testear en el pipeline actual (spot, backtesting Freqtrade, foco en 1h/4h/30m).

## A) Mean Reversion

### 1) Strat06RSIBBRegimeReclaim
- Familia: Mean Reversion
- Idea central: mean reversion de sobreventa con filtro de tendencia larga para evitar comprar caídas estructurales. Busca reclaim rápido sobre media de Bollinger.
- Indicadores/señales: RSI(14), BB(20,2), EMA200, ATR(14), ADX(14).
- Filtro de régimen: close > EMA200 y ADX < 25.
- Entrada: RSI < 33, close < BB.lower, vela actual cierra por encima del low previo (rebote inicial).
- Salida: close > BB.mid o RSI > 50.
- Riesgos: en tendencias bajistas violentas puede encadenar pérdidas rápidas.
- Métricas primero: PF, maxDD, winrate, OOS, fee sensitivity.
- Dificultad: 2/5.
- Compatibilidad Freqtrade: alta.
- Prioridad: alta.

### 2) Strat07VWAPDistanceReversion
- Familia: Mean Reversion
- Idea central: revertir distancia extrema respecto de VWAP intradía/rolling, evitando operar cuando la volatilidad está expandiendo de forma direccional.
- Indicadores/señales: VWAP rolling, z-score de distancia, RSI, ATR.
- Filtro de régimen: ADX < 22 y ATR% no creciente abruptamente.
- Entrada: z-score distancia < -2, RSI < 35.
- Salida: regreso a VWAP/z-score > -0.5.
- Riesgos: falsas reversión en días de noticia.
- Métricas primero: PF, expectancy, DD, número de trades.
- Dificultad: 3/5.
- Compatibilidad Freqtrade: media-alta.
- Prioridad: media.

### 3) Strat08KeltnerMeanReversion
- Familia: Mean Reversion
- Idea central: usar canales Keltner (EMA + ATR bands) en vez de Bollinger para controlar mejor shocks de volatilidad.
- Indicadores/señales: EMA20, ATR(20), Keltner bands, RSI.
- Filtro de régimen: close > EMA200 y ADX < 23.
- Entrada: close bajo banda inferior Keltner y RSI < 38.
- Salida: close sobre EMA20 o RSI > 52.
- Riesgos: bajo número de señales en mercados demasiado limpios.
- Métricas primero: trades/day, PF, fee sensitivity.
- Dificultad: 2/5.
- Compatibilidad Freqtrade: alta.
- Prioridad: media.

## B) Trend / Breakout

### 4) Strat09DonchianPullbackTrend
- Familia: Trend/Breakout
- Idea central: combinar breakout Donchian con entrada en pullback para evitar comprar máximos extendidos.
- Indicadores/señales: Donchian 20/10, EMA20/EMA50/EMA200, ADX.
- Filtro de régimen: close > EMA200, EMA20 > EMA50, ADX > 18.
- Entrada: breakout confirmado recientemente y pullback a EMA20 con cierre alcista.
- Salida: close < EMA20 o close < Donchian low(10).
- Riesgos: whipsaw en rangos anchos sin tendencia sostenida.
- Métricas primero: PF, maxDD, distribución por par.
- Dificultad: 3/5.
- Compatibilidad Freqtrade: alta.
- Prioridad: alta.

### 5) Strat10SupertrendContinuation
- Familia: Trend/Breakout
- Idea central: continuación de tendencia por cambio/confirmación de Supertrend con filtro de pendiente de EMA200.
- Indicadores/señales: Supertrend, EMA200 slope, RSI.
- Filtro de régimen: EMA200 ascendente.
- Entrada: flip a bullish + RSI > 50.
- Salida: flip a bearish o close < EMA50.
- Riesgos: alta sensibilidad al parámetro de ATR multipliers.
- Métricas primero: PF, DD, estabilidad mensual.
- Dificultad: 3/5.
- Compatibilidad Freqtrade: media-alta.
- Prioridad: media.

### 6) Strat11ADXTrendImpulse
- Familia: Trend/Breakout
- Idea central: capturar impulsos cuando ADX cruza umbral y precio rompe rango corto.
- Indicadores/señales: ADX, highest(12), lowest(12), ATR.
- Filtro de régimen: close > EMA200 y ADX rising.
- Entrada: close > highest(12) y ADX > 22.
- Salida: close < EMA20 o ATR-trailing stop.
- Riesgos: sobreoperación en micro-breakouts falsos.
- Métricas primero: PF, rejected signals, DD.
- Dificultad: 2/5.
- Compatibilidad Freqtrade: alta.
- Prioridad: media.

## C) Volatility / Regime

### 7) Strat12VolCompressionBreakout
- Familia: Volatility/Regime
- Idea central: entrar cuando la volatilidad se comprime (BB width baja) y luego rompe al alza con régimen favorable.
- Indicadores/señales: BB width percentile, EMA200, ATR expansion.
- Filtro de régimen: close > EMA200 y EMA200 slope > 0.
- Entrada: BB width en cuantil bajo + ruptura de high corto + confirmación de volumen.
- Salida: pérdida de EMA20 o trailing ATR.
- Riesgos: compresiones que no expanden y terminan en chop.
- Métricas primero: PF, trades, DD, OOS.
- Dificultad: 4/5.
- Compatibilidad Freqtrade: alta.
- Prioridad: alta.

### 8) Strat13ATRRegimeSwitch
- Familia: Volatility/Regime
- Idea central: conmutar entre lógica trend y reversion según ATR% y ADX (dos submodos en una sola estrategia).
- Indicadores/señales: ATR%, ADX, EMA200, RSI, Donchian.
- Filtro de régimen: ATR% alto => trend mode; ATR% bajo => mean-reversion mode.
- Entrada: depende del submodo activo.
- Salida: depende del submodo activo + stop común ATR.
- Riesgos: complejidad adicional, overfitting de umbrales.
- Métricas primero: PF por submodo, OOS, estabilidad temporal.
- Dificultad: 5/5.
- Compatibilidad Freqtrade: media.
- Prioridad: baja-media.

## D) Market Microstructure / Execution-inspired

### 9) Strat14SessionRangeBreakout
- Familia: Execution-inspired
- Idea central: usar rango de sesión temporal (ej. primeras N velas del día) para breakout posterior, sin depender de orderbook histórico.
- Indicadores/señales: session high/low, ATR, EMA filter.
- Filtro de régimen: close > EMA200 (solo largos).
- Entrada: ruptura session high con confirmación de close.
- Salida: vuelta al rango o trailing ATR.
- Riesgos: sensibilidad a definición de sesión en cripto 24/7.
- Métricas primero: PF, DD, robustez por mes.
- Dificultad: 3/5.
- Compatibilidad Freqtrade: media (backtesteable si se define sesión por UTC).
- Prioridad: media.

### 10) Strat15SpreadProxyMomentum
- Familia: Execution-inspired
- Idea central: aproximar “calidad de ejecución” con proxies de vela (wickiness y rango relativo) para filtrar entradas momentum.
- Indicadores/señales: wickiness ratio, ATR%, EMA trend.
- Filtro de régimen: wickiness bajo y ADX > umbral.
- Entrada: breakout corto en velas limpias (poca mecha).
- Salida: pérdida EMA20 o trailing.
- Riesgos: proxy imperfecto; no reemplaza orderbook real.
- Métricas primero: PF, slippage sensitivity (aproximada por fee stress), DD.
- Dificultad: 4/5.
- Compatibilidad Freqtrade: media (limitada, sin orderbook real).
- Prioridad: baja-media.

Limitación explícita microstructure:
- Estrategias que dependen de profundidad de libro, imbalance L2 o micro-latencia real no son bien backtesteables en Freqtrade con OHLCV puro.

## E) Multi-timeframe / Regime-switching

### 11) Strat16DailyRegimeHourlyPullback
- Familia: Multi-timeframe
- Idea central: régimen diario (close_1d > SMA200_1d) + ejecución en 1h por pullback a EMA20.
- Indicadores/señales: SMA200 1d (informative), EMA20/50 1h, RSI.
- Filtro de régimen: bullish solo cuando 1d está sobre SMA200.
- Entrada: pullback controlado en 1h y cierre alcista.
- Salida: close < EMA50 o RSI deteriora.
- Riesgos: menos frecuencia y dependencia del filtro diario.
- Métricas primero: PF, trades, OOS.
- Dificultad: 3/5.
- Compatibilidad Freqtrade: alta.
- Prioridad: alta.

### 12) Strat17HTFTrendLTFReversion
- Familia: Multi-timeframe / Regime-switching
- Idea central: tendencia en 4h, entrada de reversión en 1h para mejorar timing.
- Indicadores/señales: EMA200 4h, slope 4h, RSI/BB en 1h.
- Filtro de régimen: 4h alcista fuerte.
- Entrada: en 1h, pullback profundo con RSI bajo pero dentro de tendencia HTF.
- Salida: regreso a BB mid o invalidación HTF local.
- Riesgos: desalineación entre marcos temporales, timing difícil.
- Métricas primero: PF, DD, trades por par.
- Dificultad: 4/5.
- Compatibilidad Freqtrade: alta.
- Prioridad: media-alta.

---

## Observaciones prácticas
- Primer foco: ideas con compatibilidad alta y baja complejidad para ganar velocidad de ciclo.
- Evitar inicialmente estrategias con demasiados switches de régimen para no contaminar señal de robustez.
