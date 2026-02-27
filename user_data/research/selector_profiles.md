# Selector Profiles (`select_pairs.py`)

## Universal (`--profile universal`)
Backwards-compatible generic score:

`score = volume_norm * atr_norm * data_completeness * (1 - wickiness_norm)`

When to use:
- Generic universe building without strategy-family bias.

## Mean Reversion 1h (`--profile mean_reversion_1h`)
Profile aligned to 1h mean reversion behavior, without using strategy PnL history.

Score formula:

`score = w_volume*volume_norm + w_atr_target*atr_target_score + w_cleanliness*(1-wickiness_norm) + w_reversion*reversion_score + w_completeness*data_completeness`

Default weights:
- `w_volume = 0.30`
- `w_atr_target = 0.20`
- `w_cleanliness = 0.20`
- `w_reversion = 0.20`
- `w_completeness = 0.10`

Components:
- `volume_norm`: cross-sectional min-max normalized quote volume.
- `atr_target_score`: gaussian score around ATR target zone (`atr_target`, `atr_sigma`).
- `wickiness_norm`: min-max normalized wickiness (`1 - wickiness_norm` rewards cleaner candles).
- `reversion_score`: proxy of BB-lower oversold events reclaiming BB-mid within `reversion_horizon` candles.
- `data_completeness`: observed candles vs expected candles in lookback window.

Default filters:
- USDT quote only.
- minimum quote volume.
- minimum age days.
- optional stable/fiat base exclusion.
- optional leveraged token suffix exclusion.

Output diagnostics:
- Profile-specific ranking CSV with components and ranks:
  - `user_data/whitelists/pair_ranking.csv` (universal)
  - `user_data/whitelists/pair_ranking_mean_reversion_1h.csv`
