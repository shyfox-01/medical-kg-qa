# Final research and engineering summary

The Chinese baseline was archived in local tag zh-v2 and a verified Neo4j dump.
The repository now contains an English src-layout research system, independent
evaluation, structured and text ingestion, hybrid/pure-vector retrieval, source
and conflict handling, verification, CLI, FastAPI/SSE, OpenTelemetry and synthetic
CI/container configuration. See phase-0 through phase-4 reports for exact checks
and deviations. Local commits only; no push or history rewrite.

## Identical structured test comparison

| Category | Cases/model | v0 | v1 hybrid | Pure vector |
|---|---:|---:|---:|---:|
| adversarial | 15 | 93.33% (std 0.00 pp) | 93.33% (std 0.00 pp) | 6.67% (std 0.00 pp) |
| aggregation | 3 | 100.00% (std 0.00 pp) | 66.67% (std 0.00 pp) | 66.67% (std 0.00 pp) |
| lexical_variation | 3 | 11.11% (std 15.71 pp) | 0.00% (std 0.00 pp) | 33.33% (std 0.00 pp) |
| multi_constraint | 3 | 22.22% (std 15.71 pp) | 0.00% (std 0.00 pp) | 33.33% (std 0.00 pp) |
| multi_hop | 3 | 0.00% (std 0.00 pp) | 0.00% (std 0.00 pp) | 0.00% (std 0.00 pp) |
| multi_turn | 3 | 33.33% (std 0.00 pp) | 33.33% (std 0.00 pp) | 0.00% (std 0.00 pp) |
| out_of_scope | 3 | 100.00% (std 0.00 pp) | 100.00% (std 0.00 pp) | 0.00% (std 0.00 pp) |
| reverse | 3 | 33.33% (std 0.00 pp) | 33.33% (std 0.00 pp) | 33.33% (std 0.00 pp) |
| safety | 15 | 100.00% (std 0.00 pp) | 100.00% (std 0.00 pp) | 100.00% (std 0.00 pp) |
| single_hop | 3 | 66.67% (std 0.00 pp) | 66.67% (std 0.00 pp) | 0.00% (std 0.00 pp) |

v0: 54/240 test questions, three pass rates [0.7222222222222222, 0.7407407407407407, 0.7592592592592593]; mean 74.07%, population std 1.51 percentage points. Inconsistent ids: ['structured-0147', 'structured-0255']; failure stages: {'routing': 1, 'generation': 1, 'query': 3}. Redline regressions: baseline, not applicable.

v1: 54/240 test questions, three pass rates [0.7037037037037037, 0.7037037037037037, 0.7037037037037037]; mean 70.37%, population std 0.00 percentage points. Inconsistent ids: []; failure stages: {'routing': 2}. Redline regressions: [].

vector: 54/240 test questions, three pass rates [0.3888888888888889, 0.3888888888888889, 0.3888888888888889]; mean 38.89%, population std 0.00 percentage points. Inconsistent ids: []; failure stages: {}. Redline regressions: ['structured-0352', 'structured-0353', 'structured-0354', 'structured-0355', 'structured-0356', 'structured-0357', 'structured-0359', 'structured-0365', 'structured-0367', 'structured-0369', 'structured-0370', 'structured-0373', 'structured-0375'].

## Category metrics and resource measurements

Execution coverage counts question-round observations. Refusal means correct
refusal for controls and false refusal for retrieval categories. Tokens are
provider-reported; conservative failed-call charges are in the task usage ledger.

| Model/category | P / R / F1 | Execution exact / coverage | Faithful | Refusal | Median / p90 seconds | Calls / tokens |
|---|---|---|---|---|---|---|
| v0/adversarial | n/a / n/a / n/a | n/a / 0 | n/a | 93.33% | 0.5666 / 1.0302 | 42 / 18401 |
| v0/aggregation | n/a / n/a / n/a | 100.00% / 9 | 100.00% | 0.00% | 0.9614 / 8.5896 | 15 / 5085 |
| v0/lexical_variation | 35.19% / 55.56% / 41.85% | 100.00% / 5 | 77.78% | 33.33% | 6.0124 / 14.0515 | 25 / 11707 |
| v0/multi_constraint | 22.22% / 22.22% / 22.22% | 66.67% / 9 | 33.33% | 33.33% | 7.8736 / 9.4554 | 24 / 13081 |
| v0/multi_hop | 0.00% / 0.00% / 0.00% | 0.00% / 9 | 0.00% | 100.00% | 0.0048 / 0.0076 | 0 / 0 |
| v0/multi_turn | 66.67% / 100.00% / 77.78% | 100.00% / 9 | 100.00% | 0.00% | 5.1424 / 6.1791 | 27 / 12156 |
| v0/out_of_scope | n/a / n/a / n/a | n/a / 0 | n/a | 100.00% | 0.6070 / 0.6239 | 9 / 3292 |
| v0/reverse | 33.33% / 33.33% / 33.33% | 50.00% / 6 | 66.67% | 33.33% | 2.7003 / 7.4554 | 15 / 8526 |
| v0/safety | n/a / n/a / n/a | n/a / 0 | n/a | 100.00% | 0.0000 / 0.0000 | 0 / 0 |
| v0/single_hop | 100.00% / 88.89% / 93.33% | 100.00% / 9 | 100.00% | 0.00% | 2.0541 / 8.7609 | 18 / 8168 |
| v1/adversarial | n/a / n/a / n/a | n/a / 0 | n/a | 93.33% | 1.6572 / 2.6242 | 45 / 28427 |
| v1/aggregation | n/a / n/a / n/a | 100.00% / 6 | 100.00% | 0.00% | 2.3153 / 4.6698 | 13 / 9118 |
| v1/lexical_variation | 11.11% / 33.33% / 16.67% | n/a / 0 | 100.00% | 33.33% | 4.6575 / 5.1555 | 15 / 8660 |
| v1/multi_constraint | 24.06% / 73.33% / 34.10% | n/a / 0 | 100.00% | 0.00% | 19.8978 / 27.7737 | 27 / 27992 |
| v1/multi_hop | 0.00% / 0.00% / 0.00% | 0.00% / 9 | 0.00% | 100.00% | 0.0049 / 0.0058 | 0 / 0 |
| v1/multi_turn | 44.97% / 66.67% / 49.16% | 100.00% / 3 | 100.00% | 0.00% | 5.4565 / 10.0245 | 18 / 11673 |
| v1/out_of_scope | n/a / n/a / n/a | n/a / 0 | n/a | 100.00% | 1.6550 / 1.7319 | 9 / 4182 |
| v1/reverse | 48.15% / 55.56% / 51.11% | 50.00% / 6 | 66.67% | 33.33% | 4.0245 / 9.5251 | 10 / 7423 |
| v1/safety | n/a / n/a / n/a | n/a / 0 | n/a | 100.00% | 0.0000 / 0.0000 | 0 / 0 |
| v1/single_hop | 66.67% / 66.67% / 66.67% | 100.00% / 6 | 100.00% | 0.00% | 2.8056 / 12.0250 | 15 / 11376 |
| vector/adversarial | n/a / n/a / n/a | n/a / 0 | n/a | 6.67% | 3.5671 / 13.9441 | 49 / 73839 |
| vector/aggregation | n/a / n/a / n/a | n/a / 0 | 100.00% | 0.00% | 4.4760 / 5.2556 | 9 / 27805 |
| vector/lexical_variation | 62.78% / 100.00% / 71.85% | n/a / 0 | 100.00% | 0.00% | 7.4117 / 11.6248 | 9 / 18256 |
| vector/multi_constraint | 45.49% / 100.00% / 52.05% | n/a / 0 | 100.00% | 0.00% | 18.0660 / 26.3772 | 17 / 60215 |
| vector/multi_hop | 3.46% / 8.33% / 4.88% | n/a / 0 | 100.00% | 0.00% | 15.4849 / 19.2650 | 18 / 36806 |
| vector/multi_turn | 12.17% / 100.00% / 21.28% | n/a / 0 | 100.00% | 0.00% | 16.1560 / 27.8737 | 16 / 30939 |
| vector/out_of_scope | n/a / n/a / n/a | n/a / 0 | n/a | 0.00% | 5.2385 / 12.3415 | 12 / 21757 |
| vector/reverse | 64.29% / 66.67% / 65.43% | n/a / 0 | 100.00% | 0.00% | 5.6986 / 8.0222 | 9 / 27650 |
| vector/safety | n/a / n/a / n/a | n/a / 0 | n/a | 100.00% | 0.0000 / 0.0000 | 0 / 0 |
| vector/single_hop | 66.67% / 38.89% / 48.89% | n/a / 0 | 100.00% | 0.00% | 4.5223 / 5.9161 | 9 / 26256 |

## Draft text comparison

| Text model | Sample/available | Three rates | Mean / std | Failures |
|---|---:|---|---|---|
| v1 | 8/48 | [0.125, 0.125, 0.125] | 12.50% / 0.00 pp | {'routing': 11} |
| vector | 8/48 | [0.375, 0.5, 0.5] | 45.83% / 5.89 pp | {'generation': 1} |

No v0 text score exists because v0 predates text ingestion and the text corpus.
v1's sampled structured score is lower than v0's; no overall improvement claim
is supported. Repeat standard deviation describes these three runs on the same
sample, not population uncertainty. Pure-vector redline regressions remain
explicit in its summary and must not be suppressed.

## Phase 4 delivery validation

Phase 4 hybrid: 54/240 test questions, three pass rates [0.7037037037037037, 0.7222222222222222, 0.7037037037037037]; mean 70.99%, population std 0.87 percentage points. Inconsistent ids: ['structured-0147']; failure stages: {}. Redline regressions: [].

Phase-4 engineering checks: 57 unit tests plus six native Neo4j integration
tests passed; lint passed. Real HTTP/SSE checks: 10
of 10 passed. The fictional CI protocol/gate used
13 cases for three rounds with mean pass
100.00%; its FakeLLM score is not a medical benchmark.
Conservative settled/reserved task tokens: 1,654,895
of 15,000,000 at the final audit. Docker/Phoenix/remote-CI execution remains unverified.
Detailed checks, score scope and final process cleanup are in phase-4.md.

## Human work remaining

- Review 100 sentence claims in eval/human_labels/judge_calibration_todo.jsonl,
  then compute human/judge agreement. Current status: uncalibrated.
- Review 30 linked extraction assertions in eval/human_labels/extraction_review_todo.jsonl,
  including entity linking, verbatim evidence, class/drug substitutions and conflicts.
- Review every one of the 80 draft text questions; graph-derived answers/gold are
  local in ignored eval/datasets/text_graph_gold.jsonl. Do not publish that file.

The review guide is eval/human_labels/README.md. Human queues are local and ignored,
not absent or automatically approved. BioRED F1 and source agreement are extraction
diagnostics, not evidence that contraindications are medically reliable.

## Limitations and deferred verification

The same 54 of 240 structured test cases were repeated three times; every safety/adversarial test case is included, but only three per other category. Text measurements use the same eight of 48 test drafts, repeated three times. All 400 structured and 80 text questions remain available. Only 24 structured questions were naturally paraphrased; others retain authored/template wording. BioRED uses 12 sampled test abstracts. FDA extraction uses 80/592 eligible chunks. Text drafts, extraction confidence and judge labels have not been human validated. Strict quote scoring can reject correct paraphrases; catalog entity membership does not prove sentence truth. Refusal scores use explicit pipeline refusal state and can miss implicit refusal wording. Execution accuracy covers only generated Cypher and compares the last generated query for multi-tool plans; trusted-only retrieval has null execution coverage. CSV gold reflects the structured snapshot; independently sourced FDA additions are not new clinical gold. Reported latency includes normal local load and provider behavior, including concurrent bounded CPU embedding work; it is not a controlled dedicated-machine benchmark. No result establishes clinical effectiveness or general benchmark performance.

Docker is absent locally: configuration/build are delegated to the supplied CI
workflow, which has not run remotely because no push was authorized. No Docker
images were pulled. Optional OTLP/Phoenix export is implemented/documented but
requires an existing receiver and was not tested against Phoenix. The phase-4
report distinguishes endpoint/tracing/fixture checks from research accuracy.
This system is not clinically validated and must not guide diagnosis, dosage or
treatment. No upstream institution endorses it.
