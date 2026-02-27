# Strategy Research Roadmap

## Top 5 recomendadas (orden de implementación)

### 1) Strat12VolCompressionBreakout
- Por qué primero: complementa bien a baseline mean reversion (captura fases expansivas de volatilidad).
- Timeframe inicial: 1h.
- Universo inicial: top10 scoring (luego top20 si PF se sostiene).
- Validación: sanity -> walk-forward -> OOS.
- Complementariedad con v3c: alta (estilo opuesto, tendencia/expansión).

### 2) Strat09DonchianPullbackTrend
- Por qué segundo: estructura simple, robusta, fácil de depurar en Freqtrade.
- Timeframe inicial: 1h.
- Universo inicial: top10 scoring.
- Validación: sanity -> fee sensitivity -> walk-forward.
- Complementariedad con v3c: alta (trend pullback vs mean reversion pura).

### 3) Strat16DailyRegimeHourlyPullback
- Por qué tercero: añade filtro macro 1d que puede recortar falsos positivos y DD.
- Timeframe inicial: 1h + informative 1d.
- Universo inicial: top10 scoring.
- Validación: sanity -> OOS temporal -> walk-forward corto.
- Complementariedad con v3c: media-alta (misma base pullback, mejor filtro de régimen).

### 4) Strat06RSIBBRegimeReclaim
- Por qué cuarto: mejora incremental sobre familia baseline, baja complejidad y alta trazabilidad.
- Timeframe inicial: 1h.
- Universo inicial: top10 scoring.
- Validación: sanity -> compare directo vs v3c -> OOS.
- Complementariedad con v3c: media (misma familia, útil para variantes controladas).

### 5) Strat17HTFTrendLTFReversion
- Por qué quinto: enfoque híbrido MTF útil para balancear frecuencia/calidad.
- Timeframe inicial: 1h con informative 4h.
- Universo inicial: top10 scoring.
- Validación: sanity -> walk-forward -> fee sensitivity.
- Complementariedad con v3c: alta (timing distinto y filtro HTF).

## Orden sugerido de trabajo
1. Implementar 1 estrategia de tendencia/expansión (Strat12).
2. Implementar 1 estrategia trend-pullback más clásica (Strat09).
3. Probar variante MTF con filtro diario (Strat16).
4. Volver a familia mean reversion para upgrade incremental (Strat06).
5. Recién después intentar híbridos más complejos (Strat17, Strat13).

## Criterios de avance por fase
- Pasar de sanity a walk-forward solo si:
  - PF >= 1.05
  - DD controlado relativo al baseline
  - trades suficientes para inferencia (según timeframe/universo)
- Pasar de top10 a top20 solo si no hay degradación clara de PF.

## Qué evitar al inicio
- Regime-switching demasiado complejo (Strat13) sin evidencia previa.
- Ideas microstructure no backtesteables con OHLCV (orderbook real, latencia, imbalance L2).
