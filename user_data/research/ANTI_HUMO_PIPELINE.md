# Pre-screen + Anti-Humo Pipeline

## 1) Pre-screen an Idea (Before Coding)
Use:

```bash
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/strategy_prescreener.py \
  --description "Trend reclaim on 1h with EMA200 regime, ADX filter, exact stop and exits" \
  --timeframe 1h \
  --out user_data/research/strategy_specs/prescreen_example.json
```

Output includes:
- `score_total` (0-100)
- sub-scores
- flags
- recommendation (`IMPLEMENT` / `NEEDS_SPEC` / `DISCARD_IDEA`)

## 2) Register/Validate a Strategy Spec
Create spec skeleton:

```bash
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/strategy_spec.py \
  new --spec-id stratXX_example_v1 --format json
```

Validate:

```bash
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/strategy_spec.py \
  validate --spec user_data/research/strategy_specs/stratXX_example_v1.json
```

## 3) Anti-humo Validation Post Backtest
Dry-run (recommended first):

```bash
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/anti_smoke_validator.py \
  --experiment-id 20260220T150811Z_strat03rsibbmeanreversion-v3c_1h_top15-mr1h-effective \
  --dry-run
```

Write robustness report + write back to result:

```bash
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/anti_smoke_validator.py \
  --experiment-id 20260220T150811Z_strat03rsibbmeanreversion-v3c_1h_top15-mr1h-effective \
  --dry-run \
  --write-back
```

Optional command execution (if you want to actually run checks):
- `--run-lookahead`
- `--run-recursive`

## 4) Ingest with Spec/Robustness Metadata
Pass optional fields in orchestrator ingest:

```bash
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/orchestrator.py ingest-and-recommend \
  --from-meta user_data/backtest_results/stress_mr1h_20260220/top15_mr1h_effective.meta.json \
  --strategy Strat03RSIBBMeanReversion_v3c \
  --family mean_reversion \
  --config user_data/configs/config.bt_spot_1h_top15_mr1h_effective.json \
  --timeframe 1h \
  --timerange 20250101-20260201 \
  --universe top15_mr1h_effective \
  --market spot \
  --idea-spec-id strat03_v3c_spec \
  --robustness-report user_data/experiments/robustness/20260220T150811Z_strat03rsibbmeanreversion-v3c_1h_top15-mr1h-effective.robustness.json
```

## 5) Regenerate Research Leaderboard

```bash
/Users/carlaherrera/Desktop/codex/freqtrade/.env/bin/python user_data/scripts/research_leaderboard.py
```

Outputs:
- `user_data/research/RESEARCH_LEADERBOARD.md`
- `user_data/research/research_leaderboard.json`
