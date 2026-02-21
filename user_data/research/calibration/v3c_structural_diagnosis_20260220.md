# v3c 1h Structural Diagnosis (top15 vs top20)

## Stable Candidate Rule
- remove_if: `contribution_total_profit_pct < -0.05 and positive_split_ratio_pct < 35 and LOPO delta_pf_vs_baseline > +0.12`
- fill_rule: `pos_ratio >= 45, ranked by contribution then pos_ratio`
- removed: `BTC/USDT, TRX/USDT'
- candidate_pairs (13): `ETH/USDT, XRP/USDT, SOL/USDT, BNB/USDT, PAXG/USDT, ARB/USDT, AAVE/USDT, LTC/USDT, UNI/USDT, SNX/USDT, OP/USDT, ADA/USDT, BCH/USDT`

## WF Comparison (Common splits)
- common_splits: `WF_A_TEST, WF_B_TEST, WF_C_TEST, WF_D_TEST, WF_E_TEST, WF_F_TEST, WF_G_TEST, WF_H_TEST, WF_I_TEST, WF_J_TEST, WF_K_TEST, WF_L_TEST`
- top15 summary: `{'splits_count': 12, 'trades_total_wf': 106, 'pf_avg': 2.5178560469359783, 'pf_median': 1.479029227486989, 'splits_pf_gt_1': 8, 'worst_maxdd_pct': 0.24595993499999624, 'top1_share_avg_pct': 52.57637564321158, 'top1_share_worst_pct': 100.0, 'top3_share_avg_pct': 95.6504448172572, 'top3_share_worst_pct': 100.0}`
- top20 summary: `{'splits_count': 12, 'trades_total_wf': 125, 'pf_avg': 1.3205048726682356, 'pf_median': 1.4632077134451191, 'splits_pf_gt_1': 7, 'worst_maxdd_pct': 0.3585956549999992, 'top1_share_avg_pct': 50.46659123529438, 'top1_share_worst_pct': 100.0, 'top3_share_avg_pct': 93.59342363132534, 'top3_share_worst_pct': 100.0}`

## Drivers (top5 by contribution)
- ARB/USDT: contrib=0.6700, trades=13, pos_split%=46.7
- SNX/USDT: contrib=0.4000, trades=12, pos_split%=53.3
- AAVE/USDT: contrib=0.3600, trades=11, pos_split%=53.3
- SOL/USDT: contrib=0.2100, trades=14, pos_split%=33.3
- BNB/USDT: contrib=0.2000, trades=4, pos_split%=26.7

## Laggards (bottom5 by contribution)
- PAXG/USDT: contrib=-0.0200, trades=10, pos_split%=20.0
- XRP/USDT: contrib=-0.1000, trades=9, pos_split%=0.0
- BTC/USDT: contrib=-0.2400, trades=16, pos_split%=0.0
- OP/USDT: contrib=-0.2400, trades=11, pos_split%=13.3
- TRX/USDT: contrib=-0.3700, trades=30, pos_split%=0.0
