# AI source review protocol — 2026-10-09

The user explicitly authorizes multi-agent review because they do not have the
domain expertise to supply the previously requested human labels. This adds an
AI review lane; it never converts AI judgments into human or clinical validation.
Keep existing human queues, datasets, catalog and previous reports unchanged.

## Bounded first round

Two agents independently review the same first 100 historical alias pairs. A
third agent reviews the independent evaluation design and drafts 12 text-only
source-grounded pilot questions. After the blind alias passes, one available
reviewer checks the pilot without seeing its proposed answers first. The root
agent validates evidence and adjudicates conflicts explicitly. No new provider
evaluation, catalog application, download or service startup is included.

After saving both blind first passes, reviewer B searches the existing cached
openFDA labels for additional evidence on all 66 uncertain pairs. The label's own
brand and ingredient fields must identify the alias and exact canonical drug;
the requested-drug filename, existing synonyms and substring matches are not
identity evidence. Mixtures, salts, formulations and conflicting labels remain
explicit limitations. A no-match is not proof of an incorrect alias. This
supplement preserves first-pass judgments and records every searched source hash.

The 100 aliases are a priority sample, concentrated in nine entities and nine
cached MeSH descriptors. They cannot estimate the error rate of the remaining
2,289 flagged pairs or of the full catalog. Use full concept/term identities and
relations from the cached XML, not the flattened synonym list being audited.

## Reviewer dispatch prompts

Both alias reviewers receive a fresh context, the same frozen input packet, the
following shared rubric and a separate output directory. They cannot read the
original flag/verdict fields or one another's outputs during the first pass.
Agent A emphasizes direct terminology equivalence. Agent B independently tests
alternative entities, classes and formulations. Both apply the same decision rules.

> Review every assigned mapping against the supplied original MeSH descriptor,
> concept, term and scope-note evidence. Existing catalog membership is not proof.
> Supported requires explicit exact-alias evidence for this particular entity.
> Unsupported requires positive evidence for a broader class, sibling or different
> identity; absence of a matching identity alone is insufficient. Use uncertain
> for missing evidence or debatable formulation/analogue equivalence. Do not infer
> identity merely from membership in one descriptor, and do not assume all narrower
> terms are wrong. Inspect preferred/narrower/related concepts, moieties and salts,
> endogenous proteins and manufactured products, and sibling compounds. Cite
> verbatim evidence with concept/term IDs. Do not supply patient recommendations,
> invent human credentials or use remembered medical facts to fill evidence gaps.

Each review record must contain the stable input ID, reviewer, origin=`ai_review`,
decision (`supported`, `unsupported`, `uncertain`), relation, exact source excerpts,
rationale, limitation and `clinical_validation=false`. English artifacts only.
No commits or mutations outside the agent's assigned output directory; no provider
calls, downloaded sources, catalog edits or filled human fields. Agents are told
they share a workspace and must preserve one another's work.

The evaluation-review dispatch asks the third agent to audit leakage, correlated
author/judge errors, blinding, answerability, exact gold, safety scoring and what
source verification can establish. Its 12 pilot questions must use cached public
health chunks, varied topics, natural wording, known chunk IDs, verbatim supporting
spans, a bounded reference answer and source URL. It must not read old benchmark
questions/answers, prescribe, or claim human authorship. Status starts as
`ai_draft`; the pilot is not the predeclared 100-case human benchmark.

## Aggregation and evidence checks

Require both reviewers to return each input ID exactly once. Validate source IDs,
quote presence in the corresponding original record and nonempty explanations.
Check concept/term locations, then inspect the proposed relationship itself:
a genuine quotation can still fail to justify an inference. Keep all raw first-pass
judgments and any root-agent adjudication as separate artifacts.

Agreed supported/unsupported decisions are AI consensus proposals. Any disagreement
or uncertainty stays unresolved unless a separate, documented source check resolves
it. Never silently treat the majority as truth or delete aliases from these labels.
Report agreement as reviewer consistency, not accuracy. Fresh agent contexts do
not make their model errors statistically independent; shared-model/source bias
remains. Cached-source verification also does not establish current medical advice.

For the pilot, separate questions and evidence from proposed answers for the second
agent's first pass. Save that pass before revealing the author's answers. Compare
required facts, answer coverage, unsupported additions and source limitations.
Question wording and source selection can still expose intended answers; this
limited blinding reduces answer anchoring, not all dependence. Do not measure the
QA system against these questions during review or tune it from their answers.

All private evidence, dispatch manifests and per-item judgments live under
`.cache/ai-review-2026-10-09/`. Public reports contain aggregates and bounded
examples. Original human attestations remain null. Future software evaluations
may use a separately registered AI-authored, AI-reviewed diagnostic dataset, but
must retain that origin and cannot be reported as human-reviewed performance.
