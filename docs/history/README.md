# Project history

Process reports in the order the work happened. They are kept as written at the
time (scores use the evaluator version of that date) and are not needed to use the
project; start with the [README](../../README.md) and [evaluation](../evaluation.md).

| Date | Report | What happened |
|---|---|---|
| 2026-10-05 | [Phase 0](reports/phase-0.md) | Chinese prototype archived (tag `zh-v2`); English rewrite starts |
| 2026-10-05 | [Phase 1](reports/phase-1.md) | PrimeKG loaded into Neo4j; guarded Text2Cypher baseline |
| 2026-10-05 | [Phase 2](reports/phase-2.md) | Black-box evaluator and frozen v1 benchmark |
| 2026-10-05 | [Phase 3](reports/phase-3.md) | MedlinePlus/openFDA text, hybrid retrieval, pure-vector control |
| 2026-10-05 | [Phase 4](reports/phase-4.md) | FastAPI/SSE service, OpenTelemetry, CI configuration |
| 2026-10-05 | [Summary](reports/summary.md) | Running summary, appended after each later round |
| 2026-10-05 | [Review](reports/review-2026-10-05.md), [fix](reports/fix-2026-10-05.md), [second review](reports/review-2-2026-10-05.md) | First implementation reviews and repairs |
| 2026-10-06 | [Follow-up](reports/followup-2026-10-06.md), [improvement](reports/improvement-2026-10-06.md) | Routing/planning fixes; full 240-case v1 comparison |
| 2026-10-07 | Decisions D047–D050 | Code review fixes, same-name Disease/Phenotype routing, MeSH aliases, benchmark v2 |
| 2026-10-08 | [v2 results](reports/v2-results.md) | First accepted v2 test round: hybrid 80.8%, pure vector 32.5% |
| 2026-10-08 | [T5 improvements](reports/t5-improvements.md), [next round](reports/next-round-2026-10-08.md) | Source aliases, refusal narrowing, typo matching; full dev run 87.5% |
| 2026-10-09 | [AI source review](reports/ai-review-2026-10-09.md) | Multi-agent review of 100 aliases and evaluation method |
| 2026-10-15 | [Review implementation](reports/review-implementation-2026-10-15.md), [independent review](reports/independent-review-2026-10-15.md) | Alias quarantine, stricter scoring diagnostics, blind-review tooling |
| 2026-10-15 | [Integration](reports/integration-2026-10-15.md) | 19 integration tests; live CLI/HTTP/SSE smoke |

[overview_table.md](reports/overview_table.md) is an early generated table kept for
links from older reports.
