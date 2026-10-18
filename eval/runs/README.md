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
| `llm_compare_dev_glm_summary.json` | Full v2 dev, current code, cloud glm-4.5-flash (92.5%) |
| `llm_compare_dev_local_summary.json` | Full v2 dev, same code, local qwen3.5:9b via Ollama (77.5%) |
| `llm_compare_dev_glm47_local_summary.json` | Full v2 dev, same code, local open-weight GLM-4.7-Flash via Ollama (82.5%) |
| `llm_compare_dev_gemma4_local_summary.json` | Full v2 dev, D083 code, local Gemma 4 26B-A4B (79.4%) |
| `d085_dev_*_summary.json` | Full v2 dev after D085 (explicit evidence): cloud 91.3%, Gemma 4 87.5%, GLM-4.7 84.4% |
| `d086_dev_*_summary.json`, `d088_dev_gemma4_local_summary.json` | Dev after D086 and after D087/D088 (intermediate) |
| `r3_dev_glm45_cloud_summary.json`, `r3_dev_gemma4_local_summary.json` | Dev on the final round-3 code, scorer 3.8: cloud 96.3%, Gemma 4 96.9% |
| `v3_test_glm45_cloud_summary.json`, `v3_test_gemma4_local_summary.json` | Sealed v3 test, once per system: cloud 247/260, local 246/260 in scope |
| `v3_b1_*`, `v3_b2_*` | v3 diagnosis batches: first looks and post-fix runs (Gemma 4) |
| `r5_dev_gemma4_local_summary.json` | v2 dev regression check after the v3 fixes (159/160) |
| `*_rescored_v38_summary.json` | Saved outputs rescored by scorer 3.8 (no model calls): v2 test final 87.1%, first 82.1%, vector 33.3% |
| `usage_log.jsonl` | Token ledger for every provider call (local only) |

Rounds that failed the API-error rule are kept locally under their original names
and never pooled into scores. See [`docs/evaluation.md`](../../docs/evaluation.md).
