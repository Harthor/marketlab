#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "== MarketLab cycle =="
echo "ROOT=$ROOT"

echo ""
echo "[1/4] Status (fast)"
"$ROOT/tools/status.sh" >/dev/null

echo ""
echo "[2/4] Manifest validation (plus)"
PYTHONNOUSERSITE=1 /opt/homebrew/bin/python3.11 -S "$ROOT/tools/marketlab_status_plus.py" >/dev/null

echo ""
echo "[3/4] Pack for LLM"
"$ROOT/tools/pack_for_llm.sh" >/dev/null || true

echo ""
echo "[4/4] Generate next prompts (simple template)"
# Minimal prompt templates; you can edit these later.
cat > "$ROOT/next_prompts/marketlab-core.md" <<'P'
Objetivo: cerrar contrato + validators + manifest helpers.
- Asegurar docs/contracts.md y docs/artifacts.md completos.
- Implementar validate_manifest + write_json_atomic + validate_dataset_df etc.
- Agregar tests (ruff/mypy/pytest).
P
cat > "$ROOT/next_prompts/market-data-ingest.md" <<'P'
Objetivo: hardening de outputs + completar checklist.
- Escritura atómica parquet (tmp->rename).
- Asegurar demo prices y quality-report.
- Documentar MARKETDATA_PROCESSED_DIR.
P
cat > "$ROOT/next_prompts/altdata-web-signals.md" <<'P'
Objetivo: dataset robusto ante missing signals.
- coverage_signal_* flags + meta.json por dataset.
- Tests de schema + meta.
P
cat > "$ROOT/next_prompts/correlation-engine.md" <<'P'
Objetivo: manifest contractual + atomic commit.
- summary.json con schema_version/kind/status/artifacts y sin NaN/Inf.
- escribir manifest al final (atomic).
- n_effective por feature.
P
cat > "$ROOT/next_prompts/forecasting-backtest.md" <<'P'
Objetivo: run_summary.json contractual + artifacts estables.
- schema_version/kind/status/artifacts.
- predictions.parquet + equity.parquet siempre.
P
cat > "$ROOT/next_prompts/market-research-dashboard.md" <<'P'
Objetivo: backend devuelve JSON válido siempre.
- Sanitizar NaN/Inf -> None antes de Response.
- Scanner por manifests.
- endpoint /health para artifacts missing.
P

echo "Wrote prompts in: $ROOT/next_prompts/"
echo "Wrote pack: $ROOT/llm_pack.zip"
echo "Wrote: $ROOT/marketlab_status.json and marketlab_status_plus.json"
