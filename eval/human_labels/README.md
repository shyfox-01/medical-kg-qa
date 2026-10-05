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

## Text question drafts

Review every row in `eval/datasets/text_v1.jsonl`: question answerability, exact
quote grounding, source URL/chunk provenance, and the required graph-plus-text
combination for `graph_text`. Local `text_graph_gold.jsonl` contains private
PrimeKG-derived gold; do not commit it. Set `review_status` only after human
review. The current automatic text score is strict quote coverage and is
exploratory; a valid paraphrase can fail it.
