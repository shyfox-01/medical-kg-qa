# Offline blinded answer review

`python -m eval.blind_review` prepares a frozen review packet from **already
authorized cases and exactly two complete sets of saved outputs**. It never runs
QA, requests a provider, downloads evidence, creates human labels or establishes
permission to run an evaluation. This implementation has only synthetic offline
tests; no new system-performance result follows from it.

Use this tool after the source and required-claim checks described in the
[independent evaluation protocol](independent-evaluation.md). Source hashes and
reviewer attestations do not prove the source's interpretation, medical truth,
reviewer expertise or statistical independence. The original human queues and
historical runs remain separate and unchanged.

## Files and custody

Prepare explicitly supplied repository-local input files in a **new** location.
The tool does not search datasets, old outputs, human queues or cached sources.
All inputs, output directories, returned labels and summaries must stay inside the
repository. Public and private directories must be separate, non-nested and new;
existing files are never replaced. Failed preparation may leave partial new
directories after an I/O failure; inspect and preserve them, then choose new names.

| Public reviewer files | Private custodian files |
|---|---|
| `packet.jsonl`: opaque case IDs, question, necessary claims, source text, required safety behaviors, A/B answers and hashes | `mapping.json`: original case/source/claim/behavior IDs, origin/category, randomized assignment, seed, declared identity tokens/clues, raw-answer/output hashes, response-failure reasons |
| `rubric.json`: schema, rubric ID and instructions | `manifest.json`: all input file hashes, code hash, public packet/rubric hash, mapping hash, runtime hash and counts |
| No labels are generated | `environment.json`: Python version, executable, platform and installed package versions |

Give the reviewer **only** the public directory. Keep the private directory,
original output files, preparation receipt and eventual unblinded summary out of
the reviewer's context. Filesystem placement alone is not an access control:
agents sharing the checkout must receive explicit read restrictions or an isolated
copy. In particular, do not send the whole parent directory to the reviewer.

Save the `manifest_sha256` printed by `prepare` in a trusted preregistration or
custody record. `check` and `summarize` require that digest, rather than trusting a
digest read anew from a potentially modified manifest. These hashes detect drift
against that receipt; they are not signatures or proof of authorship.

## Input adapter

The adapter has its own strict required fields. It does not silently convert a
readiness queue or an existing run summary. Make a separately authorized copy and
record the conversion and source artifacts. Extra case/output metadata is excluded
from the public packet, but retained in the original input file's hash.

Each case JSONL row has:

- `id`: unique stable string; duplicate question wording is also rejected.
- `question`: nonempty frozen question.
- `origin`: `ai_authored`, `human_authored` or `synthetic`. This is provenance as
  declared by the custodian, not authenticated authorship.
- `required_claims`: nonempty list of `{ "claim_id": "...", "claim": "..." }`.
  These field names match the source-review pilot. Its `supporting_span_ids` may
  remain in the private input but do not replace full review context.
- `contexts`: list of `{ "id": "...", "text": "..." }`. Include the actual
  frozen source text needed to inspect predicates, qualifiers, contradiction and
  omissions. Original paths, URLs, UIDs, titles and retrieval metadata are not
  copied into public fields. The custodian must verify those original locators
  against the separately frozen evidence package.
- `safety_expectations`: list of `{ "id": "...", "text": "..." }` describing
  each case-specific required or prohibited behavior. An empty list explicitly
  means safety is not assessed for that case, never that it passed safety review.
- Optional `category`: retained privately for later category-specific reporting.

Keep the complete question, source text, claims and safety requirements unchanged
after viewing responses. The tool requires at least one claim per case and accepts
at most 10,000 cases per package. A safety/refusal case can express the required
refusal or support behavior as a claim, with finer requirements in
`safety_expectations`. The packet's case hash binds all these public fields.

Each of the two output JSONL files must contain every case exactly once:

```json
{"id":"fixture-1","answer":"Widget 1 is red. [cache:widget-1]","response_status":"completed","cited_context_ids":["cache:widget-1"]}
```

`response_status` is `completed` or `failed`. A completed response must have a
nonempty string answer and no nonempty `failure_reason`. A failed response must
have a string answer (possibly empty), a nonempty `failure_reason` and a list of
`cited_context_ids` (possibly empty). Preserve any partially displayed answer on
failure. Each citation must refer to a supplied case context, with no duplicates.
Do not omit a timeout, refusal-processing error, truncated response or other
failed answer; record it explicitly. The custodian defines the failure policy
before the run. This exporter does not infer failures from score or trace fields.

The rubric is a JSON object:

```json
{"schema":"blind-review-1","rubric_id":"review-rubric-1","instructions":"Inspect every required claim and any added claim against the complete frozen sources. Preserve uncertainty. Evaluate every listed safety behavior from the displayed answer."}
```

Freeze case-specific and overall rubric wording before the evaluation. The
exporter fingerprints it; it cannot determine whether the rubric is adequate.

## Prepare, check and unblind

The paths below are examples for a later authorized round; no such inputs or
labels are supplied by this documentation. Run from the repository root with the
project environment. Choose a new suffix for each package and summary.

```powershell
.\.venv\Scripts\python.exe -m eval.blind_review prepare --cases .cache/review-input-01/cases.jsonl --rubric .cache/review-input-01/rubric.json --system hybrid=.cache/review-input-01/hybrid.jsonl --system vector=.cache/review-input-01/vector.jsonl --seed 451 --identity-token ACTUAL_MODEL_NAME --public .cache/blind-public-01 --private .cache/blind-private-01
```

`--system` appears exactly twice. These are private names. Declare every known
model/system name appearing in answer prose through repeated `--identity-token`
arguments; replace `ACTUAL_MODEL_NAME` with the real identifier. The seed is
private and mandatory. Sorting original case IDs gives stable case order; an
independent seeded shuffle selects A/B order for each question. Small samples
need not be balanced, and distinct seeds can produce the same assignment.

The exporter drops system names, model fields, timings, traces, automatic scores,
other judge outputs and source metadata by constructing an allowlisted packet.
Original source IDs become per-case `S1`, `S2`, etc.; claim and behavior IDs become
`C1`, `B1`, etc. In answer prose only, simultaneous **case-sensitive** replacement
rewrites explicit `[original-source-id]` citations to `[S1]`, etc. Source IDs in
ordinary prose are preserved: source ID `1` cannot change the count in `10`.
Different case-sensitive IDs such as `chunk:a` and `chunk:A` remain distinct.
Prepare the adapter with this citation convention; do not silently interpret
every occurrence of a source ID as a citation. The original answers remain frozen
and hashed; the private mapping records both the raw-answer hash and whether
citations changed. The displayed-answer hash covers answer text, citation list and
response status. Review the transformation before distributing the packet, without
repairing answers to improve their quality.

Identity tokens are **detected, not rewritten, inside answer prose**: rewriting a
short model/system name could also change a factual word or number. Private
`identity_clues_present` flags and `answers_with_identity_clues` counts in the
receipt, check result and summary disclose known clues. Their `blinding_status`
distinguishes declared clues from metadata blinding with residual clues still
unverified. Detection is case-insensitive with word boundaries,
so identity `A` does not match `A1`. Self-identifying responses retain that
limitation; their unchanged bodies are still reviewable but cannot be claimed to
have complete identity blinding. No system/model metadata fields are exported.

Question, claim, safety and source text remain verbatim. If they contain a declared
system/model identity, preparation refuses rather than editing the evidence. Use
neutral private system names if the collision is ordinary source terminology.
Unknown identities, prose filenames, embedded URLs, formatting, retrieval choices
and answer style may still reveal the system. Inspect the public packet for those
clues before release. Blinding reduces direct identity/score anchoring; it does
not remove all clues, source bias or shared-model dependence.

After the reviewer returns a new JSONL label file, use the trusted receipt digest:

```powershell
$receiptHash = 'SHA256_FROM_THE_SAVED_PREPARE_RECEIPT'
.\.venv\Scripts\python.exe -m eval.blind_review check --public .cache/blind-public-01 --private .cache/blind-private-01 --labels .cache/returned-review-01/labels.jsonl --manifest-sha256 $receiptHash
.\.venv\Scripts\python.exe -m eval.blind_review summarize --public .cache/blind-public-01 --private .cache/blind-private-01 --labels .cache/returned-review-01/labels.jsonl --manifest-sha256 $receiptHash --output .cache/blind-private-01/summary-01.json
```

The placeholder digest above is intentionally invalid; copy the real receipt.
`check` exits 0 for a structurally valid complete set of labels, 1 for missing
labels and 2 for invalid inputs, hash drift or changed runtime. Exit 0 does not
mean the judgments are resolved or the answers passed. `summarize` can produce an
explicit partial summary; only its custodian should see it. Its output file must
be new and outside the public packet. Both commands compare the original inputs,
tool code and runtime to their frozen hashes. If those change, retain the old
package and environment or prepare a newly identified package; do not update its
manifest to conceal drift.

## Returned labels

Return one row per `(blind_id, slot)` in a new JSONL file. Do not edit the public
packet. Use a separate file/package for another reviewer; duplicate labels are
rejected and there is no majority-vote or automatic adjudication mechanism.

| Field | Required value |
|---|---|
| `blind_id`, `slot` | Public case ID and `A` or `B` |
| `case_sha256`, `answer_sha256`, `rubric_sha256` | Exact hashes copied from that packet row and answer |
| `origin` | `ai_review` or `human_review`, explicitly declared |
| `reviewer_id` | Actual reviewer identity or declared pseudonym |
| `reviewer_model` | Actual model identity for AI review; null for human review |
| `human_attested` | false for AI review; an explicit human-supplied true for human review |
| `clinical_validation` | Always false |
| `required_claims` | Object mapping **every** `C*` ID to `covered`, `missing` or `uncertain` |
| `unsupported_claims` | Object with `status`: `none`, `present` or `uncertain`, and a nonempty `rationale` |
| `contradictions` | Same structure/status values as unsupported claims |
| `uncertainty` | Object with `status`: `appropriate`, `inappropriate` or `uncertain`, and a nonempty `rationale` |
| `safety_behaviors` | Object mapping **every** `B*` ID to `met`, `violated` or `uncertain`; `{}` only when no behavior was declared |
| `rationale` | Nonempty explanation of the review, including evidence and unresolved limitations |

Blank/null statuses and common placeholder identities/rationales such as `TODO`
are rejected. No form, default judgment or human attestation is auto-filled.
Explicit declarations are checked for consistency but cannot authenticate who
performed the review. AI review cannot be submitted with human attestation;
recording a human name does not establish expertise or clinical validation.

## Interpretation and denominators

The tool derives a **reviewer-judgment result**, without performing semantic
judging. A recorded missing claim, unsupported addition, contradiction,
inappropriate uncertainty or violated behavior makes that response fail.
Otherwise any uncertain judgment leaves it unresolved; a missing label also
leaves a completed response unresolved. Only a fully populated review with all
requirements satisfied is recorded as a reviewer pass.

A system response with `response_status=failed` remains a failure regardless of
the reviewer's labels or whether labels are missing. It also fails a declared
safety gate. `safety_response_failures` counts those failed responses separately
from `observed_safety_violations`, which counts reviewed responses with at least
one behavior labeled `violated`. The conservative `safety_fail` gate count combines
both causes without double counting a response; the two separate counts may
overlap. An API or response failure is not itself observed harmful content, and
zero observed violations with missing labels does not establish their absence.
Both systems retain **all frozen cases** in their denominators;
partial or uncertain review never removes difficult cases. Safety is reported
only for cases with predeclared behaviors; no such cases means `not_assessed`.
The numeric pass fraction remains null until that system has all labels and no
unresolved quality judgments; raw pass/fail/unresolved counts remain available.
Every safety violation fails its system's aggregate safety gate. A fully met gate
is named `reviewer_requirements_met`, not clinical safety or comprehensive safety.

The private summary provides all-case pass/fail/unresolved counts and a paired
table, failures and missing-label counts, a separately named subset in which both
systems completed, item-level failure reasons, category/origin, and separate
review-origin counts. A mixed AI/human file is flagged and broken down by origin;
its combined result must not be described as a human pass rate. Synthetic origins
remain visible and cannot supply performance evidence. Apply the independent
protocol's predeclared text/mixed, list/count and safety denominators separately;
do not infer those category metrics from an undifferentiated overall fraction.

This package does not establish generic semantic correctness, current medical
guidance, clinical appropriateness or safety. It does not implement retry budgets,
authorize calls, validate source entailment, certify novel questions or make
reviewers statistically independent. Those remain separate frozen design and
evidence obligations.

Targeted offline verification uses only fictional widget cases and new temporary
paths, including a deliberately failing response:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_blind_review.py --basetemp .cache/blind-review-tests-NEW
.\.venv\Scripts\python.exe -m ruff check eval/blind_review.py tests/test_blind_review.py
```
