# Phase 2 — Independent evaluation and v0 baseline

Generated and froze 400 questions from the authorized CSV and ontology snapshots; stratified seed-42 split: 160 dev / 240 test. All 320 graph gold queries were independently checked against Neo4j and matched the CSV-computed uid/count sets. Added independent normalization, entity-set precision/recall/F1, exact counts, evidence faithfulness, refusal and safety checks, injection checks, execution-result comparison, latency/cost, trace-linked failures and redline comparison. Evaluation calls the public CLI/stdio protocol and never imports QA internals.

| Category | Tested questions | Mean pass rate | Std | Execution coverage (3 rounds) |
|---|---:|---:|---:|---:|
| adversarial | 15 | 0.9333 | 0.0000 | 0 |
| aggregation | 3 | 1.0000 | 0.0000 | 9 |
| lexical_variation | 3 | 0.1111 | 0.1571 | 5 |
| multi_constraint | 3 | 0.2222 | 0.1571 | 9 |
| multi_hop | 3 | 0.0000 | 0.0000 | 9 |
| multi_turn | 3 | 0.3333 | 0.0000 | 9 |
| out_of_scope | 3 | 1.0000 | 0.0000 | 0 |
| reverse | 3 | 0.3333 | 0.0000 | 6 |
| safety | 15 | 1.0000 | 0.0000 | 0 |
| single_hop | 3 | 0.6667 | 0.0000 | 9 |

Overall sampled test pass rates: [0.7222222222222222, 0.7407407407407407, 0.7592592592592593]; mean 0.740741, population std 0.015120. Coverage: 54/240 test cases, repeated three times. All 15 safety and all 15 adversarial test cases are included. Inconsistent ids: ['structured-0147', 'structured-0255']. Failure stages: {'routing': 1, 'generation': 1, 'query': 3}.

Validation: 45 unit tests pass; phase-1 database count/access tests already passed. Metrics are in `eval/runs/v0_summary.json`; raw per-question data is ignored. Judge scores remain uncalibrated; text drafts and human queues are generated in phase 3.

Known issues/deviations: provider timeouts and long list generation led to the task-authorized seeded cap of three per non-redline category. Only 24 natural paraphrases were sampled and entity-presence validated; 376 items retain authored/template wording. These limitations are explicit in MANIFEST and decisions D009; no full-corpus or clinical performance claim is made. A subprocess stderr pipe initially blocked the dev runner; redirected child logs prevent deadlock. Optional properties can trigger non-fatal Neo4j warnings. On Windows all file text reads use explicit UTF-8. No push.
