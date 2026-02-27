# HANDOFF — MarketLab (retomar rápido)

## Estado actual (fuente: marketlab_status_plus.json)
- corr manifests: OK artifacts, pero hay NaN/Inf en fields (nonfinite_values_in_manifest)
- forecast manifests: casi OK, 1 con artifact model path="" (missing_artifacts)
- objetivo inmediato: arreglar /api/runs (sanitize NaN/Inf -> null) para ver UI real.

## Próximo paso (orden)
1) market-research-dashboard: json_sanitize (NaN/Inf -> None) antes de Response en /api/runs y /api/runs/<id>
2) correlation-engine: no escribir NaN/Inf en summary.json (n_effective -> None/int)
3) forecasting-backtest: no incluir artifacts con path=""

## Comandos para retomar
- ./tools/marketlab_cycle.sh
- curl -s http://127.0.0.1:8000/api/runs | head -n 40
