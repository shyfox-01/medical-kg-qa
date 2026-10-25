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

These numbers use `deterministic-3.7`. Rescored offline by `deterministic-3.8`
(D089, a shared name credits only the entity whose own name it is), the same saved
outputs give 209/240 (87.1%) final, 197/240 (82.1%) first hybrid and 80/240
(33.3%) vector ([final](../eval/runs/v2_test_hybrid_final_rescored_v38_summary.json)).

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

## Stage-wise diagnosis and fix rounds (dev, 2026-10-17)

A pass rate says how often an answer is right, not where a wrong one failed.
`eval/stages.py` scores each recorded question per stage from gold the v2 dataset
already carries (anchor uids, template intent, expected entities and counts),
without model calls, and attributes a failure to generation when the evidence
contained the gold entities, otherwise to the first failing earlier stage. A fix
counts only through the per-question ledger (fixed / still failing / regressed); a
repeated identical Gemma 4 run had no pass/fail flips, so its ledgers measure the
changes rather than noise.

Each round below was diagnosed on dev and applied to every model; scores use
`deterministic-3.8` (D089).

| Round | What the diagnosis found | Change | Cloud GLM-4.5 | Local Gemma 4 |
|---|---|---|---:|---:|
| D083 code | — | — | 151 | 129 |
| D085 | brand names and intersections denied | name mapping and query descriptions in the evidence | 149 | 141 |
| D086 | generated-query rows denied; relation words blocked templates | descriptions for generated queries; faithful-reporting rule; linker | 150 | 146 |
| D087–D088 | incomplete lists; truncated group labels; "drugs that cause X" and "when not to use" routing | completeness guaranteed in code; routing fixes | **154** | **155** |

Final stage metrics on identical code:

| Stage | Cloud GLM-4.5 | Local Gemma 4 |
|---|---:|---:|
| Linking (gold anchors linked) | 99.2% | 99.2% |
| Routing (gold template intent, 92 questions) | 98.9% | 98.9% |
| Evidence sufficient | 98.4% | 99.2% |
| Answer correct given sufficient evidence | 96.8% | 96.9% |
| Passed | 154/160 | 155/160 |
| Median latency | 6.9 s | 4.0 s |

Remaining Gemma failures: a brand name absent from the catalog (Rubraca), two
answers naming two-character gene symbols the scorer cannot extract (AR, F2), an
acronym shared by two diseases (CHS), and one list completed after the run by the
uid-based check (offline replay: 156/160). The cloud model fails the same three
catalog/scorer questions plus a Cypher syntax error, one denied answer and a
provider timeout. None of Gemma's remaining failures is a model error, but the 160
dev questions were used for every round: the comparison needs a fresh held-out
split.

## Benchmark v3: capability coverage and a sealed test (2026-10-17/18)

v2's dev split was used for every fix round and several promised functions had no
questions, so v3 ([design](evaluation/v3-design.md), D091) is a CheckList-style suite:
minimum-functionality tests for every promised capability, invariance variants
(wrappers, casing, punctuation, catalogued synonyms), directional pairs (treat vs
cause, added exclusion, list vs count) and boundary probes, with anchors disjoint from
v1 and v2. Each fix round uses a fresh batch: run unchanged first (the unbiased
first-look score), diagnose per stage, fix design defects with general rules, verify
per question and on the regression sets. A sealed test, reworded in part by an
independent model (qwen3.5:9b), runs once per system at the end.

Fix rounds on the local Gemma 4 (in scope, scorer 3.12):

| Batch | Before fixes (first look) | After fixes |
|---|---:|---:|
| b1 (186 in scope) | 167 (89.8%, CI 84.6–93.4) | 183 (98.4%) |
| b2 (186 in scope) | **182 (97.8%, CI 94.6–99.2)** | 184 (98.9%) |

The b1 first look, 8 points below the tuned v2 dev score, measured the dev
overfitting; the b2 first look shows that the round-1 fixes generalise. Defects found
this way: safety gaps (dosing frequency, collapse, children by age), Spanish, French
and German let through, negated use ("must not be given", "unsafe") answered with
indications, relation wordings the router did not know, same-label duplicate names
guessed instead of clarified, and several scorer ambiguities (D092, D093).

Sealed test, once per system on identical code ([cloud](../eval/runs/v3_test_glm45_cloud_summary.json),
[local](../eval/runs/v3_test_gemma4_local_summary.json)):

| | glm-4.5-flash cloud | Gemma 4 local |
|---|---:|---:|
| In scope (260) | 247 (95.0%, CI 91.6–97.1) | 246 (94.6%, CI 91.2–96.8) |
| Template wording (100) / reworded (57) | 95 / 52 | 95 / 50 |
| Single relations (68) | 67 | 65 |
| Two-relation shapes (28) | 25 | 27 |
| Brand, consumer and typo names (23) | 17 | 15 |
| Counts, negatives, yes/no, directional, multi-turn | 100% | 100% |
| Safety, injection, non-English, non-medical | 100% | 100% |
| Invariance consistency | 100% | 100% |
| Boundary graceful failure | 83.3% | 100% |
| Median latency | 6.4 s | 2.7 s |

Paired, the systems disagree on 15 of 272 questions (7 vs 8; exact McNemar p = 1.0).
Remaining in-scope failures are catalog gaps (five each), unseen wordings for the local
model's router and denied rows for the cloud model (D094).

### Failure severity

Pass rates do not distinguish an explicit decline from an answer containing wrong
items. `eval.severity` classifies saved v3 results using the ordered rules in D095;
only questions with `scope == 'in'` enter the counts and denominators. A false item
means an item outside the knowledge graph's answer, not a clinical judgement.
The combined `answers with a false item` row is `partly_wrong + wrong`, with a
Wilson 95% interval over all recorded in-scope questions. Policy breaches are
reported separately.

Sealed test (260 in-scope questions per system), rescored offline with scorer 3.12:

| Severity | cloud | local |
|---|---:|---:|
| correct | 247 (95.0%) | 246 (94.6%) |
| declined | 7 (2.7%) | 6 (2.3%) |
| incomplete | 0 (0.0%) | 4 (1.5%) |
| partly_wrong | 2 (0.8%) | 3 (1.2%) |
| wrong | 4 (1.5%) | 1 (0.4%) |
| policy_breach | 0 (0.0%) | 0 (0.0%) |
| answers with a false item | 6 (2.3%, CI 1.1%–4.9%) | 4 (1.5%, CI 0.6%–3.9%) |

The pass rates are statistically indistinguishable (95.0% vs 94.6%, paired test
above), but the cloud system has four answers whose items are mostly wrong,
listing the union of two sets when their intersection was requested; the local
system has one mostly-wrong answer. These counts describe the saved runs, not
evidence of a population-level difference in severity. The other failed answers
are declines (seven cloud, six local) or incomplete answers (zero cloud, four local).

Local diagnosis batches (186 in-scope questions per run); `fixed` denotes the saved
`fix2` run, after both fix rounds:

| Severity | b1-first | b1-fixed | b2-first | b2-fixed |
|---|---:|---:|---:|---:|
| correct | 167 (89.8%) | 183 (98.4%) | 182 (97.8%) | 184 (98.9%) |
| declined | 2 (1.1%) | 1 (0.5%) | 2 (1.1%) | 2 (1.1%) |
| incomplete | 2 (1.1%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| partly_wrong | 6 (3.2%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| wrong | 3 (1.6%) | 2 (1.1%) | 2 (1.1%) | 0 (0.0%) |
| policy_breach | 6 (3.2%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| answers with a false item | 9 (4.8%, CI 2.6%–8.9%) | 2 (1.1%, CI 0.3%–3.8%) | 2 (1.1%, CI 0.3%–3.8%) | 0 (0.0%, CI 0.0%–2.0%) |

The first batch had six failed safety/refusal cases before fixes and zero after
fixes. These post-fix results reuse the diagnosis batches; they are regression
measurements, not a fresh held-out test.

Reproduce both tables from saved outputs without model or graph calls:

```bash
python -m eval.severity eval/runs/v3_test_glm45_cloud_round1.jsonl eval/runs/v3_test_gemma4_local_round1.jsonl --dataset eval/datasets/structured_v3_sealed.jsonl --rescore --names cloud local
python -m eval.severity eval/runs/v3_b1_gemma4_local_round1.jsonl eval/runs/v3_b1_gemma4_local_fix2_round1.jsonl eval/runs/v3_b2_gemma4_local_round1.jsonl eval/runs/v3_b2_gemma4_local_fix2_round1.jsonl --dataset eval/datasets/structured_v3.jsonl --rescore --names b1-first b1-fixed b2-first b2-fixed
```

## Real consumer questions: TREC 2017 LiveQA (2026-10-24)

Every earlier question was generated. To see how the system behaves on questions
people actually send, the 104 consumer health questions of the TREC 2017 LiveQA
medical test set (sent to the US National Library of Medicine; CC BY 4.0) were
turned into a benchmark (D097): each question in two wordings, the user's own
message and NLM's short summary. Question type, focus and keywords come from NLM's
manual annotations; entities are matched to the catalog exactly, not by the
system's own linker; gold comes from the knowledge graph. An independent reviewer
re-derived all 104 classifications and gold answers from the raw files with zero
mismatches.

**Scope.** Only 5 of the 104 questions are a single graph lookup or pair (2 yes/no
questions and 3 dosage questions that must be refused). Most real questions are
compound, personal, or ask for something the graph does not record (diagnosis,
prognosis, storage, research, comparisons). The in-scope pass rate is therefore not
an accuracy figure (a system that refuses everything would pass 8 of 10 rows); what
this set measures is coverage and behaviour.

**Entity coverage.** 53 of 118 annotated entities (44.9%) match a catalog name or
synonym exactly: diseases 30/72, drugs 23/43. Real users write "ear wax", "leg
cramps", "Jock itch", misspell drugs ("Gabamentine", "effextor") and use classes
("NSAIDS"). Coverage of consumer wording, not graph reasoning, is the first
bottleneck on real questions.

**Behaviour** (local Gemma 4; "after" includes D100–D103 and the RxNorm aliases):

| | Before | After |
|---|---:|---:|
| In-scope rows passed (of 10) | 7 | 9 |
| Out-of-scope and catalog-gap rows (198): declined | 98 | 112 |
| answered | 78 | 67 |
| refused by the safety gate or asked to clarify | 17 | 9 |
| error | 5 | 10 |
| Answers containing dosing content | 0 | 0 |

Before the fixes, 77 of the 78 answers named only entities present in the
retrieved evidence. A language-model rating of those answers (one rater, not human
labels) found 25 directly relevant, 42 partly relevant and 11 off-topic; 15 of
the "answered" rows were declines the status classifier missed and 2 were empty
after verification, both fixed in D102 (hence more declines after). Off-topic
answers come mostly from planner queries that do not match the question, whose
rows the completeness guard then reports faithfully. The extra errors after are
3 model timeouts and 4 generated queries rejected by the Cypher guard; rerun on the
same code, 3 of those 4 passed, so generated Cypher varies from run to run on long
real messages (the earlier zero-flip noise baseline was measured on short template
questions).

**Safety gate on real wording.** Before D103, 22 rows were refused by the safety
gate: 11 appropriately (dose, tapering, timing, allergy questions) and 11 only
because the question mentioned a dose ("Zolmitriptan 5mg … contain gluten?",
"Dicyclomine 20mg, phentermine … adverse effect?", "low dose naltrexone") or a
population. One dose question was missed ("50,000 IUs per week"); IU and units were
added to the dose units (D100).

## RxNorm brand names (2026-10-24)

RxNorm Current Prescribable Content (NLM, no licence required) maps brand names to
ingredients. 1,901 single-ingredient brands were added as aliases of 963 catalog
drugs (D099–D101). Two independent reviews shaped the change:

- 45 proposed aliases were harmful: wrong mappings (Hextend, K-Phos) and ordinary
  phrases or names that would link inside unrelated questions ("Morning After",
  "P & S", "Terrell"); they are excluded.
- Every long brand name became a target of the linker's single-edit typo
  correction ("medicine" → Medicone). RxNorm brands are therefore exact-only
  aliases: they link and score only by exact match, never through typo, fuzzy or
  vector matching. The cost is that misspelt brands are not corrected.
- An existing catalog error surfaced: MeSH's hydroxyethyl-starch descriptor had been
  attached to Pentastarch; 11 of its 13 synonyms are quarantined.

With the previous catalog, the new code links all 1,450 benchmark questions and
rescores all 1,102 saved answers identically; with the aliases, linking changes
for exactly four questions, each naming the brand. Measured on the fresh batch b3,
generated and run before the change (D098):

| | Before | After |
|---|---:|---:|
| b3 in scope (182) | 170 (93.4%, CI 88.8–96.2) | 172 (94.5%) |
| v3 b2 in scope (186), regression | 184 | 185 |
| v2 brand questions (Tyenne, Abrilada, Rubraca) | 0/3 | 3/3 |

Both b3 fixes are brand-name questions (Nufymco, Ruxience); no question regressed.
The b3 baseline also confirmed the router's weakness on unseen wordings: 5 of its
16 failures are routing ("What is the purpose of …", "What specific forms of … are
documented?").

## Partial answers with a safety notice (2026-10-24)

D103 replaces the whole-question safety gate: crisis, emergency, diagnosis requests,
personal population advice, personal medication decisions and dose-only requests
stay blocked before any model call; a question that only mentions a dose, mixes a
dose request with a knowledge question, or asks impersonally about a condition in a
population is answered from the graph behind a fixed notice. Against the old gate,
no decision changes on any generated benchmark (all 83 blocked questions stay
blocked); 11 LiveQA rows move to answered-with-notice.

On a frozen caveat benchmark (64 template questions, anchors disjoint from every
earlier benchmark), the local system passes 62: all 20 must-block questions are
blocked, all 44 caveat answers lead with the notice and contain no dose, and the
two failures are "Can a low dose of X be used to treat Y?" questions that the
planner did not resolve (a routing gap, not a safety one). On LiveQA the 11
changed rows gave 1 correct yes/no answer, 6 declines with the notice, 3 output-guard
refusals (the answer repeated "5mg tablets" from the question) and 1 off-topic
list; safety refusals fell from 22 to 15 with no dosing content in any answer. The
caveat questions are templates written alongside the rules, so they show that the
mechanism works end to end; the LiveQA rows are the real-wording check.

## Personal medication decisions and confirmed names (2026-10-25)

D104 blocks personal medication decisions that mention no dose ("Should I stop
taking X?", "What can I take for Y?") and answers "Can I take A with B?" as an
interaction question behind a notice. No safety decision changes on any generated
benchmark, and router decisions are identical on all 1,334 routable questions.

D105 replaces silent name correction. On the 42 generated questions whose names
are affected, 26 are answered with a visible "read as" note (25 pass, one more than
before) and 14 misspellings are asked back; every suggestion contains the intended
entity (14/14). Eight of those had been answered through silent correction and now
need one confirmation, six had failed and now get the right suggestion, and one
consumer-term question ("pinworms") regresses. On real LiveQA messages, vector
matches of ordinary words ("hands", "Ear", "clear") no longer become anchors.

D106 checks exact matches that cover only part of a phrase ("jock itch" → the gene
ITCH, "sleep paralysis" → Paralysis): the answer model chooses among catalog
entries, and a different choice is asked back. No generated benchmark question
triggers it (0 of 1,445). On LiveQA 19 of 208 rows trigger and 14 are asked back;
10 of those had been refused or had failed, and 6 now offer a better entry
(temporal arteritis for "giant cell vasculitis", pruritus for "facial itch"). Three
text-set questions now need one confirmation. These LiveQA rows were used to set
the rules.

D107 matches names typed with a missing or extra space when one of the joined words
is unknown. On generated questions with the anchor name perturbed, merged names are
found 433/443 times (235 before) and split names 271/278 (156 before); linking is
unchanged on all 1,573 non-sealed questions, and on 55,163 correctly spelled source
sentences it fires only on real spacing variants.

## Known failure modes

- **Surface forms.** Names missing from the catalog still fail most of the time
  (4/11 in the final round); coverage depends on the cached MeSH, openFDA and
  MedlinePlus sources (D049, D060) and, for brands, RxNorm (D099–D101, exact match
  only). On real questions only 45% of annotated entities match the catalog;
  consumer disease names and misspellings are the main gap. Typo matching covers one
  edit in long drug names (D065).
- **Unseen wordings.** Router rules cover the phrasings seen during development;
  on fresh questions, phrasings such as "What is the purpose of X?" fall to the
  planner, which does not always recover them (5 of 16 b3 failures).
- **Run-to-run variation on long questions.** Generated Cypher for long, messy real
  messages varies between runs; the guard rejects some of these queries.
- **Generated Cypher and plans.** Invalid plans fell from 10 to 0 after boolean
  normalisation (D062). Intersections now use a template (D082); exclusions and
  multi-hop chains still depend on free-form generated Cypher.
- **Provider availability.** The free endpoint produced four invalid rounds
  before a valid one; timeouts and rate limits are paced with a shared backoff
  but not retried (D063). A local model avoids this but scores lower (D083).

## Threats to validity

- v3 questions come from one generator; LLM rewording covers part of the sealed test
  and scores 6–8 points lower, so wording generalisation is only partly measured.
  The only human-written questions are the 104 LiveQA questions, of which 5 are
  single graph lookups; their failures were used to design D100–D106, so LiveQA is
  no longer a fresh measure of those changes.

- Every fix round in D085–D088 was diagnosed on the same 160 dev questions; dev
  scores after these rounds overstate performance on new questions.

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
