# Independent implementation review and repairs — 2026-10-15

The user requested another independent review of commits `b62e2b4` and `4d73f08`
and authorized repairs. Three fresh-context agents reviewed alias/scoring,
evidence/readiness and offline blind-review code from base `4d73f08`. They used
named code, tests and protocols with synthetic counterexamples. They did not read
historical QA outputs or frozen benchmark questions. The root confirmed representative
failures and integrated the repairs; agents cross-checked other owners' changes.

## Confirmed findings and repairs

| Finding | Reproduction before repair | Result after repair |
|---|---|---|
| P2: evidence dispatch bypass | A declared aggregation case with `kind=safety` and invented count returned integrity success with zero graph rows checked | Known category/kind mismatches fail before dispatch; valid generic kind-only rows remain supported |
| P2: quoted or negated safety support | A quoted example containing an emergency action or dose boundary satisfied required support; a negated isolation precaution could also pass | Required support uses a bounded unquoted affirmative-statement view; full displayed text remains subject to prohibitions |
| P2: citation masking collision | An unknown raw `[S1]` and a real source citation became identical displayed answers | Public source IDs skip both original IDs and existing bracket references; the unknown citation stays visibly distinct |
| P2: audit digest described different bytes | Saving labels or the authoring queue during validation attached a newer file's hash to older judgments/readiness | Parsing and hashing share captured bytes; readiness rejects detected queue edits; blind results identify their exact reviewed snapshot |
| P2: source drift during readiness | A graph file changed after the initial snapshot but readiness still returned true | Frozen hashes are checked before and after validation, with either drift blocking readiness |
| P2: incomplete evaluation checkpoint dependencies | With alternate QA source selected, the current scorer's alias policy could change without changing the old fingerprint | Named file hashes include the selected QA tree and current evaluator/data-policy dependencies |

Two smaller improvements accompany these repairs. Malformed authoring rows and
invalid IDs now return validation errors instead of uncaught attribute errors.
Unblinded summaries cannot be written into either the supplied public directory or
the original directory recorded in the trusted manifest when a packet is copied.

Cross-review caught additional single-quote/possessive and single-quoted prohibition
edges in the first scoring repair. These were returned to the owner for regression
tests and another independent check. This is an engineering review of synthetic
failure cases, not evidence that a deployed QA system produced those answers.

## Scope and retained limits

The scorer is now `deterministic-3.7`. No old answers are rescored and no new
performance result is claimed. Entity support still does not establish claim
entailment. Safety diagnostics remain finite English rules and can miss unfamiliar
wording or reject acceptable paraphrases. AI reviewers supply engineering findings,
not clinical certification or human labels.

The alias policy itself is unchanged. A synthetic cross-path probe covers all
28 excluded pairs, retained canonical names, valid other owners and stale vector
rows without finding a new runtime defect. An independent in-memory graph oracle
checks 300 declared one/two-hop selections, including both directions, duplicate
paths and numeric-ID normalization, with no mismatch. These bounded probes do not
establish complete terminology coverage or external-system behavior.

Byte snapshots identify what was validated; they do not lock files or create an
atomic snapshot across the repository. The readiness check never authorizes model
calls. The blinded tool still depends on a trusted preparation receipt and explicit
custody restrictions; style and source-selection clues can remain. Existing packets
retain their original code hashes and require their frozen implementation to be
reused, or a newly identified preparation with the changed tool.

No dependencies, data, providers or models were added. No Neo4j service or persistent
background process was started. Human queues, frozen v1/v2 data, original source/
vector artifacts, previous review outputs and the earlier implementation report
remain unchanged. The conservative project-provider ledger remains at 10,201,771
cumulative tokens; Codex agent work is separate AI usage. Changes stay local on
`review-fixes-2026-10-07`, without push or merge.

## Evidence

The aggregate record is
[`independent_review_2026_10_15_summary.json`](../../../eval/runs/independent_review_2026_10_15_summary.json).
Raw before/after probes, cross-review records and validation outputs are retained
locally under `.cache/independent-review-2026-10-15/` and are unavailable from a
fresh public clone. The earlier [implementation report](review-implementation-2026-10-15.md)
remains the historical record of the first repair round.

Final verification: **677 non-integration tests pass** in 12.70 seconds, with
15 integration tests deselected and one existing Starlette TestClient deprecation
warning. Ruff and all nine cached-artifact checks pass. The root separately reruns
the seven new blinded-review regressions; the other agents cross-check the final
scorer, evidence validator and checkpoint fingerprint. All 81 preserved files and
final reviewed source hashes match. No known actionable finding remains open in
this bounded review. Integration services and live provider behavior were not
exercised; future source-semantic and clinical evaluation remain separate work.
