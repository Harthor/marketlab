# KOL Scheduler Dry-Run

- run_id: 20260221T133608Z
- created_at_utc: 2026-02-21T13:36:08+00:00
- queue_path: /Users/carlaherrera/Desktop/codex/freqtrade/user_data/research/social/pipeline_run_20260221T133608Z/kol_dryrun_queue.sample.json
- rows_in: 12
- rows_out: 12
- executed_count: 2
- budget_used_estimated: 0.13819998
- skipped_by_reason: {'skipped_cooldown': 10}

| queue_id | token | kol | action | status | est_cost | reason |
|---|---|---|---|---|---:|---|
| 5b78233dbe66a5f4 | SOL | sol_researcher | quote_kol | executed_mock | 0.069100 |  |
| dd7fc1225a574441 | ARB | sol_researcher | quote_kol | skipped_cooldown | 0.069100 | kol_cooldown |
| bf753b3f10b9b8fb | SOL | arb_insights | quote_kol | skipped_cooldown | 0.069100 | token_cooldown |
| 35a0b2091a8b31fb | ARB | arb_insights | quote_kol | executed_mock | 0.069100 |  |
| 3b29f29e9877c9af | SOL | btc_macro_view | ask_question | skipped_cooldown | 0.023033 | token_cooldown |
| 02d620eccddc72b8 | ARB | btc_macro_view | ask_question | skipped_cooldown | 0.023033 | token_cooldown |
| 86f281e9763ba43e | SOL | multi_chain_flow | reply_to_kol | skipped_cooldown | 0.046067 | token_cooldown |
| 9aba1f36089b571a | ARB | multi_chain_flow | reply_to_kol | skipped_cooldown | 0.046067 | token_cooldown |
| 278ae2f706e81d90 | SOL | latam_crypto_radar | ask_question | skipped_cooldown | 0.023033 | token_cooldown |
| 8c4cfc851264612f | ARB | latam_crypto_radar | ask_question | skipped_cooldown | 0.023033 | token_cooldown |
| 644933fb48f0c206 | SOL | meme_buzz | reply_to_kol | skipped_cooldown | 0.046067 | token_cooldown |
| b940b665fc439c04 | ARB | meme_buzz | reply_to_kol | skipped_cooldown | 0.046067 | token_cooldown |
