# Strategy Spec Template

## Metadata
- id: `stratXX_name_v1`
- family: `mean_reversion|trend|breakout|volatility|hybrid`
- owner: `research`
- status: `draft`

## Hypothesis
- Why this should have edge in this market regime.

## Market Regime Target
- Primary regime:
- Regime filters:

## Timeframe Objective
- Primary timeframe:
- Informative timeframe(s):

## Universe Assumptions
- Universe source/profile:
- Universe constraints:

## Indicators
- Core indicators:
- Derived features:

## Entry Rules (Exact)
1.
2.

## Exit Rules (Exact)
1.
2.

## Stop / Risk Rules
- Hard stop:
- Dynamic stop:
- Position/risk constraints:

## What Could Break It
- Failure modes:
- Structural market changes:

## Freqtrade Implementation Notes
- Interface/callbacks:
- Data dependencies:
- Startup candles:

## Anti-Lookahead Notes
- Confirm no forward references.
- Confirm no future candle leakage in features.

## Validation Plan
- Sanity setup:
- Walk-forward plan:
- Fee sensitivity plan:
