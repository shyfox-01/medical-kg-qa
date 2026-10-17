# Benchmark v3: capability coverage, perturbations and a sealed test

v2 measured common usage, but after several fix rounds on its 160 dev questions its
dev score overstates performance on new questions, and several promised functions
had no questions at all. v3 is a behavioural test suite in the style of CheckList
(Ribeiro et al., ACL 2020): every promised capability gets minimum-functionality
tests, and perturbations check that answers stay the same when they should
(invariance) or change as expected when they should (directional). Gold always comes
from the PrimeKG CSV transform, never from Neo4j or QA code (as in v1 and v2).
Decision: D091.

## Scope: what the system promises

**In scope (counted in the pass rate).** English questions, one sentence or a
follow-up turn, about at most two named entities and at most two relations (one hop
plus a constraint, or two hops). Entities may be named by canonical name, catalogued
synonym, catalogued US brand name or consumer term, or, for drug names of eight or
more letters, with one adjacent-letter swap. Answers are entity lists, counts or
yes/no; a question whose correct answer is "the graph records none" must be answered
without naming entities; an unknown or ambiguous name must lead to a clarification
or refusal, not a guess; crisis, emergency, dosage, diagnosis and special-population
requests, prompt injection, non-medical and non-English questions are refused.

**Boundary (reported separately, not in the pass rate).** Three named entities,
misspelt disease names, two-letter typos in drug names. Correct answers count, but
the measured property is graceful failure: an answer either is correct or names no
wrong entity.

**Not tested.** Conflict notes between PrimeKG and FDA claims (their gold would
come from the FDA extraction, not the CSV), questions answered only from document
text (see the text benchmark), explanations and comparisons ("why", "which is
better"), and human-written questions.

## Test types

| Type | Purpose | Gold |
|---|---|---|
| MFT | one capability, random anchors | CSV |
| INV | the base question rewrapped (politeness, casing, missing question mark, catalogued synonym); the answer must not change | the base question's gold |
| DIR | a controlled change with a known effect: treat vs cause on a same-name Disease/Phenotype pair, an added exclusion, list vs count | CSV, per variant |
| BOUNDARY | beyond the promised scope | CSV; graceful failure |

## Capabilities (MFT)

Single relations (all 17 template intents, both directions), counts, the seven
two-relation shapes, brand names, consumer terms, drug-name typos, follow-up turns,
knowledge questions using sensitive words, pairwise interaction yes/no (both answers),
negative questions (single relation, intersection), unknown names, ambiguous names,
the five safety categories, prompt injection, non-medical and non-English questions.
Safety, injection and out-of-scope questions are generated from templates with
random entities and wrappers, not taken from the fixed v1 controls.

## Scoring (scorer 3.9)

New kinds: `none` passes when the answer names no entity of the requested type;
`yesno` passes when a recorded interaction is affirmed with the partner named, or an
unrecorded one is not affirmed; `clarify` passes when the system refuses or asks for
clarification and names no target entity. Summaries add Wilson 95% intervals,
per-capability and per-test-type rates, invariance consistency (perturbed answer
passes exactly when its base passes) and the boundary graceful-failure rate.
`eval.compare` gives a paired comparison of two systems on the same questions (exact
McNemar test on discordant questions).

## Data protocol

One generation (new seed, anchors disjoint from v1 and v2 and between parts):

- diagnosis batches `b1`, `b2`: one per fix round; run first without changes (the
  first-look score is the unbiased number), then diagnose and fix design defects
  with general rules only;
- regression set: v2 dev plus used batches; a fix must not regress it;
- sealed test: written to its own file whose hash is recorded and whose contents are
  not inspected; its questions are reworded by an LLM (with validation) so that
  routing rules written while fixing cannot match its wording; run once per system
  with `--final`.

A round stops the fix cycle when its first-look score is within the confidence
interval of the post-fix score and the remaining failures are model limits, data
gaps or scorer limits.
