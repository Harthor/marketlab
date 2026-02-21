# Social Signals Architecture (Future Layer)

## Scope (Not Implemented Yet)
This document defines a future architecture to add social-signal features (Twitter/Reddit/KOLs) to the research pipeline, without replacing Freqtrade as backtest engine.

## Goals
- Add narrative/context filters to reduce low-quality strategy ideas.
- Improve pair/universe selection using social activity momentum.
- Keep deterministic, auditable outputs for experiment orchestration.

## Proposed High-Level Architecture
1. Collector Layer
- Ingest from APIs/connectors (Twitter/X, Reddit, curated KOL lists).
- Normalize to common event schema: `source`, `author`, `timestamp`, `symbol_mentions`, `text_hash`, `engagement`.

2. Feature Store Layer
- Time-bucketed features by symbol and interval (e.g., 1h, 4h, 1d).
- Store features in parquet/duckdb (append-only snapshots).
- Preserve raw->feature provenance.

3. Scoring Layer
- Compute social factors:
  - mentions_velocity
  - unique_accounts
  - sentiment_proxy
  - KOL_weighted_mentions
  - narrative_cluster_strength
- Export per-symbol score table by timeframe.

4. Integration Layer (Current Pipeline)
- Universe filter: intersect MR/volume pairs with social-score thresholds.
- Regime filter: allow strategy entries only when social regime is neutral/constructive.
- Extra ranking term: combine existing pair score with social factor under controlled weight.

5. Orchestrator Integration
- Record social snapshot id used by each experiment.
- Add robustness checks for social dependency sensitivity.
- Keep fallback mode: pure technical scoring only.

## Candidate Features
- Mentions velocity: short-window mentions / long-window mentions.
- Unique account count: de-dup by account per window.
- Sentiment proxy: lightweight polarity model + emoji/keyword heuristics.
- KOL weighted mentions: weighted by curated account trust score.
- Narrative clusters: embedding/topic grouping to detect coordinated themes.

## Integration Modes
1. Universe pre-filter
- Exclude low-liquidity/low-interest symbols unless technical score is very strong.

2. Regime filter
- Strategy active only when social pressure is not in extreme noise state.

3. Score augmentation
- `final_score = technical_score * (1 + alpha * social_score_norm)`
- Keep `alpha` small and bounded to avoid overpowering technical logic.

## Risks
- Bot/spam contamination.
- API limits and data latency.
- Survivorship bias from only available historical social data.
- Regime leakage if delayed timestamps are mishandled.
- Overfit risk if social features are tuned against in-sample performance.

## MVP Plan (Future)
1. Collector MVP
- One source first (Reddit or curated Twitter proxy), hourly snapshots.

2. Feature MVP
- Build 3-5 simple features and snapshot tables.

3. Scorer MVP
- Generate per-symbol social score export CSV/JSON.

4. Pipeline Hook
- Optional selector flag: `--social-score-file`.
- Use as secondary filter/ranking only.

5. Validation
- Compare technical-only vs technical+social in homogeneous setup.
- Apply anti-humo checks (sample, concentration, fee fragility, OOS splits).
