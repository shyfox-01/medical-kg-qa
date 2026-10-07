# Capability improvements — 2026-10-06

Execution continues into 2026-10-07 local time. The artifact directory keeps the
original start date so all checkpoints and recovery records stay together.

The follow-up engineering fixes are preserved. This implementation addresses the
remaining planning, relationship routing, lexical matching, explicit refusal and
human-review handoff gaps. It changes no dataset, provider or dependency.

## Implementation

- Bounded JSON repair, conservative guarded graph fallback, complete-question
  intersection and multi-hop examples, and bounded useful Neo4j retry feedback.
- Hierarchy, off-label and reverse-gene templates; matched alias spans; catalog
  alias-length coverage and unambiguous fuzzy/vector winner selection.
- Broader explicit unsupported-answer normalization; resolved conversation input
  and successful bounded query constraints provided to answer generation.
- Independent deterministic-3.3 corrections for cross-type alias collisions and
  conversation anchors; isolated source control and frozen full-test runner.
- Validated blind-review import with backups; no agent-created human labels.

## Verification and interpretation

Final-source Ruff and 213 unit tests pass. Native Neo4j integration passes all 15 tests,
including actual CSV/graph counts and fictional multi-hop/intersection checks.
FakeLLM passes all 13 cases in three rounds with no redline regression. Temporary
fictional nodes are removed before real evaluation. The isolated environment is
Python 3.12.10; no dependency was added or upgraded in this implementation.

Development evidence is iteration-specific: the 36-case pre-improvement run is
29/36 under independent deterministic-3.3 offline rescoring. A later 36-case
development iteration is 35/36 under the same rescoring (saved answers, zero new
model calls). The subsequent eight-conversation run is 6/8, with one first-turn
provider timeout and one redundant-alias list error. After the final prompt
revision, the two selected development failures pass 2/2. These selected rechecks
do not establish a whole-development-set or test-set improvement.

The full comparison is frozen at 2,149,226 charged/reserved task tokens. Its own
ceiling is 12,149,226, below the 15-million task cap. The initial plan requested 240
test questions per system, three rounds and three systems, maximum four hours. Code and data
hashes are in `eval/runs/improvement_plan_summary.json`. All test cases include
the previously reported 38-case pilot; the full set is not a wholly fresh holdout.
No test-answer tuning is performed. Historical summaries remain immutable.
An importer-only privacy refinement and two failure-path unit tests were added
during the experiment. All 80 frozen QA/evaluator/runner/data/selection hashes
were verified unchanged at completion, before the separate maintenance patch.

After the first complete improved-system round approached 50 minutes, the original
serial schedule projected beyond the wall cap. Following the task's timeout
sampling instruction, the separately frozen balanced plan completes one full
240-case round per system plus three rounds on 70 fixed common cases. The subset
uses seed 42 and cap 5 per non-redline category, retaining all 30 safety/adversarial
cases. Reuse the actual full first-round subset and run two more subset rounds;
source fingerprints must match before combination. Original plans, the complete
first round and interrupted second-round prefix remain intact. Abandoned attempts
remain charged in the ledger. The four-hour deadline and token ceiling are shared,
not reset. See D042 and `improvement_balanced_plan_summary.json`.

The first control attempt after the orchestration switch encountered an abandoned
single-request slot left by the stopped worker. Three 120-second lock-wait cases
never reached the provider. After verifying all owned LLM workers had exited,
the slot and invalid partial records/checkpoint were moved with matching hashes
to `.cache/improvement-2026-10-06/abandoned-lock-control/`. The control restarted
under the same frozen inputs and deadline. Diagnostics and conservative ledger
charges are preserved; those operationally invalid attempts are excluded from
performance rates. Successful control execution was verified after recovery.

The pre-maintenance wheel is `.cache/improvement-2026-10-06/wheel-final/medkg-0.1.0-py3-none-any.whl`
(53,893 bytes), SHA-256
`f6ee903aab196b3cd061ca229aa09e74f997a0f68f239628d8e2a3aeb067c58e`.
Cached artifact and delivery checks pass; 27 retained assertions remain
internally supported, with 121,277 alias rows and 47,668 complete corpus rows.
These checks do not validate the retained assertions medically.

## Complete first-round comparison

Each row covers all 240 frozen structured test cases once, with cache disabled,
the same approved provider/model, repaired cached data and deterministic-3.3.

| System | Passed / 240 | Pass and composite quality |
|---|---:|---:|
| Exact pre-capability phase-3 hybrid | 141 | 58.75% |
| Improved phase-3 hybrid | 206 | 85.83% |
| Improved-code pure-vector control | 127 | 52.92% |

The observed improved/control difference is 27.08 percentage points for this
benchmark and single round. A single round cannot estimate repeat variance.
All fixed 70-case measurements have completed. This is a safety-heavy subset
(30/70 redline cases), not three repetitions of all 240 cases or a full-test estimate.

| Category | Cases | Before | Improved | Vector |
|---|---:|---:|---:|---:|
| adversarial | 15 | 100.00% | 93.33% | 80.00% |
| aggregation | 21 | 71.43% | 80.95% | 28.57% |
| lexical_variation | 27 | 59.26% | 88.89% | 48.15% |
| multi_constraint | 27 | 7.41% | 85.19% | 18.52% |
| multi_hop | 36 | 19.44% | 66.67% | 13.89% |
| multi_turn | 12 | 75.00% | 83.33% | 83.33% |
| out_of_scope | 18 | 100.00% | 100.00% | 88.89% |
| reverse | 27 | 40.74% | 85.19% | 59.26% |
| safety | 15 | 100.00% | 100.00% | 100.00% |
| single_hop | 42 | 78.57% | 90.48% | 69.05% |

The largest observed change is in complete-question graph constraints. Multi-hop
remains the weakest improved non-redline category at 24/36. Category results are
benchmark-specific automated judgments; human semantic and clinical validation
remain absent.

The first improved round fails the strict no-regression gate on one adversarial
id: its routing call raises `APITimeoutError`, with zero executed statements and
no forbidden content. The control successfully refuses that request. A transport
failure is still a refusal-availability regression under the declared gate.
Preserve that failure; do not reinterpret it as a passing redline result.

The measured source snapshot is saved and byte-verified in ignored
`.cache/improvement-2026-10-06/measured-source/`. Follow-up lock or scope maintenance
will receive independent checks, not these earlier full-round scores.

## Complete fixed 70-case three-round comparison

Reuse the actual first-round subset and add two fresh rounds on the same ids.
Pass and composite quality coincide in these measurements. Standard deviation
is the population standard deviation of three round rates, in percentage points;
it is descriptive and not a confidence interval or significance test.

| System | Round 1 | Round 2 | Round 3 | Mean | Std | Inconsistent ids | Redline regressions |
|---|---:|---:|---:|---:|---:|---:|---|
| Before | 70.00% | 72.86% | 72.86% | 71.90% | 1.35 pp | 6 | Baseline |
| Improved | 90.00% | 90.00% | 92.86% | 90.95% | 1.35 pp | 6 | 1; gate failed |
| Vector | 71.43% | 75.71% | 74.29% | 73.81% | 1.78 pp | 5 | 3; gate failed |

The improved/control difference is 19.05 percentage points for this fixed subset.
The improved redline failures by round are 1, 0 and 0; the first timeout remains
a regression under the strict minimum-outcome gate. Vector's initial three failures
lack the expected explicit refusal, with safe recorded queries and no forbidden
content. They are not evidence of executed writes or disclosed credentials.

`improvement_full_{before,after,vector}_summary.json` and
`improvement_balanced_{before,after,vector}_summary.json` contain per-category
precision/recall/F1, exact counts, entity faithfulness, execution accuracy **with
coverage**, refusal, latency, usage, failure stages and inconsistent ids. Execution
accuracy is conditional on available comparisons; absent coverage stays null.
Failure-stage and cost accounting include all conversation turns, so failed-turn
counts can exceed failed-case counts. These summaries do not prove sentence-level
medical accuracy.

Measured source fingerprints are
`417a0c0ed918f3fb302d363e0ba00a081e308c16f00fba357f231f6f6d42de2d` (before) and
`8e159e3737bf55a6b6329ceb4469e9bcf5d678d37b64ffae147f9910f8f06a60` (improved/vector).
The final maintenance source is
`a2e42a7a54957b2bb389b4ba3b15cc964a25a5c6a427272f41a29d514fae2f30`.
Only `llm.py`, the pipeline scope branch and new `qa/scope.py` differ after
measurement. Earlier comparison scores belong to the saved capability snapshot.

## Separate final-source maintenance validation

OS-owned mutexes replace crash-sensitive lock ownership after the experiment.
Real owned-process probes verify live exclusion, exception release, forced-exit
reacquisition and retained legacy locks. Administrative scope refusal precedes
cache, linking, retrieval and provider calls; clinical safety remains first.
Development adversarial cases and 20 fictional text boundaries guide the finite
rules. Test question/answer text is not used to tune code or prompts.

The fixed 22-case development selection passes 22/22 on final code. All 30
safety/adversarial test ids pass three fresh hybrid rounds, with no redline
regressions, no failure stages and no inconsistent ids. See
`improvement_redline_final_summary.json`. This is a new check, not a replacement
for the failed historical gate. Some adversarial refusals, including the initial
timeout id, still use the provider; future transport failure remains possible.
The finite scope guard is not a general prompt-injection classifier.

Vector's fresh final-source redline rounds each pass 29/30 (96.67%), with one
repeatable explicit-refusal regression and gate exit 1. See
`improvement_vector_redline_final_summary.json`. It remains an experimental control;
the passing hybrid gate does not approve vector as a fallback.

## Delivery, resource accounting and remaining work

The balanced comparison completes in 202.81 minutes within its original four-hour
window, including adaptation and recovery. It adds 2,480,504 conservatively charged
tokens from the frozen 2,149,226 balance. Final task balance is 4,719,544 of
15,000,000; this implementation adds 2,717,040 from its initial 2,002,504 balance.
Failed calls and interrupted reservations remain charged. This ledger is not a
provider invoice. Provider/model are unchanged: verified HTTPS
`open.bigmodel.cn`, `glm-4.5-flash`, thinking disabled, no new keys or downloads.
No dependency is installed or upgraded in this implementation.

The nine unique complete detail files contain 1,140 scored cases and 1,206
conversation turns. Every requested trace matches in
`improvement_profile_summary.json`; reused first-round records are counted once.
LLM spans have median 5.07 seconds and p90 14.28 seconds; template retrieval median
is 0.0039 seconds, vector retrieval median 0.0124 seconds. Nested spans overlap.
These are observed local/provider timings, not standalone capacity measurements.

Final artifact and delivery checks pass: frozen dataset, English/private-data/
credential boundaries, independent evaluation imports, complete cached vectors,
retained evidence and real graph counts. Temporary fictional nodes are removed.
The 27 retained assertions remain internally supported, with 121,277 alias rows
and 47,668 corpus rows; this does not establish medical truth.

The final offline-built wheel is
`.cache/improvement-2026-10-06/wheel-delivery/medkg-0.1.0-py3-none-any.whl`,
60,676 bytes, SHA-256
`ca6208202a2f998c24c2d1524c8fc4c5ae1c3f2a6c06b070fc50c1d8872df189`.
All 43 entries are package code or metadata; cached/raw/derived data, credentials
and private answers are absent. The existing README was missing from project
metadata; D046 adds its declaration and preserves the preceding code-only build.
Current measured outcomes and limitations are verified inside wheel metadata.

`improvement_human_review_delivery_summary.json` verifies unchanged source hashes
and zero human-labelled items in the 100-claim judge, 30-assertion extraction,
18-item quarantine and 80-text-draft queues. The import mechanism supplies no human
decisions. All judge and draft evidence remains uncalibrated/unreviewed.

Remaining improvement space is independent human semantic/clinical review, a
more natural benchmark (only 24/400 questions were LLM-paraphrased), broader
multi-hop constraints, finite-rule scope coverage and provider-dependent refusal
availability. Keep test answers out of subsequent prompt development. Docker,
remote CI and Phoenix execution remain unverified; Docker is absent and images/
push are prohibited by the task. No deployment or clinical-efficacy claim is made.

The verified owned Neo4j server (PID 3564) shuts down gracefully; bootstrap PID
36744 also exits. No evaluation worker or listener on 7474/7687 remains. Idle native
mutexes are acquirable; their persistent files do not represent live workers.
Cleanup evidence is `.cache/improvement-2026-10-06/cleanup-summary.json`; final
checks, source provenance, wheel and accounting are in
`eval/runs/improvement_validation_summary.json`. Changes remain in the working tree;
no push, history rewrite, new dependency or persistent background service is added.

Human review, remote CI, container execution and Phoenix remain unverified. Docker
is absent locally and the task prohibits pulling images and pushing. Clinical
validation is not claimed. Decisions and rejected alternatives are D038–D046.
