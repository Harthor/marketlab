# KOL Scheduler Dry-Run

- run_id: 20260221T174656Z
- created_at_utc: 2026-02-21T17:46:56+00:00
- queue_path: /Users/carlaherrera/Desktop/codex/freqtrade/user_data/research/social/pipeline_run_20260221T174655Z/kol_dryrun_queue.sample.json
- rows_in: 12
- rows_out: 12
- executed_count: 2
- budget_used_estimated: 0.47560002
- skipped_by_reason: {'skipped_cooldown': 10}

| queue_id | token | kol | action | status | est_cost | reason |
|---|---|---|---|---|---:|---|
| 84575a87f7314f7e | SOL | sol_researcher | quote_kol | executed_mock | 0.237800 |  |
| 66d606493a71f6c2 | ARB | sol_researcher | quote_kol | skipped_cooldown | 0.237800 | kol_cooldown |
| 88719106b1685f7d | SOL | arb_insights | quote_kol | skipped_cooldown | 0.237800 | token_cooldown |
| 3432900bb4c73278 | ARB | arb_insights | quote_kol | executed_mock | 0.237800 |  |
| e4915152d8c942db | SOL | btc_macro_view | ask_question | skipped_cooldown | 0.079267 | token_cooldown |
| 45fa566079709886 | ARB | btc_macro_view | ask_question | skipped_cooldown | 0.079267 | token_cooldown |
| ddc7b8028c2b1696 | SOL | multi_chain_flow | reply_to_kol | skipped_cooldown | 0.158533 | token_cooldown |
| bd72cb69f5cc2395 | ARB | multi_chain_flow | reply_to_kol | skipped_cooldown | 0.158533 | token_cooldown |
| f87bc4944e92bea0 | SOL | latam_crypto_radar | ask_question | skipped_cooldown | 0.079267 | token_cooldown |
| 03d3a976a0abf2c2 | ARB | latam_crypto_radar | ask_question | skipped_cooldown | 0.079267 | token_cooldown |
| 516b1aead8640ef5 | SOL | meme_buzz | reply_to_kol | skipped_cooldown | 0.158533 | token_cooldown |
| fea157cac7875f63 | ARB | meme_buzz | reply_to_kol | skipped_cooldown | 0.158533 | token_cooldown |
