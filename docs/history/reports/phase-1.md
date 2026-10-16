# Phase 1 — English structured baseline v0

Implemented ontology parsing, canonical CSV filtering, deduplication and MONDO orientation; 10,000-row UNWIND loading, uid constraints, English fulltext and 384-dimensional vector index. Added exact/fuzzy/vector candidate linking, parameterized intent templates, bounded JSON planner, guarded Text2Cypher with two repair retries, English answer composition, safety rules, four-turn resolution, TTL cache and CLI/stdio boundary.

| Node | Count |
|---|---:|
| Drug | 7,957 |
| Gene | 9,811 |
| Disease | 15,774 |
| Phenotype | 9,433 |

| Relation | Count |
|---|---:|
| TARGETS | 25,653 |
| CONTRAINDICATED_FOR | 30,675 |
| INDICATED_FOR | 9,388 |
| OFF_LABEL_FOR | 2,568 |
| INTERACTS_WITH | 1,336,314 |
| HAS_PHENOTYPE | 150,317 |
| ASSOCIATED_WITH | 80,411 |
| SUBTYPE_OF | 20,626 |
| HAS_SIDE_EFFECT | 64,784 |

CSV rows: 8,100,498; excluded: 4,659,026; duplicate/reciprocal rows removed: 1,720,736. Node and relationship counts matched an independent CSV recomputation in the integration test.

Validation: 36 unit tests and 2 integration tests passed; ruff passed. Three independent five-question live CLI smoke rounds are saved in `eval/runs/phase1_smoke_summary.json`. This is availability/chain validation, not a frozen benchmark score. The full stratified dataset and v0 test scores belong to phase 2. Cache is disabled.

Known issues: occasional 30-second provider timeout; failed calls remain recorded. A declared optional property absent in v0 initially triggered EXPLAIN false rejection and was repaired. Candidate embeddings are being computed over 120,896 aliases with bounded CPU; completion is checked later, and no vector-linking measurement is claimed here. Prior Chinese scores are incomparable.

Deviations: full test-set repetition is unavailable before the phase-2 generator exists, so this phase runs three external smoke rounds. Default special-population safety responses are conservatively blocked. See decisions D004–D007.
