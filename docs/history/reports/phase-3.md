# Phase 3 — Text, hybrid retrieval and independent vector control

Imported all 1017 English MedlinePlus summaries and
247 linked FDA labels in 4693 chunks.
openFDA used exactly 500 requests: 382
returned labels, 126 unlinked and
30 ambiguous matches; document deduplication
and successful linking yield the stated final coverage. The initial 17 unusable
queries remain charged. No source outside the authorized list was downloaded.

Added section chunking, cached 384-dimensional embeddings, ABOUT/MENTIONS,
source-filtered top-eight vectors, English fulltext and bounded two-hop expansion,
validated four-step plans/backward references and known-entity answer verification.
FDA added 782 new aliases; previous alias vectors were reused. The independent
pure-vector corpus has 47668 fully embedded records: 42,975 entity
paragraphs plus 4,693 text chunks. Full paragraph text is stored; embedding uses
the model's 512-token window and generation uses disclosed evidence limits.

BioRED entity-pair detection F1: 0.3467; native typed
relation F1: 0.1067; 1 failed
call. Its Chemical–Disease relations are not contraindication gold. The mapping
and non-mappings are recorded in decisions D011.

FDA extraction produced 45 unique linked assertions:
{'INTERACTS_WITH': 39, 'CONTRAINDICATED_FOR': 6}; recorded PrimeKG agreement 75.56%,
1 conflict, both sources retained. 9
sampled chunks retain failed extraction/parse outcomes. The initial pass had 30
failures; bounded recovery/final sampling is in D017. The unlinked-mention audit
contains 273 entries including diagnostic/recovery
calls, not unique entities. Random 30-assertion review is generated locally.

## Structured measurements

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

## Text measurements and pending calibration

| Text model | Sample/available | Three rates | Mean / std | Failures |
|---|---:|---|---|---|
| v1 | 8/48 | [0.125, 0.125, 0.125] | 12.50% / 0.00 pp | {'routing': 11} |
| vector | 8/48 | [0.375, 0.5, 0.5] | 45.83% / 5.89 pp | {'generation': 1} |

All 80 questions are draft (40 text-only / 40 mixed; 32 dev / 48 test).
Grounding-checked LLM drafts: 19; others use
declared fallbacks. Seven structurally invalid selections were repaired before
text testing, preserving ids/splits. No questions were removed based on test score.
The 100-item sentence queue covers 56 questions:
32 actual system claims and 68 draft claims,
with 100 uncalibrated judge labels and zero human labels.
The annotation guide explains sentence sampling and blind human review.

## Checks, limitations and deviations

51 mechanism/evaluation unit checks and both real-data count/access integration
checks pass. Preparatory fictional retrieval checks also pass after streaming
expansion avoided a global-neighborhood-sort timeout. Lint passes. Provider HTTP
429 during concurrent preliminary runs led to process-shared serialized calls;
interrupted preliminary runs are excluded from completed metrics but remain in
the local usage ledger. The token cap remains enforced. All raw/derived details,
private graph gold and human queues are ignored by Git; public text drafts and
aggregate summaries are committed. No push.

The same 54 of 240 structured test cases were repeated three times; every safety/adversarial test case is included, but only three per other category. Text measurements use the same eight of 48 test drafts, repeated three times. All 400 structured and 80 text questions remain available. Only 24 structured questions were naturally paraphrased; others retain authored/template wording. BioRED uses 12 sampled test abstracts. FDA extraction uses 80/592 eligible chunks. Text drafts, extraction confidence and judge labels have not been human validated. Strict quote scoring can reject correct paraphrases; catalog entity membership does not prove sentence truth. Refusal scores use explicit pipeline refusal state and can miss implicit refusal wording. Execution accuracy covers only generated Cypher and compares the last generated query for multi-tool plans; trusted-only retrieval has null execution coverage. CSV gold reflects the structured snapshot; independently sourced FDA additions are not new clinical gold. Reported latency includes normal local load and provider behavior, including concurrent bounded CPU embedding work; it is not a controlled dedicated-machine benchmark. No result establishes clinical effectiveness or general benchmark performance.

v1 does **not** improve the overall structured sampled score over v0. The added
mechanisms are implemented and measured; this run does not justify claiming
that hybrid retrieval improves overall answer accuracy. The vector control's
redline outcomes are a diagnostic, not a deployable fallback approval.
