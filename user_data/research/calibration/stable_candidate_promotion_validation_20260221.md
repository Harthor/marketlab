# Stable Candidate Promotion Validation (2026-02-21)

## Final Recommendation
- promote confirmed

## Sanity Comparison
| universe | pairs effective | trades | trades/day | profit% | winrate% | PF | maxDD% |
|---|---:|---:|---:|---:|---:|---:|---:|
| top15_mr1h_stable_candidate | 13 | 20 | 0.05 | 0.2736 | 50.00 | 2.1250 | 0.2110 |
| top15_mr1h_effective (benchmark) | 15 | 27 | 0.07 | 0.1832 | 37.04 | 1.5491 | 0.2460 |

## WF Summary (Stable Candidate)
- splits: 15 | trades_total: 90 | pf_avg: 5.6286 | pf_median: 3.4404 | splits_pf>1: 11 | worst_dd: 0.2110

## LOPO (Top Impacts by Delta PF)
| pair_removed | delta PF vs stable baseline | delta profit% | delta DD pp |
|---|---:|---:|---:|
| ETH/USDT | 0.7198 | 0.0391 | -0.0737 |
| AAVE/USDT | 0.1675 | -0.0158 | -0.0438 |
| PAXG/USDT | 0.1290 | 0.0064 | -0.0199 |
| XRP/USDT | 0.0998 | 0.0109 | 0.0000 |
| OP/USDT | 0.0847 | -0.0236 | -0.0365 |
| ARB/USDT | -0.4934 | -0.1200 | 0.0000 |
| BNB/USDT | -0.2057 | -0.0500 | 0.0000 |
| SOL/USDT | -0.1243 | -0.0451 | -0.0148 |
| SNX/USDT | -0.0669 | -0.0388 | 0.0000 |
| BCH/USDT | -0.0527 | -0.0367 | -0.0223 |

## Fee Sensitivity
| scenario | trades | profit% | winrate% | PF | maxDD% | delta PF vs base |
|---|---:|---:|---:|---:|---:|---:|
| base | 20 | 0.2736 | 50.00 | 2.1250 | 0.2110 | 0.0000 |
| p25 | 20 | 0.2543 | 50.00 | 1.9855 | 0.2229 | -0.1396 |
| p50 | 20 | 0.1363 | 45.00 | 1.4946 | 0.2348 | -0.6304 |
| p75 | 20 | 0.1141 | 45.00 | 1.3905 | 0.2467 | -0.7345 |
| p100 | 20 | 0.0918 | 45.00 | 1.2975 | 0.2586 | -0.8275 |

- PF breakpoint: not_reached_up_to_+100%
