# Evaluation: method and results

This page is the short version. Every number links to an aggregate under
`eval/runs/`; the full audit trail (attempts, budgets, hashes, reviews) lives in
[`docs/history/`](history/README.md) and the [decision log](decisions.md).

## Principles

- **Black-box.** The evaluator talks to the system only through its public
  `ask(question, history)` process boundary and never imports QA code. Entity
  normalisation and scoring are implemented separately in `eval/` (D008).
- **Gold from source data.** Expected answers are computed from the PrimeKG CSV
  transform, not from the running Neo4j graph or from model output. For v2, all
  320 gold queries were also executed against Neo4j and matched exactly (D050).
- **Frozen sets, dev/test discipline.** Datasets are generated once and hashed
  (`eval/datasets/MANIFEST*.json`). Rules and prompts are tuned on the dev split
  only; the test split is run once per system version and reported as is.
- **Every case counts.** Failures, refusals and provider errors stay in the
  denominator. When the free LLM endpoint fails (timeouts, HTTP 429), the whole
  round is rerun under a new name instead of re-asking individual questions; a
  round with more than ten API-error questions is invalid (D054, D058).

## Benchmark v2

v1 sampled only entities with 1–15 neighbours, used ontology names and template
wording, and had one multi-hop shape, so it said little about how people ask
(D050). v2 has 400 questions (160 dev / 240 test, seed 2026):

| Category | Questions | What it tests |
|---|---:|---|
| single_hop | 60 | One relation from a common drug or disease ("What is Lynparza used for?") |
| reverse | 30 | Phenotype → drugs/diseases ("Which drugs can cause diplopia?") |
| aggregation | 40 | Exact counts ("How many drugs are indicated for bursitis?") |
| lexical_variation | 60 | US brand names (openFDA), MedlinePlus consumer names ("lazy eye"), typos |
| multi_constraint | 40 | Intersections and exclusions ("…for A but not contraindicated in B?") |
| multi_hop | 50 | Clinical chains ("Which drugs for major depressive disorder interact with melatonin?") |
| multi_turn | 20 | Follow-ups with pronouns ("What are its side effects?") |
| sensitive_terms | 20 | Knowledge questions using words like *chest pain* or *pregnancy* that must not be refused |
| out_of_scope / adversarial / safety | 30 / 25 / 25 | Refusals, prompt injection, crisis/dose/diagnosis requests (v1 controls) |

75% of anchors come from common pools (diseases with a MedlinePlus page, drugs
with an FDA label or 3+ indications). Wording uses 2–4 natural templates per
relation; an LLM rewording pass changed only 28 questions.

**Scoring** (`eval/score.py`) is deterministic: entity-set precision/recall/F1
for lists (lists over 15 items need correct entries plus a partial-list notice),
exact match for counts, explicit refusal for controls, and output checks for dose
instructions, diagnoses and write queries. It checks *which entities* an answer
names, not whether each sentence is true; semantic support is reported as not
evaluated.

## Results on the v2 test split

The first accepted round (2026-10-08, [v2 report](history/reports/v2-results.md),
[paired aggregates](../eval/runs/v2_comparison_summary.json)) scored 80.8% for the graph
hybrid and 32.5% for the pure-vector control; per-category numbers are in the table
below.

The pure-vector control retrieves top-8 passages from the same text plus one
paragraph per entity (its relations and up to 20 synonyms) and answers with the
same generator. Its gap is largest exactly where structure matters — counts,
intersections and multi-hop chains — which is the case for using a graph.

### Final round of the current code (2026-10-16)

After the first round, all changes (source aliases, typo matching, refusal
narrowing, planner normalisation, provider backoff, alias quarantine) were built
and checked on dev only. The current code then ran the test split once, with the
same provider, model and settings. The first rounds are rescored with the same
evaluator (`deterministic-3.7`), which leaves them unchanged
([final](../eval/runs/v2_test_hybrid_final_summary.json),
[first hybrid](../eval/runs/v2_test_hybrid_retry3_rescored_v37_summary.json),
[vector](../eval/runs/v2_test_vector_retry1_rescored_v37_summary.json)).

| Category | n | Hybrid, first | Hybrid, final | Vector, first |
|---|---:|---:|---:|---:|
| single_hop | 36 | 83.3% | **97.2%** | 36.1% |
| reverse | 18 | 83.3% | 77.8% | 16.7% |
| aggregation | 24 | 95.8% | **100%** | 29.2% |
| multi_constraint | 24 | 70.8% | 66.7% | 8.3% |
| multi_hop | 30 | 86.7% | 73.3% | 3.3% |
| multi_turn | 12 | 91.7% | 91.7% | 25.0% |
| lexical_variation | 36 | 47.2% | **69.4%** | 0.0% |
| sensitive_terms | 12 | 66.7% | 75.0% | 33.3% |
| safety / adversarial / out_of_scope | 15 / 15 / 18 | 100 / 100 / 94.4% | 100 / 100 / 100% | 100 / 93.3 / 88.9% |
| **All** | **240** | **80.8%** | **85.0%** | **32.5%** |

The final round has 8 API-error questions (valid under the rule) and no safety
or injection regression. On the 226 questions without an API error in either
hybrid round, the score moves from 188 to 198.

- **Gains** come from surface forms and simple lookups. Lexical variation:
  catalog-present brand names 9/11, absent brand names 3/6, catalog-present lay
  names 8/9, absent lay names 1/5, typos 4/5 (first round: 0/5).
- **Multi-hop drop** (26 → 22 of 30): three failures are consecutive provider
  timeouts; the others are wrong answers from LLM-planned queries. One round
  cannot separate a code effect from model variance.
- **Persistent Cypher errors:** all 7 syntax errors are "drugs indicated for both
  A and B" intersections (6 of them failed the same way in the first round). A
  deterministic intersection template was added afterwards (D082): on dev,
  multi-constraint questions go from 11/16 to 16/16. It has not been run on test.
- One reverse question moved from a template to the planner and failed; this is a
  candidate regression to reproduce on dev.

## LLM backend: cloud vs local (dev, 2026-10-16)

The free cloud `glm-4.5-flash` and two local open-weight models in Ollama
answered the full v2 dev split on the same code (D083, D084):
[GLM-4.7-Flash](../ollama/glm-4.7-flash.Modelfile) (MIT, 30B/3B-active MoE, Q4_K_M,
weights pinned by digest) and [qwen3.5:9b](../ollama/qwen3.5-9b.Modelfile) (Q4_K_M).
Summaries: [cloud](../eval/runs/llm_compare_dev_glm_summary.json),
[GLM-4.7 local](../eval/runs/llm_compare_dev_glm47_local_summary.json),
[qwen local](../eval/runs/llm_compare_dev_local_summary.json).

| Category | n | glm-4.5-flash cloud | GLM-4.7-Flash local | qwen3.5:9b local |
|---|---:|---:|---:|---:|
| single_hop | 24 | 100% | 79.2% | 91.7% |
| reverse | 12 | 100% | 100% | 100% |
| aggregation | 16 | 100% | 100% | 100% |
| multi_constraint | 16 | 93.8% | 93.8% | 81.3% |
| multi_hop | 20 | **80.0%** | 60.0% | 15.0% |
| multi_turn | 8 | 100% | 75.0% | 87.5% |
| lexical_variation | 24 | 75.0% | 58.3% | 62.5% |
| sensitive_terms | 8 | 87.5% | 75.0% | 87.5% |
| safety / adversarial / out_of_scope | 10 / 10 / 12 | 100 / 100 / 100% | 100 / 100 / 100% | 100 / 80 / 91.7% |
| **All** | **160** | **92.5%** | **82.5%** | **77.5%** |
| API-error questions | | 2 | 0 | 0 |
| Median latency | | 7.8 s | 3.3 s | 3.6 s |

Against the cloud model, GLM-4.7-Flash loses 20 questions and wins 4; qwen3.5:9b
loses 26 and wins 2. GLM-4.7 plans multi-hop questions far better than the 9B
model (12/20 vs 3/20). Both local models lose about eight questions where the
retrieved evidence was identical to the cloud run but the written answer left out
entities, and some to invalid plans. The 9B model's adversarial misses are
fail-closed errors, not unsafe queries. The cloud model remains the reported
system; the local ones are faster, private, never rate-limited and pinned by
weight digest, but weaker. Prompts were developed against GLM-4.5, which may
favour it. The free cloud endpoint of GLM-4.7-Flash was too overloaded to measure
(3 of 21 calls succeeded).

## Known failure modes

- **Surface forms.** Names missing from the catalog still fail most of the time
  (4/11 in the final round); coverage depends on the cached MeSH, openFDA and
  MedlinePlus sources (D049, D060). Typo matching covers one edit in long drug
  names (D065).
- **Generated Cypher and plans.** Invalid plans fell from 10 to 0 after boolean
  normalisation (D062). Intersections now use a template (D082); exclusions and
  multi-hop chains still depend on free-form generated Cypher.
- **Provider availability.** The free endpoint produced four invalid rounds
  before a valid one; timeouts and rate limits are paced with a shared backoff
  but not retried (D063). A local model avoids this but scores lower (D083).

## Threats to validity

- One round per system version; no repeated-run variance on test.
- The final run is the second use of the test split. All changes between the
  two were developed and checked on dev only, but the split is no longer fresh.
- Mostly template wording; small subgroups (5 typo questions on test).
- Entity-level scoring cannot detect a wrong relation stated about the right
  entities; there is no human or clinical review of answers yet.
- Gold reflects PrimeKG; it inherits that source's gaps and errors.

## Not done (optional next steps)

Human review queues in `eval/human_labels/` (judge calibration, extraction checks,
text drafts, alias audit) and a human-authored independent test set
([protocol](evaluation/independent-evaluation.md)) are prepared but unlabelled.
Tooling for blinded human review is documented in
[`evaluation/blind-review.md`](evaluation/blind-review.md).
