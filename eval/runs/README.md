# Evaluation run summaries

Aggregate results only; per-question records stay local (they contain
PrimeKG-derived content). Most files are kept because older reports link to them.
The ones that matter now:

| File | What it is |
|---|---|
| `v2_test_hybrid_retry3_summary.json` | First accepted v2 test round, graph hybrid (80.8%) |
| `v2_test_vector_retry1_summary.json` | First accepted v2 test round, pure-vector control (32.5%) |
| `v2_comparison_summary.json` | Paired and per-category comparison of the two rounds above |
| `v2_test_hybrid_final_summary.json` | Final v2 test round of the current code (85.0%) |
| `v2_test_*_retry*_rescored_v37_summary.json` | The two first-round runs rescored offline by the final evaluator (unchanged) |
| `next_round_summary.json` | Complete 160-question v2 dev run (87.5%) |
| `usage_log.jsonl` | Token ledger for every provider call (local only) |

Rounds that failed the API-error rule are kept locally under their original names
and never pooled into scores. See [`docs/evaluation.md`](../../docs/evaluation.md).
