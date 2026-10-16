# Follow-up implementation and complete dev diagnostic — 2026-10-08

The user authorized all four follow-up items: bounded typo handling, a historical
alias audit, isolated integration plus complete dev checks, and preparation of an
independent evaluation. Work remains on `review-fixes-2026-10-07`, with local
commits only. V1/v2, the existing catalog and vector artifacts were not changed.
There is no new vector or held-out test result.

## Implementation

The linker now recognizes modal constructions and permits one edit, including
adjacent-letter transposition, for long alphabetic drug names. Exact catalog
matches take precedence. Distinct nearby drugs remain ambiguous; the system does
not break that tie using a tiny similarity-score difference. Short symbols,
ordinary words and exact-only document ingestion keep their previous behavior.
Fictional tests cover missing/extra/replaced letters, transpositions, exact
neighbors, ambiguous alternatives, mixed anchors and unsupported names.

On all ten dev typo anchors, linking improves from 0/10 unambiguous correct
matches to 10/10. This offline check established linking only; the complete
provider run below separately measures answers. The change does not establish
general spelling robustness or clinical identity correctness.

## Historical alias audit

The read-only audit examines 42,975 entities and 95,995 synonym strings, flagging
2,389 entity/alias pairs. Flags overlap:

| Mechanical review flag | Entity/alias pairs |
|---|---:|
| MeSH join not reproduced under current stricter rules | 402 |
| Same-label collision | 511 |
| Different-name cross-label collision | 1,497 |
| Short acronym collision | 228 |
| Ordinary/generic word | 33 |

These are review candidates, not confirmed incorrect synonyms. Broad-class and
individual-drug equivalence require source inspection by the human reviewer.
The priority batch has 100 records, with decision/reviewer/notes left null;
2,289 further records remain in the complete local audit. Nothing is removed
from the catalog, and no human verdict is inferred from a flag.

Full flags and provenance are retained in
`.cache/next-round-2026-10-08/alias-audit/flagged.jsonl`. The new authoritative
queue is `eval/human_labels/alias_audit_2026_10_08_todo.jsonl`.

## Integration and artifacts

All 15 integration tests pass: 13 fictional-graph tests plus the read-access test
run against a separately authenticated, loopback Neo4j database (14/14, 5.42 s).
The remaining CSV-count test runs read-only against the research graph (1/1,
22.43 s). No fictional fixtures enter the research graph. The temporary database
is retained locally; its server is stopped before the research server starts.
All nine artifact checks pass, including both frozen datasets, alias identities,
matrix shapes, complete corpus and retained assertion evidence.

Ruff and 412 non-integration tests pass (15 integration tests deselected in that
command; one pre-existing Starlette/httpx deprecation warning). A restricted-wrapper
test attempt stalled and was interrupted; the same required suite then passed
using the project interpreter outside that wrapper. No dependency was installed.

## Independent evaluation preparation

The [protocol](../../evaluation/independent-evaluation.md) fixes 100 blank slots:
28 graph, 12 lexical, 15 text-only, 15 graph-plus-text, 10 out-of-scope, 10 safety
and 10 adversarial. Source/code fingerprints and hashes of prior question wording
are saved before authoring. No new question, gold answer, author identity or human
review decision is fabricated.

The offline readiness tool checks assigned slots, human attestations, nonempty
gold, known UIDs/chunks, duplicate wording and frozen-source drift. It cannot prove
medical correctness or semantic independence. Passing authoring checks still does
not authorize model calls: immutable reviewed data, blinded scoring forms and a
finite scoring/run/budget registration remain required. The primary future text
answer metric is blinded human review on all 30 text/mixed cases; strict phrase
matching is a separate diagnostic. Safety/adversarial failures remain gate failures.

Local handoff materials:

- Authoritative new queue: `eval/human_labels/independent_2026_10_08_authoring_todo.jsonl`.
- Readable tables: `.cache/next-round-2026-10-08/independent-evaluation/authoring.csv`
  and `alias_review.csv` in the same directory.
- Immutable manifest and initial blocked-readiness evidence are in that directory.

The original seven human queues remain byte-identical. Both new queues are blank
in their human fields. Completing the labels is reserved to the user by task
section 4; the actual independent evaluation remains pending.

## Complete 160-question dev diagnostic

One phase-3 hybrid run uses every frozen v2 dev ID, without per-category sampling.
Provider/model/key are unchanged. Timeout is 60 seconds, ordinary cooldown two
seconds, SDK retries zero and cache off. The existing bounded planner/query repair
steps remain; zero SDK retries does not mean one model call per question. The
estimated allowance was 450,000-650,000 conservative tokens, with a hard run cap
of 800,000 and a 90-minute deadline. The run finishes in 2912.17 s.
No QA/evaluator source or retrieval artifact changes during the run. Every
completed record is retained; no failed case is selectively rerun.

| Category | Passed | API-error questions | Other execution-error questions |
|---|---:|---:|---:|
| adversarial | 10/10 (100.00%) | 0 | 0 |
| aggregation | 16/16 (100.00%) | 0 | 0 |
| lexical_variation | 18/24 (75.00%) | 0 | 0 |
| multi_constraint | 11/16 (68.75%) | 1 | 4 |
| multi_hop | 12/20 (60.00%) | 4 | 2 |
| multi_turn | 8/8 (100.00%) | 0 | 0 |
| out_of_scope | 12/12 (100.00%) | 0 | 0 |
| reverse | 12/12 (100.00%) | 0 | 0 |
| safety | 10/10 (100.00%) | 0 | 0 |
| sensitive_terms | 7/8 (87.50%) | 0 | 0 |
| single_hop | 24/24 (100.00%) | 0 | 0 |
| **All dev** | **140/160 (87.50%)** | **5** | **6** |

On the single-system subset without an API error on any conversation turn, the
result is **140/155 (90.32%)**. This is not a paired hybrid/vector
comparison. API errors are identified on every turn, not just the final response.
There are 9 failed answers without
an execution error. Error counts by failed turn: {"APITimeoutError": 5, "CypherSyntaxError": 6}.
Exact dev IDs and error classes remain in the aggregate; response text stays local.

| Lexical variant | Passed |
|---|---:|
| lay_disease_name | 3/6 (50.00%) |
| typo | 10/10 (100.00%) |
| us_brand | 5/8 (62.50%) |

| Original v2 alias_in_catalog annotation | Passed |
|---|---:|
| True | 6/9 (66.67%) |
| False | 2/5 (40.00%) |
| None | 10/10 (100.00%) |

Catalog annotations above are the frozen dataset's original labels, not a fresh
membership check after subsequent alias enrichment; None covers typo cases.
Sensitive-term false refusals are **0/8**.
Median/p90 pipeline latency is **10.70/46.04 s**,
summed across turns. This dev set informed development; neither its pass rate nor
the earlier 38-case smoke is a new estimate of held-out performance. Different
case coverage also prevents treating their headline difference as a regression.

### Remaining limitations

The typo subgroup passes all ten answers, but six lexical cases still fail the
deterministic score. Their records include extra entity matches, answers missing
expected targets and missing recognized anchors; an automatic miss is not by itself a
clinically incorrect statement. Historical alias ambiguity and scoring ambiguity
require human review, and no aliases were deleted to improve a score.

Generated complex queries still have execution failures after bounded repair.
Report those separately from free-provider failures; pacing has not established
endpoint reliability. The failed-query records retain error class/stage but do
not retain rejected query text; a syntax root cause has not been diagnosed from
these records. No code is tuned during this measurement and no used test is reopened.
Human gold, blinded text scoring and a fresh independent run remain pending.

## Accounting and delivery

This run makes 243 provider calls, reporting
353,298 tokens and conservatively charging
391,504. Failed calls without usage keep reservations in
the ledger; these are resource-accounting numbers, not monetary charges. No new
reservation remains unsettled. Cumulative additional task usage is
**4,857,467 / 6,000,000**, leaving **1,142,533**;
the ledger was never reset. The historical baseline is 5,344,304, with cumulative
task cap 11,344,304. No data/model download, provider change, installation, push,
merge or history rewrite occurred.

The evaluator and this task's Neo4j server/launcher have exited; loopback ports
7474 and 7687 are closed. Existing runs, raw data, backups, the isolated test
database and all old human queues are retained. Every original frozen input hash
matches its pre-run value. Work stops at the human-authoring/review boundary in
task section 4; automated preparation is complete, not human validation.

Evidence: [complete dev summary](../../../eval/runs/next_full_dev_hybrid_summary.json),
[implementation/check aggregates](../../../eval/runs/next_round_summary.json),
[decisions D065-D069](../../decisions.md#d065--repair-drug-mention-extraction-and-bounded-spelling-variants-2026-10-08).
Raw responses, audit files, process identities and budget checks remain local under
`.cache/next-round-2026-10-08/` and `eval/runs/`.

| Frozen snapshot | SHA-256 |
|---|---|
| QA/evaluator source | `e318277e849e3a79c0c89136e1e9ed8320b289db98d22689bbe0ad8ab7a242ec` |
| Entity catalog | `60208bae51b1ad3b84621c69e261a6ef571c09f6250bea8615e53b81e27e16e5` |
| Vector corpus | `799f9a2dd55a97bfbe92795cebccac4fe32b9ba6b05b59828d09afdafdee2b52` |
| Vector matrix | `313cd5f38442bde6f9b352926f66c5d34a0ef617797b54aeba3735cf9dfe18e2` |
