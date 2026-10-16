# Frozen v2 evaluation results — 2026-10-08

The accepted phase-3 hybrid run passes 194/240 questions (80.83%); the pure-vector
control passes 78/240 (32.50%). On the same 233 questions where neither system
has an API error, the rates are 83.26% and 32.62%. These are single-round results
on a frozen, mostly template-based knowledge benchmark, without clinical validation.
The vector control fails one adversarial case that hybrid passes.

This is the pre-improvement snapshot. The later [T5 work](t5-improvements.md)
changes code, vocabulary and corpus; its dev diagnostics do not replace or revise
any test result below. The original dataset annotations and accepted run artifacts
are preserved.

## Scope and accepted runs

| Scope | Questions | Hybrid | Pure vector |
|---|---:|---:|---:|
| All frozen test cases | 240 | 194/240 (80.83%) | 78/240 (32.50%) |
| Paired, neither system has an API error | 233 | 194/233 (83.26%) | 76/233 (32.62%) |

Sources: [hybrid summary](../../../eval/runs/v2_test_hybrid_retry3_summary.json),
[vector summary](../../../eval/runs/v2_test_vector_retry1_summary.json), and
[paired/category aggregates](../../../eval/runs/v2_comparison_summary.json).
Each accepted run contains all 240 distinct frozen test IDs once, with saved
60/120/180/240-question milestones. The first valid attempt of each system is
accepted by the API-error rule, without selecting a higher-scoring attempt.
No test answers were used to change QA code, prompts or retrieval inputs.

Both runs use `deterministic-3.5`, phase 3, cache off, the existing free
`glm-4.5-flash` endpoint at `open.bigmodel.cn`, temperature 0, thinking disabled,
zero SDK retries, a two-second post-call cooldown and a 60-second provider timeout.
The provider timeout was increased from 30 seconds through the existing
process-local configuration after API-invalid attempts (D058); both accepted
systems use this same setting. The 300-second worker deadline remains unchanged.
Neither accepted run is truncated by a worker deadline or the token cap.

The dev smoke completes 38 cases, because the existing sampler retains every
safety/adversarial control despite `--max-per-category 2`: 30 pass (78.95%), five
have API timeouts and two have handled planning validation errors. Planning-output
leniency is reserved for T5; the smoke does not become a capability estimate.

## Category pass rates

| Category | Questions | Hybrid | Pure vector |
|---|---:|---:|---:|
| adversarial | 15 | 15/15 (100.00%) | 14/15 (93.33%) |
| aggregation | 24 | 23/24 (95.83%) | 7/24 (29.17%) |
| lexical_variation | 36 | 17/36 (47.22%) | 0/36 (0.00%) |
| multi_constraint | 24 | 17/24 (70.83%) | 2/24 (8.33%) |
| multi_hop | 30 | 26/30 (86.67%) | 1/30 (3.33%) |
| multi_turn | 12 | 11/12 (91.67%) | 3/12 (25.00%) |
| out_of_scope | 18 | 17/18 (94.44%) | 16/18 (88.89%) |
| reverse | 18 | 15/18 (83.33%) | 3/18 (16.67%) |
| safety | 15 | 15/15 (100.00%) | 15/15 (100.00%) |
| sensitive_terms | 12 | 8/12 (66.67%) | 4/12 (33.33%) |
| single_hop | 36 | 30/36 (83.33%) | 13/36 (36.11%) |

All 240 cases remain in these denominators, including API and system failures.
The secondary composite-quality metric is 193/240 (80.42%) for hybrid and
73/240 (30.42%) for vector; it is distinct from the pass-rate metric above.

## Paired comparison without API errors

An API-error question has at least one `APITimeoutError`, `RateLimitError`,
`APIConnectionError` or `InternalServerError` on any conversation turn. Exclude the
union of these IDs across both systems, then score both on the same remaining IDs.
Hybrid has seven such questions; vector has none, leaving 233 paired questions.
Planning and query failures remain failures in this comparison.

| Category, paired without API errors | Questions | Hybrid | Pure vector |
|---|---:|---:|---:|
| adversarial | 15 | 15/15 (100.00%) | 14/15 (93.33%) |
| aggregation | 23 | 23/23 (100.00%) | 6/23 (26.09%) |
| lexical_variation | 34 | 17/34 (50.00%) | 0/34 (0.00%) |
| multi_constraint | 24 | 17/24 (70.83%) | 2/24 (8.33%) |
| multi_hop | 29 | 26/29 (89.66%) | 1/29 (3.45%) |
| multi_turn | 12 | 11/12 (91.67%) | 3/12 (25.00%) |
| out_of_scope | 17 | 17/17 (100.00%) | 15/17 (88.24%) |
| reverse | 17 | 15/17 (88.24%) | 3/17 (17.65%) |
| safety | 15 | 15/15 (100.00%) | 15/15 (100.00%) |
| sensitive_terms | 11 | 8/11 (72.73%) | 4/11 (36.36%) |
| single_hop | 36 | 30/36 (83.33%) | 13/36 (36.11%) |

Excluded IDs: `v2-0082`, `v2-0121`, `v2-0147`, `v2-0177`, `v2-0263`,
`v2-0320`, `v2-0344`. This conditional comparison does not replace the full-test
result or establish performance when the provider is always available.

## Lexical variation and catalog coverage

| Lexical variation | alias_in_catalog | Questions | Hybrid | Pure vector |
|---|---|---:|---:|---:|
| us_brand | All | 17 | 10/17 (58.82%) | 0/17 (0.00%) |
| us_brand | true | 11 | 10/11 (90.91%) | 0/11 (0.00%) |
| us_brand | false | 6 | 0/6 (0.00%) | 0/6 (0.00%) |
| lay_disease_name | All | 14 | 7/14 (50.00%) | 0/14 (0.00%) |
| lay_disease_name | true | 9 | 7/9 (77.78%) | 0/9 (0.00%) |
| lay_disease_name | false | 5 | 0/5 (0.00%) | 0/5 (0.00%) |
| typo | All | 5 | 0/5 (0.00%) | 0/5 (0.00%) |
| typo | not_recorded | 5 | 0/5 (0.00%) | 0/5 (0.00%) |

The test split contains 17 brand-name, 14 lay-name and five typo questions; it is
not proportional within each lexical subtype. Typo cases have no
`alias_in_catalog` annotation, so `not_recorded` is preserved rather than inferred
as false. Among the 31 annotated forms, 20 are in the catalog and 11 are absent.
Hybrid passes 17/20 catalog-present forms and none of the 11 absent forms.
Both systems fail all five typo cases. Vector passes no lexical-variation case,
including those whose forms are present in the catalog.

Catalog membership describes the linker's catalog. It does not prove that an
alias survives the vector paragraph's 20-alias limit, is retrieved, or yields a
correct answer. Adding synonyms to the vector corpus therefore does not itself
demonstrate improved lexical capability; this task has no same-v2, pre-rebuild
vector measurement. The T5 handoff lists 18 absent brand/lay forms, whereas the
frozen dataset contains 16 rows marked `alias_in_catalog=false` (11 test, five
dev). This count discrepancy remains disclosed for follow-up; neither the labels
nor the catalog were changed to reconcile it. The test denominators above come
directly from the frozen annotations.

## Sensitive-term false refusals and safety

All `sensitive_terms` cases are answerable knowledge questions. Count the
scorer's explicit `refused` flag, including an explicit unsupported refusal.
This metric can miss implicit refusal wording and does not count every wrong
answer as a refusal.

| sensitive_terms refusal scope | Questions | Hybrid | Pure vector |
|---|---:|---:|---:|
| all | 12 | 1/12 (8.33%) | 1/12 (8.33%) |
| paired_no_api_error | 11 | 1/11 (9.09%) | 1/11 (9.09%) |

Both systems pass 15/15 safety cases. Hybrid passes 15/15 adversarial cases;
vector passes 14/15. **Vector regresses on `v2-0373`**, which hybrid passes:
the vector result has `refused=false` and `safety=none`, without an API or execution
error. This remains a failed adversarial control. The recorded forbidden-content,
unsafe-generated-query and unsafe-executed-statement counters are zero for both
systems; these bounded checks do not establish general resistance to injection.

## API availability and retained attempts

| Attempt (file stem) | Completed | Timeout setting | Timeout / rate-limit questions | Other failure questions | Disposition |
|---|---:|---:|---:|---:|---|
| `v2_test_hybrid` | 240/240 | 30 s | 24 / 20 | 15 | Invalid; retained locally |
| `v2_test_hybrid_retry1` | 240/240 | 30 s | 18 / 12 | 16 | Invalid; retained locally |
| `v2_test_vector` | 121/240 | 30 s | 16 / 1 | 0 | Invalid; retained locally |
| `v2_test_hybrid_retry2` | 24/240 | 30 s | 2 / 9 | 0 | Invalid; retained locally |
| `v2_test_hybrid_retry3` | 240/240 | 60 s | 1 / 6 | 17 | Accepted |
| `v2_test_vector_retry1` | 240/240 | 60 s | 0 / 0 | 0 | Accepted |

There are no connection-error or internal-server-error questions in these
attempts. The accepted hybrid run has one timeout and six rate-limit questions,
plus ten planning `ValidationError` and seven `CypherSyntaxError` questions.
The accepted vector run has no API or other execution-error questions; its
incorrect answers and refusals still count as failures.

Every invalid attempt remains local with its records, checkpoint and logs. The
two complete invalid hybrid summaries are not committed; the two stopped prefixes
have no completed summary. The pre-existing `review_fix_*_summary.json` files also
remain local. Invalid rounds are never pooled into capability scores. The first
vector prefix stops at the original budget gate; the next hybrid prefix stops
upon its eleventh API-error question. Reruns start from all 240 questions under a
new filename, after at least ten minutes without model calls following an invalid
attempt. No individual failed question is selectively rerun.

## Latency and token accounting

| System | Median / p90 latency (s) | LLM calls | Input tokens | Output tokens | Reported total |
|---|---:|---:|---:|---:|---:|
| hybrid | 12.76 / 41.97 | 407 | 522,878 | 46,599 | 569,477 |
| vector | 11.02 / 41.11 | 248 | 1,182,720 | 68,909 | 1,251,629 |

Latency is pipeline time summed across every conversation turn, including provider
waiting and the configured cooldown; it excludes evaluator setup and gold-query
scoring. Percentiles follow the frozen evaluator's sorted-order convention.
Complete-run wall time is 76.07 minutes for hybrid and 64.65 minutes for vector.
These sequential local runs include normal host and provider variability and are
not a controlled deployment-latency or repeated-stability study.

| Task component | Provider-reported tokens | Conservative ledger tokens |
|---|---:|---:|
| Dev smoke | 40,607 | 69,000 |
| Four invalid test attempts | 1,494,991 | 2,456,579 |
| Accepted hybrid | 569,477 | 627,148 |
| Accepted vector | 1,251,629 | 1,251,629 |
| **Total additional task usage** | **3,356,704** | **4,404,356** |

The user approved raising the total additional task allowance from 3,000,000 to
6,000,000 (D057). The original ledger balance, 5,344,304, was retained; the final
balance is 9,748,660 against a cumulative cap of 11,344,304. Remaining allowance:
1,595,644. Failed calls without reported usage keep their full UTF-8-input-plus-
output reservation. These conservative tokens are resource accounting, not
metered billing. Four old unsettled reservations remain included in the original
balance; no new reservation is unsettled. All invalid attempts and stopped
in-flight calls remain included in task accounting.

## Vector rebuild and reproducibility

The control contains 47,668 rows: 42,975 entity paragraphs and 4,693 unchanged
document rows. Entity paragraphs use catalog synonyms, retained MeSH additions
first, normalized/deduplicated and capped at 20. Of the entity paragraphs, 18,889
have synonyms; 3,699 receive MeSH priority. New paragraphs are fully re-embedded
on the existing cached CPU model with at most four threads. A desktop interruption
was resumed at 6,720 completed rows under the same corpus hash. The hash-verified
old corpus, matrix and progress file remain in `.cache/vector-corpus-pre-v2/`.

| Frozen input | SHA-256 |
|---|---|
| v2 dataset | `749cab3bfb68e2ce95f75e4894e5b3de30da0c1a6af9b3c8959c383d86ca7572` |
| QA/evaluator source | `a926a2798215e2e4930ba378dd042063c861977260ae5bfe99938f0bbf59965c` |
| Entity catalog | `f82a736d3d9b7432a139866ae902c9d2c002e52f206229e3bea271562b32a111` |
| Synonym corpus | `1bedffcb6a8f4268f8e63a97ae46bcb9726159cd016629afe79d9697e350fe8f` |
| 47,668 x 384 embedding matrix | `081bc9f5a8fe9ed4cd3d9ffcc93bcdea97c2b1a1260335bc2ad263f92747690c` |

The [artifact summary](../../../eval/runs/v2_artifact_check_summary.json) has all nine
checks passing; a final recheck gives the same result. V1/v2 dataset, catalog,
synonym ledger and QA/evaluator hashes remain unchanged after the test freeze.
The matrix is finite and normalized. All seven human-review queues are unchanged.
Ruff passes; 307 unit tests pass, with 15 integration tests deselected and one
existing Starlette/httpx deprecation warning. Native integration tests were not
rerun in this task. Artifact checks do not verify the live graph or clinical truth.

## Limits and the T5 stop

- Each system has one accepted round. API-invalid retries and the disclosed
  runtime timeout amendment prevent claims of repeated-run reliability or a
  controlled before/after effect. V1 has different cases and scoring; its scores
  are historical, not a matched baseline for v2.
- The 400-case v2 set has 28 validated LLM rewordings, 95 unchanged LLM returns,
  261 templates and 16 template fallbacks after failed validation. The test
  subgroups are small. CSV-derived gold and entity/quote checks do not establish
  clinical accuracy; text drafts, extraction and judge labels still need people.
- Long lists are scored using precision plus a partial-list notice, with a
  complete 16-25-item list also accepted. These scores do not measure full recall
  for high-degree entities. Catalog membership does not prove sentence truth.
- Coverage gaps remain. The handoff names Rubraca, Zejula and lazy eye and notes
  that Tamiflu is absent from the cached MeSH source. Its 18-form count differs
  from the 16 frozen rows flagged absent, as disclosed above. The synonym cap and
  retrieval stage impose further limits.
- Special-population rules still falsely refuse some knowledge questions, such
  as infant/medicines wording. Planner format tolerance and generated-query syntax
  remain failure sources. The free endpoint's limits and timeouts remain an
  availability risk despite the accepted rounds.

Numeric `count` output is one known planner-format issue reserved for T5. The
saved validation errors do not identify which field failed in each measured case;
the report does not attribute all ten accepted-run validation errors to `count`.

Stop after T1-T4. Alias expansion, special-population rule changes, planner-format
leniency and provider-availability improvements are pending the user's T5
decision. No new data or dependencies were downloaded, no DrugBank vocabulary
was found in the local raw-data inventory, and no synonym-enrichment apply step
was run. Human labels were not filled. Docker, remote CI and Phoenix verification
remain outside this task. All changes are local on `review-fixes-2026-10-07`,
without a push or merge. The owned evaluators, Neo4j console and launcher have
exited; ports 7474/7687 were confirmed closed.
