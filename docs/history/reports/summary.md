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

## Subsequent local work

The numbers above are the original phase-delivery snapshots. Later correctness
repairs and the 38-case pilot are documented in
[the ordered follow-up](followup-2026-10-06.md). Subsequent capability changes,
final engineering verification and the bounded frozen 240-case comparison are
documented in [the implementation report](improvement-2026-10-06.md). Preserve
these scopes and evaluator versions when comparing results. The additional
18 quarantined assertions also await human review. The updated human review guide
provides blind copies, validated imports and calibration auditing; it supplies no
human decisions.

## Completed capability comparison and maintenance — 2026-10-06 to 2026-10-07

The [capability implementation report](improvement-2026-10-06.md) now distinguishes
the complete 240-case single-round comparison (before 58.75%, improved 85.83%,
vector 52.92%) from 70 fixed questions in three rounds (71.90%, 90.95%, 73.81%).
The initial hybrid timeout and vector refusal regressions remain archived.
Post-measurement native mutex and scope changes pass 213 unit tests, 15 native
integration tests, fictional CI and three fresh hybrid redline rounds. Vector
still has one refusal regression. Human labels and deployment validation remain
pending; the report records provenance, budgets, packaging and owned-process cleanup.

## Code review fixes and offline rescoring — 2026-10-07

A code review fixed safety false positives, relation-blind expansion, common-word
alias links, pronoun substitution, the contraindication route, silent evidence
truncation, the runtime token cap and count scoring (decision D047; 60 new
fictional regression tests, 273 unit tests pass). Saved answers from the comparison
above were rescored offline with `deterministic-3.4` (zero model calls): 240 cases
60.00% / 87.50% / 56.67% and 70 cases over three rounds 73.33% / 92.38% / 75.24%
(before / improved / vector). Only aggregation changed, because the previous parser
rejected correct "Count: N" answers that also contained other numbers. The rescored
answers predate the D047 code fixes; measuring those requires a new real-provider run.

## Frozen v2 comparison — 2026-10-08

The [v2 results report](v2-results.md) supersedes earlier measurements as the current
benchmark snapshot. The vector control was rebuilt with up to 20 catalog synonyms
per entity, prioritizing retained MeSH additions. Both systems then completed all
240 frozen v2 test cases once in accepted rounds with `deterministic-3.5`, a shared
60-second provider timeout, two-second cooldown, zero SDK retries and cache off.
No QA code or prompt was changed using test answers.

| Scope | Questions | Hybrid | Pure vector |
|---|---:|---:|---:|
| All frozen test cases | 240 | 194/240 (80.83%) | 78/240 (32.50%) |
| Same cases with no API error in either system | 233 | 194/233 (83.26%) | 76/233 (32.62%) |

Hybrid has one timeout and six rate-limit questions, plus ten planning validation
and seven query-syntax failure questions. Vector has no execution-error questions.
Hybrid passes all 15 safety and 15 adversarial controls; vector passes 15/15 and
14/15, with a regression on `v2-0373`. Lexical variation is 17/36 versus 0/36;
sensitive-term false refusal is 1/12 for both systems. These failures remain visible.

Median/p90 pipeline latency is 12.76/41.97 seconds for hybrid and 11.02/41.11 for
vector, summed across conversation turns. Accepted runs report 569,477 and
1,251,629 provider tokens. Including the dev smoke and four API-invalid attempts,
the task uses 3,356,704 provider-reported tokens and 4,404,356 conservative ledger
tokens under the user-approved 6,000,000 total additional allowance. Invalid full
runs and stopped prefixes stay local; no individual failed case was selectively
rerun. The runtime timeout amendment and all deviations are recorded in D051-D059.

All nine artifact checks and Ruff pass; 307 unit tests pass, while 15 integration
tests remain deselected. Frozen inputs and all seven human-review queues are
unchanged. No clinical validation, new data download, dependency installation,
push or merge occurred. Owned evaluators and Neo4j are stopped, with ports
7474/7687 closed. Work stops at T5: alias coverage, special-population false
refusals, planner-format tolerance and free-provider availability await the user.
V1 and v2 have different cases/scoring; their headline scores are not a matched
before/after experiment. The report provides the subgroup denominators and limits.

## Authorized T5 continuation — 2026-10-08

After the user's instruction to continue, implemented cached-source alias
enrichment, narrower population refusals, bounded planner boolean normalization
and cross-process provider backoff. Added 94 aliases to 80 entities and verified
them in Neo4j; refreshed 75 vector paragraphs while preserving the other 47,593
vectors exactly. No new source data was downloaded. Frozen datasets and all seven
human queues remain unchanged. Details and current fingerprints are in the
[T5 implementation report](t5-improvements.md), with decisions D060-D064.

The same 38 dev cases yield 35 passes (92.11%), including all 20 safety/adversarial
controls. Two API timeouts and one unsupported typo answer remain; there are no
other execution-error questions. This is development evidence only, with no new
test or vector performance claim. The preceding test table remains the historical
pre-improvement snapshot. The new smoke charges 61,607 conservative tokens, bringing
additional task usage to 4,465,963 of the approved 6,000,000 allowance.

Ruff, 361 non-integration tests and all nine artifact checks pass. The 15 integration
tests remain deselected; separate read-only graph checks verify synchronization.
All changes are local commits on `review-fixes-2026-10-07`, without push or merge.
Owned evaluators and Neo4j are stopped, and ports 7474/7687 are closed.

## Complete follow-up dev check and independent authoring preparation — 2026-10-08

The [follow-up report](next-round-2026-10-08.md) records the user's four authorized
items: bounded drug spelling corrections, a historical alias audit, isolated
integration plus all-dev verification, and preparation of an independent evaluation.
All ten dev typo questions now pass. The complete hybrid dev run passes 140/160
(87.50%); excluding five API-timeout questions gives 140/155 (90.32%). Six query
syntax errors and nine other answer-score failures remain. Both safety/adversarial
groups pass all ten cases each; sensitive-term false refusals are 0/8, with 7/8
answer passes. Source remains frozen during the run, and no failed case is rerun.
There is no new test or vector result.

All 15 integration tests pass: 14 on an isolated fixture database and one read-only
CSV-count check on the research graph. Ruff, 412 non-integration tests and nine
artifact checks pass. The audit flags 2,389 entity/alias pairs without deleting
aliases; the first 100 await human review. The independent packet contains 100
blank human-authored slots, a source manifest, readable tables and an offline
readiness gate. No human labels are assigned. Both frozen datasets, the catalog,
vector artifacts and seven original human queues retain their prior hashes.

The dev run uses 353,298 reported / 391,504 conservative tokens over 243 calls.
Cumulative additional task usage is 4,857,467 of the approved 6,000,000 allowance,
leaving 1,142,533. The run lasts 2,912.17 seconds; no new reservation is unsettled.
Owned evaluators and both task-started Neo4j instances have exited, and ports
7474/7687 are closed. Changes remain local on the specified branch, without push,
merge, downloads or installations. Human review/authoring is the next required
input under task section 4; a new independent performance claim remains pending.

## User-authorized multi-agent source review — 2026-10-09

The user subsequently requests AI reviewers because they lack domain expertise.
The [multi-agent report](ai-review-2026-10-09.md) records a distinct AI review lane,
preserving every human queue and its original labels. Two fresh-context reviewers
agree on 6 supported, 28 unsupported and 66 uncertain mappings among the first
100 priority alias pairs (nine entities). Their relation classifications differ
on two pairs. All 780 quoted evidence occurrences resolve to the stated cached
MeSH locations; agreement and quote integrity do not establish medical accuracy.
Searching 483 cached openFDA files does not resolve the remaining 66 pairs under
the declared exact-identity rule. No alias is applied or deleted.

A third agent reviews evaluation methodology and authors 12 text-only questions
from cached MedlinePlus documents. A subsequent answer-blind audit finds all 12
reference answers source-supported and complete for their questions, with six
optional wording/grading clarifications and no required factual corrections.
All 23 author spans, 24 supplied full-source chunks and 60 auditor quote occurrences
are checked. These are AI-authored and AI-reviewed pilot artifacts, not human gold
or QA-system outputs; the original 100 human-authoring slots remain untouched.

Seven methodology recommendations include substantive safety-content review, exact
gold reconstruction, subtype coverage, answer blinding, semantic claim evaluation
and fuller preregistration. Synthetic scorer inputs expose missed contradictions,
incomplete mixed graph coverage and inappropriate safety content passing the
current diagnostics. No such response is claimed as an observed runtime output.
No QA/scoring changes or new benchmark runs occur. The GLM ledger remains unchanged
at 10,201,771 cumulative conservative tokens; Codex agent work is separate AI usage.
The report links both completed review tables, raw evidence and aggregate checks.

## Implementation of review findings — 2026-10-15

The [implementation report](review-implementation-2026-10-15.md) records the user's
request to continue. Exactly 28 reviewed conflicting entity/name mappings now have
reversible query-time quarantine, including fuzzy/vector fallback and whole-phrase
scorer/verifier protection. The actual catalog probe preserves all six supported
and 66 uncertain mappings; original catalog and vector bytes remain unchanged.

Scorer deterministic-3.6 requires complete mixed-graph coverage and checks bounded
safety content across the full displayed answer. Entity support is explicitly
separate from unevaluated semantic support. Evidence readiness verifies exact text
locators, declarative raw-CSV selections/counts, subtype quotas and adversarial
contracts. New manifests freeze broader code/protocol/environment state. Offline
blinded review tooling binds explicit AI/human judgments to immutable packets,
retains failures and unresolved labels, and makes no model calls.

Six prior pilot clarifications are applied to a separate 12-case development copy;
all 27 required claims retain source spans. No new held-out result, human labels,
clinical validation or permanent catalog migration is claimed. Independent audit
found and prompted fixes for shorter-alias fallback and answer-corrupting source-ID
replacement. Final validation and artifact preservation are linked in the report.
No downloads, provider calls, push or merge are added; historical scores remain
unchanged under their original evaluators.

## Independent follow-up review and repairs — 2026-10-15

The [follow-up report](independent-review-2026-10-15.md) records three independent
reviewers and cross-checks of their repairs. Confirmed gaps included category/kind
evidence bypass, quoted or negated safety support, citation-ID collisions, hashes
from different file revisions, concurrent source drift and omitted current-scorer
dependencies in frozen-system checkpoints. Fixes retain original data, prior
outputs and human queues. Scorer deterministic-3.7 remains a finite diagnostic;
historical measurements are not recomputed.

All 677 non-integration tests, Ruff and nine artifact checks pass; 81 preserved
files match the initial hashes. There is no new QA benchmark, provider call,
clinical validation, download or background service. Raw before/after probes and
reviewer cross-checks are retained locally and indexed in the aggregate report.

## Integration and live-interface verification — 2026-10-15

The [integration report](integration-2026-10-15.md) records 19 passing integration
tests: 18 in an isolated authenticated fixture database and one read-only comparison
between the research graph and frozen CSV. Four new tests cover CLI, stdio,
HTTP/SSE and rejection of unidentified non-fixture nodes. The fixture path now
requires isolation by default. All 677 non-integration tests, Ruff and nine
artifact checks pass.

Live CLI hybrid/vector and HTTP/SSE requests complete 3/4 initially, with one
provider timeout, then 4/4 on one complete-group retry. Eight calls add 27,118
conservative tokens; the cumulative ledger ends at 10,228,889. These operational
observations are separate from answer-quality or clinical claims. Research counts
and 82 preserved files remain unchanged; the final owned-process and port checks
confirm cleanup. No provider/model change, download, installation, push or merge
is performed.
