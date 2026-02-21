# Calibration Scorecard

## Buckets
- good: 8
- bad: 8
- low_sample: 15
- mixed: 14

## Heuristic Classification Quality
- Good marked ROBUST_CANDIDATE: 8/8
- Bad marked severe flags: 8/8
- False positives (bad but robust): 0
- False negatives (good not robust): 0

## Robustness Score Distribution
- good avg: 98.75
- bad avg: 75.0
- low_sample avg: 51.46666666666667

## Thresholds Used
- min_trades_for_confidence: 80
- low_sample_trades: 20
- baseline_candidate_min_pf: 1.05
- baseline_candidate_max_dd: 1.5

## Suggested Adjustments
- If many good candidates are not marked robust, lower `robust_candidate_min_score` slightly.
- If many bad candidates pass robust, tighten concentration and cost fragility thresholds.
- If low-sample dominates, raise sample generation priority before new ideas.
