# Experiments Orchestrator (MVP+)

Capa semiautomática para experimentación de backtests en este repo, sin tocar configs UI.

## Estructura
- `user_data/experiments/results/`: JSON estructurado por experimento.
- `user_data/experiments/summaries/`: resumen markdown por experimento.
- `user_data/experiments/prompts/`: próximo prompt generado para Codex.
- `user_data/experiments/templates/`: plantillas de prompt.
- `user_data/experiments/logs/`: logs del orchestrator.
- `user_data/experiments/ledger.csv`: historial append-only.
- `user_data/experiments/schema.experiment_result.json`: schema del resultado.
- `user_data/experiments/baseline.json`: baseline marcado manualmente.

## Scripts
- `user_data/scripts/collect_backtest.py`
- `user_data/scripts/orchestrator.py`
- `user_data/scripts/decision_rules.py`
- `user_data/scripts/report_utils.py`
- `user_data/scripts/prompt_templates.py`

## Uso

### 1) Ingestar un resultado (desde meta.json)
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/orchestrator.py ingest \
  --from-meta user_data/backtest_results/backtest-result-2026-02-20_07-51-06.meta.json \
  --strategy Strat03RSIBBMeanReversion_v3c \
  --family mean_reversion \
  --config user_data/configs/config.bt_spot_1h_top10.json \
  --timeframe 1h \
  --timerange 20250101-20260201 \
  --universe top10 \
  --market spot
```

### 2) Ingestar y recomendar en un solo paso
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/orchestrator.py ingest-and-recommend \
  --from-meta user_data/backtest_results/backtest-result-2026-02-20_07-51-06.meta.json \
  --strategy Strat03RSIBBMeanReversion_v3c \
  --family mean_reversion \
  --config user_data/configs/config.bt_spot_1h_top10.json \
  --timeframe 1h \
  --timerange 20250101-20260201 \
  --universe top10 \
  --market spot
```

### 3) Pedir recomendación y generar próximo prompt
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/orchestrator.py recommend
```

### 4) Ver estado
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/orchestrator.py status --last 10 --min-trades 10
```

### 5) Marcar baseline
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/orchestrator.py baseline --experiment-id EXP_ID
```

### 6) Comparar experimentos
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/orchestrator.py compare --ids EXP1 EXP2 EXP3
```

## collect_backtest.py directo

### Desde meta
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/collect_backtest.py \
  --from-meta user_data/backtest_results/backtest-result-...meta.json \
  --strategy Strat03RSIBBMeanReversion_v3c \
  --family mean_reversion \
  --config user_data/configs/config.bt_spot_1h_top10.json \
  --timeframe 1h \
  --timerange 20250101-20260201 \
  --universe top10 \
  --market spot
```

### Desde texto (fallback)
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/collect_backtest.py \
  --from-text /tmp/summary.txt \
  --strategy Strat03RSIBBMeanReversion_v3c \
  --family mean_reversion \
  --config user_data/configs/config.bt_spot_1h_top10.json \
  --timeframe 1h \
  --timerange 20250101-20260201 \
  --universe top10 \
  --market spot
```

## Workflow sugerido
1. Correr backtest con Freqtrade/Codex.
2. Ingestar `meta.json` con `orchestrator.py ingest` o `ingest-and-recommend`.
3. Si usaste `ingest`, ejecutar `orchestrator.py recommend`.
4. Pegar el prompt generado a Codex.
5. Repetir ciclo y acumular evidencia en `ledger.csv`.

## Notas
- No modifica configs UI.
- No modifica estrategias existentes (solo registra/decide/prompt).
- `ledger.csv` es append-only.
- Si el parseo desde `.meta.json` no encuentra zip asociado, se registra `status=partial` con warning.

## UI local de experimentos (Streamlit)
Esta UI es independiente de las UIs de trading.

### Ejecutar UI
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python -m streamlit run user_data/scripts/experiments_ui.py
```

Alternativa (si `streamlit` está en PATH):
```bash
streamlit run user_data/scripts/experiments_ui.py
```

### Dependencias
- Requerida: `streamlit`
- Opcional para auto-refresh en Logs: `streamlit-autorefresh`

## Preferencias del orquestador
El orquestador puede leer preferencias desde:
- `user_data/experiments/preferences.json`

Ejemplo:
```json
{
  "default_timeframe": "1h",
  "prioritize_universe_expansion": true,
  "avoid_lower_timeframes": true,
  "prefer_scoring_pure": true
}
```

Significado:
- `default_timeframe`: timeframe base a priorizar.
- `prioritize_universe_expansion`: sugiere aumentar muestra por pares/splits antes que tocar timeframe.
- `avoid_lower_timeframes`: evita recomendar bajar a 30m/15m/5m por defecto.
- `prefer_scoring_pure`: prioriza scoring puro sobre selección train-based, salvo test explícito.

## Capa Pre-screen + Anti-humo

### Pre-screen de idea (antes de codificar)
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/strategy_prescreener.py \
  --description "Idea de estrategia con reglas de entry/exit/stop/regime" \
  --timeframe 1h
```

### Crear/validar spec estructurada
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/strategy_spec.py new --spec-id stratXX_v1 --format json
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/strategy_spec.py validate --spec user_data/research/strategy_specs/stratXX_v1.json
```

### Validación anti-humo post-backtest
Dry-run (sin ejecutar lookahead/recursive):
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/anti_smoke_validator.py \
  --experiment-id EXP_ID \
  --dry-run \
  --write-back
```

Con ejecución de checks (opcional):
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/anti_smoke_validator.py \
  --experiment-id EXP_ID \
  --run-lookahead \
  --run-recursive \
  --write-back
```

### Ingest con metadata de idea/spec y robustez (opcional)
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/orchestrator.py ingest-and-recommend \
  --from-meta path/to/backtest.meta.json \
  --strategy STRAT \
  --family FAMILY \
  --config user_data/configs/CONFIG.json \
  --timeframe 1h \
  --timerange 20250101-20260201 \
  --universe top15 \
  --market spot \
  --idea-spec-id stratXX_v1 \
  --robustness-report user_data/experiments/robustness/EXP_ID.robustness.json
```

### Regenerar leaderboard de research (md + json)
```bash
cd /Users/carlaherrera/Desktop/codex/freqtrade
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/research_leaderboard.py
```
