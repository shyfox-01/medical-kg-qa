# Human review instructions

All queues contain research outputs and await human review. Do not treat an LLM
confidence score or a matching database edge as clinical validation.

## Sentence judge calibration

`judge_calibration_todo.jsonl` contains 100 actual sentence claims sampled with seed
42 from text-question draft answers and available system responses. The sampling
unit is a sentence, so several items may concern one of the 80 draft questions.
`claim_origin` distinguishes draft answers from system responses; only real system
responses have a `trace_id`. Review each sentence against the attached evidence.

Set `human_supported` to `true` only if the complete sentence follows from the
evidence. Set it to `false` for unsupported details, contradictions or entity
substitutions. Use `null` and an optional `human_note` when undecidable. Do not use
outside clinical knowledge to repair the evidence. To reduce anchoring, hide
`judge_supported` and `judge_reason` during the first pass. Set `review_status` to
`reviewed`. Preserve ids and original sentences.

Calculate comparison only after all human and judge labels are present:

```powershell
python -c "from pathlib import Path; from eval.judge import agreement; print(agreement(Path('eval/human_labels/judge_calibration_todo.jsonl')))"
```

Until then, every judge result is **uncalibrated**. Agreement and Cohen's kappa are
comparisons to this human review, not proof of medical correctness.

## Extracted relationships

`extraction_review_todo.jsonl` contains up to 30 seed-42 sampled unique linked
assertions, their source chunks, verbatim quotes, entity uids and extraction
metadata. Set `human_supported` after reading the complete source passage, and
`human_linking_correct` after checking each linked entity. Record ambiguity,
class-to-drug substitutions, hypothetical language and conflicts in `human_note`.
Keep `confidence` unchanged: it is an uncalibrated model estimate. The review
queue does not itself approve a relationship for clinical use.

The cached corrective repair also creates `extraction_repair_review_todo.jsonl`.
Its 18 assertions failed the stricter quote/current-identity check and are
quarantined outside the current graph. Read the supplied quote and complete
contexts, then assess both support and endpoint identity. Preserve original
metadata and record your decision in `human_supported` and `human_note`.
Review does not automatically reload an assertion. The original 30-item queue
is preserved as a historical artifact; some of its assertions may now be
quarantined. Use the corrective report when checking current graph membership.

## Text question drafts

Review every row in `eval/datasets/text_v1.jsonl`: question answerability, exact
quote grounding, source URL/chunk provenance, and the required graph-plus-text
combination for `graph_text`. Local `text_graph_gold.jsonl` contains private
PrimeKG-derived gold; do not commit it. Set `review_status` only after human
review. The current automatic text score is strict quote coverage and is
exploratory; a valid paraphrase can fail it.

## Blind copies and completion audit

`python -m eval.human_review --prepare-blind` creates local `*_blind_todo.jsonl`
copies without judge labels/reasons or model confidence. Existing copies and
original queues are not overwritten. Review those copies first, then transfer
only human decision fields back to the corresponding original records by stable
id. The original judge labels are needed for agreement calculation. Run
`python -m eval.human_review` to audit remaining work and calibration status.
The tool never creates human labels. Do not commit any of these private/local
review queues; the existing ignore rule includes the blind JSONL files.

After a human has filled the blind copies, transfer decisions with:

```powershell
python -m eval.human_review --apply-blind --output eval/runs/human_import_summary.json
```

The importer checks stable ids and unchanged evidence, accepts only boolean/null
decisions and bounded human notes, and saves hash-verified originals in
`.cache/human-review-import/` before replacing a source file. All queues are
validated before import; each file replacement is atomic. Temporary replacements
stay inside the same ignored cache, and source drift is checked before replacement.
Concurrent writers are unsupported. A filesystem failure
between queues can leave a partial import; rerunning safely completes it. No
graph assertion is automatically approved or loaded. Unlabelled copies create no
decisions, and incomplete judge labels remain uncalibrated.
