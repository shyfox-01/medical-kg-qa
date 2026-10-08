# T5 implementation and dev verification — 2026-10-08

The user authorized continuing after the original T5 stop. Implemented the four
deferred areas using existing cached data and dev-only verification. The original
[v2 test results](v2-results.md) remain a historical snapshot; no test questions
were rerun, no frozen dataset was regenerated, and no human labels were filled.

## Implemented changes

| Area | Change | Evidence and limits |
|---|---|---|
| Brand and consumer names | Added 94 source-attributed aliases to 80 entities: 20 openFDA, 73 MedlinePlus, one MeSH | All additions verified in the catalog and Neo4j; four of five originally catalog-absent dev anchors now link exactly. This does not establish answer accuracy. |
| Population false refusals | Allow explicit impersonal graph lookups, with personal/advice/action cues taking precedence | Fictional mixed-intent controls remain blocked before model/graph calls; all eight dev sensitive-term questions pass the input gate. Other phrasings may still be refused. |
| Planner formatting | Normalize `count` 0/1, true/false strings and optional null; clarify boolean semantics in the prompt | Arbitrary numbers, floats, numeric strings, extra tool arguments and unsafe references remain invalid. This does not fix every possible malformed plan. |
| Provider reliability | Cross-process backoff after timeouts, connection errors, 429 and 5xx, capped at 60 seconds | No automatic retry or hidden replacement answer. Fake-clock tests verify pacing/accounting; two real timeouts remain in the dev result. |

The initial 151-alias preview was not applied. Reviewing source mappings exposed
recursive chemical-class joins, OTC product descriptions and consumer titles
matching existing acronym aliases. Tightened the rules before applying the final
94 additions. Prescription labels must resolve all ingredient names to one drug;
their search-request uid is not identity evidence. Consumer topics must match a
canonical disease title. New cross-label collisions are rejected. A repeat preview
after application proposes zero further additions.

No new download or DrugBank vocabulary was used. The earlier 40 source-coverage
probes remain 39/40, including one unresolved name. Current coverage still depends
on the cached sources; source-provided consumer names are not an expert-reviewed
clinical equivalence table. Historical aliases were not removed or re-adjudicated.

## Catalog and vector synchronization

Backups preserve the old catalog, alias index/matrix, synonym provenance and
unlinked mentions in `.cache/synonyms-20261008-203328/`. Graph MENTIONS were
recomputed from exact linking and verified at 45,636 edges. The alias index now
contains 138,893 rows; 87 new alias texts required embedding computation.

The vector control was refreshed using the same cached model, offline, with two
CPU threads. Only alias additions qualify for this refresh: old catalog and
paragraph prefixes, unchanged canonical fields, complete progress, hashes and
matrix shape are checked before replacement. All previous corpus artifacts are
backed up in `.cache/synonym-corpus-1791462868137259600/`.

- 75 changed entity paragraphs were re-encoded.
- 47,593 unchanged rows retain exactly equal vectors; document rows and all
  relationship text are preserved.
- All 47,668 vectors are finite and normalized (norm range
  0.9999998808–1.0000001192).
- The 20-alias paragraph cap remains; catalog membership alone does not ensure
  a name is included in the vector paragraph.
- All nine artifact checks pass. Both frozen datasets and all seven human queues
  retain their previous hashes. An additional read-only graph check confirms every
  newly applied synonym; the artifact checker alone does not check the live graph.

This incremental operation assumes the same embedding recipe and cached model.
Changes to models, graph facts, documents or canonical names require a full rebuild.

## Development smoke

One phase-3 hybrid run uses the same 38 dev IDs as the earlier smoke: two per
ordinary category and all 20 dev safety/adversarial controls. The dataset has 160
dev questions; these 38 are a diagnostic sample, not a new held-out measurement.
Provider/model/key are unchanged, with a 60-second timeout, two-second ordinary
cooldown, zero SDK retries and cache disabled. The predeclared bounds were 200,000
conservative tokens and 20 minutes; the run finished in 547.42 seconds.

| Dev outcome | Result |
|---|---:|
| Passed | 35/38 (92.11%) |
| Safety controls | 10/10 |
| Adversarial controls | 10/10 |
| Sampled sensitive-term questions | 2/2 |
| Questions with API errors | 2 timeouts |
| Questions with other execution errors | 0 |
| Answer failures without execution errors | 1 |

The remaining answer failure is a dev typo case (`v2-0190`): no candidate was
linked and the system returned no supporting evidence. The two timed-out cases
(`v2-0199`, `v2-0241`) retain their failure records. Both triggered a ten-second
shared backoff. No failed case was selectively rerun. Absence of validation errors
in this small run does not establish that all planning failures are solved.

The changes affect vocabulary, prompts, safety routing and provider scheduling
together. This smoke cannot isolate which change caused any score difference.
There is no new vector end-to-end score and no new test score. Do not interpret
the 92.11% dev result as a revision of the earlier 80.83% hybrid test result.

## Validation, accounting and delivery

Ruff passes. The non-integration suite passes **361 tests**, with 15 integration
tests deselected and one existing Starlette/httpx deprecation warning. The selected
unit tests use fictional entities and fake provider responses. Full synthetic
integration tests were not run against the live research database; graph synonym
and mention checks above were read-only after synchronization.

This smoke made 35 provider calls, reporting 47,088 tokens and conservatively
charging 61,607 tokens. Failed calls without usage retain their reservation.
Cumulative additional task usage is 4,465,963 of the approved 6,000,000 allowance,
leaving 1,534,037; accounting was not reset. No new reservation is unsettled. These
are resource-accounting values, not monetary charges.

All edits remain on `review-fixes-2026-10-07`, committed locally without push or
merge. The evaluator and the owned Neo4j server/launcher have exited; ports 7474
and 7687 were verified closed. Existing invalid runs, raw records, backups and
manual-review queues remain in place. No dependency or global setting changed.

Evidence: [dev summary](../../eval/runs/t5_dev_smoke_summary.json),
[implementation/check aggregates](../../eval/runs/t5_improvements_summary.json),
and [decisions D060–D064](../decisions.md#d060--resume-t5-with-cached-source-aliases-and-bounded-index-refresh-2026-10-08).
Raw records, source previews and process/budget audits remain local under
`.cache/t5-improvements-2026-10-08/` and `eval/runs/`.

| Current snapshot | SHA-256 |
|---|---|
| QA/evaluator source | `d58b477f79df19d43f738a321710308e9366727595a6e6b62fb58acd68c7cf03` |
| Entity catalog | `60208bae51b1ad3b84621c69e261a6ef571c09f6250bea8615e53b81e27e16e5` |
| Vector corpus | `799f9a2dd55a97bfbe92795cebccac4fe32b9ba6b05b59828d09afdafdee2b52` |
| Vector matrix | `313cd5f38442bde6f9b352926f66c5d34a0ef617797b54aeba3735cf9dfe18e2` |

The subsequently authorized [four-item follow-up](next-round-2026-10-08.md) fixes
the dev typo boundary, audits historical aliases, runs all integration tests and
the complete dev split, and prepares new independent authoring materials. This
report preserves the earlier 38-case snapshot and its accounting unchanged.
