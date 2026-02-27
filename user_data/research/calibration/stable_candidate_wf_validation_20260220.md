# Stable Candidate WF Validation (v3c 1h)

- generated_at: 2026-02-20T18:37:11.693821Z
- config: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/configs/config.bt_spot_1h_top15_mr1h_stable_candidate.json`
- coverage_report: `/Users/carlaherrera/Desktop/codex/freqtrade/user_data/research/calibration/top15_mr1h_stable_candidate_coverage_report_20260220.json`

## WF Summary
- baseline_top15: splits=12, trades_total=106, pf_avg=2.5179, pf_median=1.4790, splits_pf_gt_1=8, worst_dd=0.2460, top1_avg=44.24%, top3_avg=87.32%
- stable_candidate: splits=12, trades_total=74, pf_avg=4.6474, pf_median=2.5887, splits_pf_gt_1=8, worst_dd=0.2110, top1_avg=44.24%, top3_avg=87.32%

## Fee (Stable Candidate)
- base: trades=20, profit%=0.2736, pf=2.1250, maxDD%=0.2110, delta_pf=0.0000
- p25: trades=20, profit%=0.2543, pf=1.9855, maxDD%=0.2229, delta_pf=-0.1396
- p50: trades=20, profit%=0.1363, pf=1.4946, maxDD%=0.2348, delta_pf=-0.6304

## Anti-smoke
- sanity: score=100.0, flags=[], lookahead=None, recursive=None
- wf_b: score=58.0, flags=['TOO_CONCENTRATED_TOP3', 'PAIR_DEPENDENCY_RISK', 'LOW_SAMPLE'], lookahead=None, recursive=None
- wf_d: score=70.0, flags=['PAIR_DEPENDENCY_RISK', 'LOW_SAMPLE'], lookahead=None, recursive=None