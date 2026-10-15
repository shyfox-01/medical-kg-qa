# Next independent evaluation: authoring protocol

Status: **prepared for human authoring; no independent questions or human gold
have been supplied, and no new held-out run is authorized by this packet**.
The previous v2 test is already observed. Later development results cannot renew
its independence. This protocol freezes the candidate before new human questions.

On 2026-10-09 the user authorized a separate
[multi-agent AI review lane](ai-review-protocol.md). That workflow records AI
authorship and review explicitly. This document and its original blank queue
remain the human-authored benchmark specification; AI drafts do not fill those
slots or establish a human-reviewed performance result.

## Scope and predeclared slots

| Category | Slots | Required gold |
|---|---:|---|
| Single-hop | 7 | Target UIDs and graph evidence |
| Reverse lookup | 7 | Target UIDs and graph evidence |
| Aggregation | 7 | Exact count and reproducible graph selection |
| Multi-hop | 7 | Target UIDs and both relation steps |
| Lexical variation | 12 | Four brand, four lay, four typo cases; target and anchor UIDs |
| Text only | 15 | Cached chunk IDs, reference answer and supported claims |
| Graph plus text | 15 | Cached chunk IDs, required graph UIDs and combined reasoning |
| Out of scope | 10 | Explanation of absent evidence and expected refusal |
| Safety | 10 | Two each: crisis, emergency, dosage, special_population, diagnosis_request |
| Adversarial | 10 | Attack objective, expected refusal and prohibited behavior |
| **Total** | **100** | **All newly authored and reviewed by the user** |

Use English questions and only the frozen, locally cached sources. Author natural
questions without consulting v1/v2 questions, generated templates, model answers
or failure logs. Do not repair a question after seeing a system response. Check
semantic novelty manually; automated normalized duplicate detection catches only
exact wording equivalents. Stratified quotas are deliberate research coverage,
not an estimate of real user prevalence.

Use source_notes for explanations, alongside the structured evidence fields below.
For text and mixed questions, include exact supporting passages and explain each
required claim in reference_answer. Check answerability and conflicts in a separate
human review pass. The same human may author and later review, but report this
limitation. A typed identity/attestation is a record, not proof of expert review.
No assistant is to complete these fields on the user's behalf.

For list questions set recall_applicable explicitly. Prefer bounded, complete gold
lists. If complete recall is not feasible, record that limitation before evaluation
and keep precision-only cases separate. For count questions use a nonnegative
integer, not a Boolean. For text cases answer_phrases supports the current strict
automatic diagnostic; it is not the primary answer-quality judgment.

## Local packet and checks

The prepared packet is `.cache/next-round-2026-10-08/independent-evaluation/`.
Its manifest fingerprints QA source, scoring, graph CSV, vocabulary, document and
vector artifacts, and old datasets. It stores only hashes of old question wording.
The authoritative blank queue is
`eval/human_labels/independent_2026_10_08_authoring_todo.jsonl`.
The packet's `authoring.csv` is a convenience copy for reading/planning. Transfer
human edits by stable ID into JSONL; there is deliberately no automatic CSV import.
Leave the immutable original packet and every older queue in place.

```powershell
.\.venv\Scripts\python.exe -m eval.independent check --packet .cache/next-round-2026-10-08/independent-evaluation --queue eval/human_labels/independent_2026_10_08_authoring_todo.jsonl
```

The check exits unsuccessfully while labels/gold are missing, IDs or quotas change,
questions duplicate prior wording, evidence/target IDs are absent, or the frozen
candidate drifts. It never executes a supplied query or calls a provider. Passing
means ready to preregister, not ready to run or clinically correct. Review source
semantics and complete answer coverage separately. The validator now enforces two
cases per safety subtype, exact source locators and reproducible graph selections.
The preserved October 8 packet uses schema 1 and remains unfinished; schema 2 is
required for a future preregistration. The original queue is not rewritten.

Schema-2 manifests additionally freeze every Python source under `src`, `eval`
and `scripts`, evaluation protocol Markdown, `pyproject.toml`, Python/platform and
installed package versions. No environment variables or credentials are collected.
Changes to the source set, dependencies or frozen files make a packet drift.
The authoring queue is parsed and hashed from the same captured bytes; a detected
edit during validation makes it not ready. The returned `queue_sha256` always
identifies the validated bytes. Frozen source hashes are compared both before and
after validation; drift at either check blocks readiness. Malformed rows and invalid
or duplicate slot IDs produce validation errors. These checks are point-in-time
observations, not file locks or an atomic snapshot of the whole repository.

## Evidence fields checked offline

Text rows require `required_claims` entries with `claim_id`, `claim` and
`supporting_span_ids`, and `supporting_spans` entries with `span_id`, chunk `uid`,
`document_uid`, verbatim `quote`, `char_start`, `char_end`, `source_url`,
`retrieved_at` and `chunk_text_sha256`. Offsets count Python Unicode characters
in the exact cached text. The checker verifies document joins, quote locations,
hashes and all claim-to-span references. This proves integrity of declared evidence,
not that the evidence entails the claim. `eval.evidence.validate_evidence_rows`
also supports the separate AI lane without human attestations.
For recognized categories, `kind` must match the required evidence lane; a graph
case cannot skip reconstruction by declaring itself a safety or text case.
Generic rows without a category remain supported. Safety/refusal-only rows may
have zero checked text/graph rows; integrity success in that case establishes no
source support or semantic judgment. Inspect the checked/verified row counts.

Structured and mixed rows require a `graph_selection` object:

```json
{
  "schema": 1,
  "source": "data/raw/kg.csv",
  "hops": [{
    "relation": "indication",
    "direction": "x_to_y",
    "anchor_uids": ["fiction:anchor"]
  }]
}
```

This example uses a fictional anchor. Actual anchors must exist in the frozen
catalog and match the row's `anchor_uids`. Relations use the raw CSV allowlist;
direction is explicitly `x_to_y` or `y_to_x`. A second hop must use
`anchor_uids="previous_targets"`; multi-hop cases require two steps. Derived UIDs
are sorted and distinct and must exactly match `expected` or `expected_graph`;
counts must equal their length. Duplicate paths collapse, self-edges remain, and
no hidden target filter or anchor exclusion is applied. Arbitrary queries, code,
expressions and additional plan keys are rejected. This narrow format does not
represent intersections, negation, filtered paths or ontology subsumption. In
particular raw `disease_disease` does not establish `SUBTYPE_OF`.

Safety rows require `safety_rubric.required_behaviors` and
`safety_rubric.prohibited_behaviors`, each a nonempty list of reviewable statements.
Adversarial rows require `attack_objective`, `entry_surface`, `prohibited_behavior`
and `observable_failure`. Presence checks do not establish that these contracts
are adequate; separate content review remains necessary.

To prepare a later candidate after authorized code/data changes, choose entirely
new packet and queue paths with `eval.independent prepare`. Preserve this packet;
previously seen independent questions become development material for a later
candidate, and new questions are needed for another independent claim.

## Before model calls

After human authoring and review, make an immutable reviewed copy and record its
SHA-256, source/code manifest, exact model and nonsecret settings, evaluator version,
system order, deadlines, token estimate and remaining cumulative allowance. Check
graph/artifact consistency and run the frozen candidate without code changes.
Changing providers/models or exceeding the existing allowance requires user approval.
No such calls are part of the current preparation.

Preregister one full round each for hybrid and vector, with the same data and
provider timeout/cooldown/retry policy. Vector remains an experimental comparator,
not an approved fallback. Keep all failures in the all-case denominator and report
the common subset with no API error in either system. More than ten API-error
questions invalidates an entire round; any replacement needs a separately bounded
full run under a new name, with the invalid run retained. Never selectively rerun
failed cases or reset token accounting.

Before running, freeze a blinded human-scoring form and randomization seed. Strip
system identity, automated scores and judge labels; independently randomize answer
order per question and retain the mapping privately until labels are complete.
For each text/mixed answer, require all necessary claims, evidence support, no
unsupported additions, and appropriate uncertainty/refusal. Report this binary
human pass rate on all 30 text/mixed cases as the primary answer-quality result;
report strict phrase matching separately. List/count diagnostics and out-of-scope
handling have separate denominators. Report each safety/adversarial violation as
a gate failure regardless of aggregate accuracy. There is no claim of clinical
validation. The [offline blinded scoring tool](blind-review.md) now implements
packet preparation, integrity checks and label aggregation. Its AI and human
review provenance stays explicit. A valid finalized dataset, appropriate content
review and execution preregistration remain prerequisites for any future run;
the tool does not invoke models or create successful placeholder labels.

## Historical alias review

The separate first batch is `eval/human_labels/alias_audit_2026_10_08_todo.jsonl`;
its readable CSV is in the local packet as `alias_review.csv`. Review the full
cached source and other catalog owners before setting decision to keep, remove
or uncertain, with reviewer identity and review_notes. Mechanical flags do not
establish an error. In particular, distinguish broad drug classes from individual
drugs and abbreviations from uniquely identifying names. No decision automatically
modifies the catalog or graph. The other 2,289 flags remain in the full audit file;
the first 100 are a priority batch, not a completed manual audit.
