# Implementation after the AI review — 2026-10-15

The user's request to continue is implemented as code changes following the
[October 9 review](ai-review-2026-10-09.md): reversible alias quarantine, stronger
automatic scoring diagnostics, reproducible evidence checks, and offline blinded
review tooling. Three workers implemented separate components; a fourth agent
independently probed their boundaries. The root integrated the changes and checked
the actual cached catalog and evidence. This is an engineering validation round,
with no new QA benchmark or clinical-performance claim.

## Changes and observed checks

| Area | Implemented behavior | Evidence |
|---|---|---|
| Reviewed aliases | Quarantine exactly 28 conflicting entity/name mappings, without rewriting stored data | All 28 fail to resolve to the rejected entity by direct linking and in questions; all 28 canonical-name checks pass |
| Preserved names | Keep supported and unresolved mappings distinct from rejected mappings | All six supported and 66 uncertain reviewed pairs retain their existing mappings |
| Retrieval boundary | An unresolved quarantined name asks for an exact drug name before planning/retrieval in either mode | Actual catalog yields 28 such gates; synthetic hybrid/vector tests verify zero model calls |
| Alias fallback and verification | Skip stale excluded vector rows; reserve full rejected phrases before shorter matching | 28 stale vector rows identified; synthetic tests cover fuzzy, vector, scorer and output-verifier paths |
| Mixed graph/text scoring | Every expected graph UID must occur in answer and evidence; empty graph gold fails | An incomplete two-entity synthetic answer now fails |
| Safety scoring | Check the whole displayed answer against bounded content requirements independently of refusal flags | Flags-only emergency/crisis counterexamples fail; footer content, negation and benign factual controls are tested |
| Metric meaning | Report entity support separately; semantic support stays null and unevaluated | A contrary-predicate fictional example cannot be presented as semantic validation |
| Evidence readiness | Verify spans, offsets, hashes, document joins, graph targets/counts, subtype quotas and adversarial contracts | Revised pilot spans pass; corrupted evidence, invented counts and malformed plans fail |
| Blinded review | Prepare opaque A/B packets, preserve a private mapping and trusted receipt, validate labels and retain failures | Synthetic offline round-trip, tamper, missing-response and unresolved-label checks |
| Pilot revision | Apply six existing wording/rubric notes in a new development copy | 12 cases, 27 required claims and 23 source spans; original references and review artifacts preserved |

## Alias correction scope

`medkg_data.alias_policy` records the exact reviewed pairs. This is an engineering
quarantine based on AI source review, not a claim that all terminology questions
are settled. Valid other owners and longer canonical names take precedence;
uncertain formulations and brands remain uncertain. The two relationship-label
disagreements from the original review remain in their raw artifacts.

The original catalog, graph, alias vectors and vector-corpus paragraphs are not
rewritten. Query-time safeguards prevent explicit rejected names from reaching
planning/retrieval as the wrong drug, and alias-vector lookup ignores the excluded
rows. Future enrichment and embedding/corpus builders honor the same exclusions.
No embedding rebuild, new graph import or service startup is required here.

This does not purge historical mention edges or every occurrence from stored
documents. Questions using a broad rejected name may receive a clarification even
when a general textual answer could be useful. New paraphrases and unreviewed
aliases are outside this 28-pair policy. The 66 unresolved pairs still need
additional identity evidence; they were not converted into negative labels.

## Scoring and evidence integrity

The evaluator is now `deterministic-3.6`. Historical reports keep their original
versions and scores; they are not rescored or directly compared with this revision.
`faithful` remains a compatibility alias for `entity_supported`; both describe
entity presence only. `diagnostic_passed` clarifies the meaning of the legacy
`quality_passed` field. `semantic_support` remains null with status `not_evaluated`.
No deterministic phrase check has been promoted into a claim-entailment judge.

Safety diagnostics use finite English patterns against the existing response
contract. They now detect missing required support and bounded forms of explicit
contradiction in the full displayed answer, including content after footer markers.
They can still miss unfamiliar harmful wording or reject an acceptable paraphrase.
Passing these checks does not establish clinical safety. Case-specific semantic
review is recorded separately through the blind-review workflow.

`eval.evidence` reconstructs declared graph gold from raw CSV relations and explicit
directions, with one or two steps and sorted distinct final targets. It retains
self-edges, collapses duplicate paths and executes no supplied query or code.
Its narrow plan format excludes arbitrary filters, intersections and negation.
Text checks prove the integrity of exact claimed evidence, not its interpretation.
A real cached-CSV probe reconstructs a declared selection and rejects an altered
count; this is source reconstruction, not a QA performance measurement.

Schema-2 readiness additionally requires two safety cases per subtype, explicit
safe/prohibited behaviors and observable adversarial objectives. It freezes QA,
evaluator, validator and script source, protocols, dependency declarations and a
nonsecret environment inventory. The preserved old human packet is unfinished
and requires a newly identified schema-2 package for future preregistration.
No old queue is rewritten, and readiness never authorizes a model call.

## Blind review and revised pilot

The [blind-review guide](../../evaluation/blind-review.md) documents concrete offline
commands and schemas. Public packets omit system metadata, timings and automatic
scores. Private mappings, input/code/environment hashes and a saved preparation
receipt bind returned labels to the reviewed artifacts. Labels distinguish AI
from human review; unresolved or missing judgments never become passes. Failed
responses stay in all-case denominators. The tool records reviewer judgments;
it does not generate or authenticate them.

Only explicit bracket citations are rewritten to opaque source IDs; factual prose
and numbers must remain unchanged. Raw and displayed answers have separate hashes.
Style, source selection or model names within answer prose may still reveal
identity; known body clues are preserved and disclosed instead of destructively
redacting factual text. Custodians must inspect this residual blinding limitation.

The new pilot copy clarifies trial-board wording and plant origin, and separates
optional sleep, immunity, urine-route and MRI elaborations from required claims.
Its original reference answers remain intact. This previously exposed AI-authored
material is explicitly a development diagnostic, not fresh held-out or human gold.
No system answers were collected against it.

## Independent implementation audit

The independent auditor found two concrete implementation defects during this
round: rejected names could return through a shorter retained alias in the scorer
and output verifier; global source-ID replacement could change an ordinary number
inside a displayed answer. Both were assigned back for fixes and targeted
regressions. Final audit evidence is included in the local verification summary.

One tooling worker inadvertently exposed a few historical text_v1 questions in
an early broad search. It immediately disclosed the exposure and restricted further
reads to named code/protocol files and synthetic fixtures. It authored no benchmark
and supplied no medical judgments. No historical QA outputs were reopened for
tuning. The existing pilot's earlier authoring record is preserved; this round
does not claim question blindness or a new independent evaluation.

## Delivery and remaining limits

The [aggregate verification record](../../../eval/runs/review_implementation_2026_10_15_summary.json)
contains final tests, artifact checks, preservation hashes and resource accounting.
Private evidence and scripts live in `.cache/review-implementation-2026-10-15/`.
The revised [readable pilot](../../../.cache/review-implementation-2026-10-15/pilot-r2/pilot.csv)
is local-only; it is not available from a fresh public clone.

All original human queues, frozen datasets, stored catalog/vector/source artifacts
and October 9 review evidence remain unchanged. The nine cached-artifact checks
pass. Integration services and historical model evaluations are not rerun for
this round; query-boundary tests use controlled stores and the real catalog.
No downloads, installations or project-provider calls are added. The conservative
GLM ledger remains at 10,201,771 cumulative tokens; Codex agent work is separate AI
usage. Changes are local on `review-fixes-2026-10-07`, without push or merge.

Remaining work before a stronger performance claim includes finalizing a separately
registered dataset and case-specific semantic rubric, performing actual review of
future responses, and resolving unsupported source identities with additional
evidence. The tools now support that workflow; their tests do not supply those
judgments or establish clinical effectiveness.

Final verification: Ruff passes; **593 non-integration tests pass**, with 15
integration tests deselected and one existing Starlette TestClient deprecation
warning. The complete run takes 9.82 seconds. Approved execution outside the
restricted sandbox uses the project interpreter and a new project-local temporary
directory, avoiding the previously reproduced sandbox stall. Independent audit
closes both correctness findings and the disclosure follow-ups with no remaining
blocking finding in its scope. Seventy preserved files and the final audited
source hashes are checked. No task-owned background service remains running.
