# Implementation decisions

Each entry records a decision, its reason, and alternatives. All runtime and data artifacts remain local.

## D001 — Environment and scope

Use Python 3.12 in the repository `.venv`. Store pip, model, and temporary caches inside the repository to respect the write boundary. Do not alter the parent application's environment. Alternative: a shared E-drive environment; rejected because task scope permits no writes there.

## D002 — Archived evaluation

Preserve the Chinese implementation and its evaluation in the local `zh-v2` tag only. Its saturated keyword benchmark is not comparable to the new entity-set benchmark and is not clinical validation.

## D003 — Task execution

The explicit task authorization covers local phase commits without further confirmation. Docker execution is skipped locally if unavailable; CI configuration is supplied and remote CI remains unverified until the user pushes.

## D004 — Hierarchy and relation identity

Use only direct MONDO `is_a` evidence to orient Disease–Disease edges; ambiguous direction or missing current ontology terms causes exclusion. Alternative: infer hierarchy from lexical similarity or transitive closure; rejected as unsupported direction. Actual relation names match the task table. The CSV contains reciprocal duplicates: canonical endpoint orientation plus relation and TARGETS kind removes them. TARGETS kind remains part of edge identity.

## D005 — Optional schema properties

The static guard rejects properties outside the declared schema. EXPLAIN rejects missing labels and relation types but permits declared optional properties not yet present (e.g. `evidence` in v0). Alternative: reject every Neo4j UnknownPropertyKey warning; rejected because it incorrectly blocks valid baseline templates before extraction creates optional fields.

## D006 — Safety and language

Block all five safety categories with fixed English responses; special-population questions use a conservative professional-assessment response. Alternative: allow general retrieval with a banner; deferred to avoid implying individualized treatment safety. Language detection rejects unsupported scripts and later supplements common non-English Latin-script patterns; this is a heuristic, not full language identification.

## D007 — Usage reservations

Reserve an upper bound from UTF-8 prompt bytes plus completion cap under an exclusive ledger lock. Settle with provider usage when present; retain conservative charges for failed/unknown calls. Pending reservations count against the 15-million-token task cap. SDK retries are disabled; unsupported thinking parameters receive one compatibility retry. No prompts, keys or provider error bodies enter the usage ledger.

## D008 — Evaluation boundary and shared transformations

Put canonical CSV/OBO transforms in independent medkg_data; ingestion re-exports them and the generator imports that pure library. Evaluators use JSON-lines subprocess protocols for ask and research LLM calls, not QA imports. Alternative: import Pipeline or its linker into eval; rejected because it couples scoring to implementation. Execution scoring independently runs gold and predicted queries in read transactions and compares uid/count sets.

## D009 — Bounded live measurement

Live v0 smoke encountered a 30-second provider timeout, and a 25-item answer took 28.6 seconds. Use a seeded per-category cap for live repetitions and record evaluated ids, available count, coverage and cap in every summary. Never cap safety/adversarial cases. Keep the complete 400-case frozen corpus. Natural paraphrasing is initially limited to 24 cases with two attempts; retain original templates on bounded failure. Alternative: repeated full-corpus calls; rejected for this run because the task explicitly permits shrinking samples when runtime is excessive. These are sampled research results, not full benchmark or clinical claims.

## D010 — Text ingestion and request recovery

MedlinePlus imports NLM-authored full summaries only; it does not fetch linked third-party pages. openFDA uses newest effective_time, phrase search on generic/substance names, then the prescribed exact/fuzzy entity link. The initial 17 exact-field queries returned no matches; their requests remain charged to the 500-request cap. Successful downloads are cached; only failed old-query entries are eligible for one corrected-query attempt within the original cap. The final coverage report distinguishes selected drugs, requests, returned labels and linked documents.

## D011 — BioRED relation semantics

| BioRED label | Production mapping | Reason |
|---|---|---|
| Drug_Interaction, Chemical–Chemical | INTERACTS_WITH | Explicit interaction concept |
| Association, Positive_Correlation, Negative_Correlation, Bind | No automatic production mapping | Association or correlation does not establish a contraindication or drug interaction |
| Cotreatment, Comparison, Conversion | No automatic production mapping | These labels are different biomedical assertions |
| Chemical–Disease labels | Native BioRED evaluation only | BioRED has no clinical contraindication gold label |

Run the same JSON extraction implementation in BioRED mode and report pair-detection and native-type F1. Production mode permits only explicit CONTRAINDICATED_FOR and INTERACTS_WITH. Alternative: interpret positive correlation as contraindication; rejected as medically unsupported. This benchmark is an extraction diagnostic, not contraindication or clinical safety validation.

## D012 — Public text drafts and private graph gold

Keep MedlinePlus questions, verbatim supported text phrases, chunk URLs and draft review status in text_v1.jsonl. Put graph-derived draft answers and graph facts in ignored text_graph_gold.jsonl. Mixed public questions name the public health topic and ask for graph associations plus the summary; the precise private gold remains local. Alternatives: commit PrimeKG-derived relationship lists inside text drafts, or call unreviewed drafts verified; both rejected. Strict quote coverage is exploratory until human review.
## D013 — Development repairs and exact coverage

Before text test measurement, structural validation found seven mixed drafts
without phenotype/gene gold because the original selector allowed any disease
relation. Replace only those drafts with unused eligible MedlinePlus chunks using
seed 43, preserving ids/splits and logging ids in text_dataset_summary.json.
Selection does not depend on system test answers. Keep all 80 rows marked draft.
Use strict source/label enum validation and one bounded plan-schema repair after
invalid development plans. Alternatives: score unanswerable mixed drafts, accept
arbitrary tool arguments, or discard low-scoring tests; rejected.

## D014 — Provider concurrency and interrupted measurements

The existing endpoint returned HTTP 429 during concurrent evaluation/extraction.
Serialize task LLM calls with a process-shared slot, a 120-second wait bound and
one-second cooldown; do not change model, provider or keys. Preserve conservative
charges for failed attempts. Restart interrupted preliminary v1 runs after the
development-discovered source-argument and synthetic-test expansion fixes; only
completed final three-round summaries count as measurements. Raw failed attempts
remain ignored local artifacts/ledger entries. Alternative: concurrent automatic
retry storms or attributing provider errors to clinical accuracy; rejected.

## D015 — Retrieval work and evidence bounds

Expose at most 25 expansion rows from a 26-row streaming query after bounding
anchors to 25; avoid sorting an entire two-hop neighborhood, which timed out in
the fictional integration test on the populated local database. Reject quantified
path syntax that bypasses the classical variable-path guard. Bound actual answer
and verification evidence to 24,000 JSON characters and 5,000 characters per text
field, with explicit partial-result notices. Store complete entity paragraphs for
the vector control but acknowledge the embedding model's 512-token prefix limit.
Reuse unchanged alias vectors when FDA adds brands. Alternatives: unbounded
neighborhood sorting, oversized LLM prompts, or claiming complete vector coverage
of long paragraphs; rejected.

## D016 — Source rights and calibration unit

Official openFDA terms include private-party copyright exceptions, so NOTICE
qualifies the task's public-domain shorthand; FDA text stays local and committed
text drafts use only public-domain MedlinePlus summaries. HPO uses its own
attribution/integrity terms; local ontology version is 2026-09-01. Government
hosting is not blanket permission for linked or manufacturer-authored content.

The 100-item judge queue samples unique actual sentence claims from the 80 text
question drafts, graph-plus-text draft answers and available system responses.
Multiple sentences may concern the same question; claim_origin distinguishes
drafts from system outputs and only real system outputs have trace ids. All
scores remain uncalibrated pending human review. Alternative: fabricate 100
unique questions or report automatic labels as human-calibrated; rejected.

## D017 — Extraction sample and failure recovery

BioRED diagnostics use 12 seeded test abstracts. FDA extraction initially sampled
60 chunks, with 30 call/parse failures. One bounded recovery of legacy empty
cache entries plus additional sampled chunks produced enough assertions; finalize
80 of 592 eligible chunks and a random 30-assertion review queue. New cache entries
record failure type and recovery status. Local extraction logs include unrelated
failed diagnostic mentions; report the actual total rather than claim all were
unlinked labels from one pass. A confidence value or PrimeKG agreement does not
approve the extracted relation. Alternatives: process all chunks despite runtime
or manufacture review assertions; rejected.

## D018 — Installed layout and fictional CI isolation

MEDKG_HOME overrides the data/cache/log root for an installed wheel; Docker sets
/app. Default editable development retains the existing E-drive repository.
Synthetic fixture imports require an empty/fictional-only database by default;
local mixed validation requires an explicit allow-mixed flag and deletes only
the synthetic: namespace afterward. FakeLLM bypasses real provider and embedding
calls and uses only fictional fixture aliases. CI needs no real data or LLM keys.
Alternative: overwrite the populated research graph or load real upstream data
in CI; rejected.

## D019 — Service streaming and observability

SSE emits processing status and streams the verified final answer, followed by
the complete public result, so unsupported model tokens are not exposed. The
service serializes asks per process; history is explicitly bounded. Local ports
bind loopback. OpenTelemetry uses an actual SDK trace root and local JSONL by
default, switching to OTLP HTTP only when configured. No Phoenix installation or
external telemetry upload is performed by this task. Docker/Phoenix execution
remains unverified locally where the required runtime/receiver is absent.

## D020 — Bounded embedding completion and archived measurements

Complete the pure-vector corpus before final scoring: 42,975 entity paragraphs
and 4,693 public-source chunks, 47,668 records total. Resume verified prefixes
after FDA chunks arrive and flush a checkpoint after each batch. Increase only
this CPU embedding job from two to four threads on the verified 24-logical-core
machine; other embedding calls retain two. Alternative: measure an incomplete
corpus or saturate all cores; rejected. Long paragraphs retain complete text
but embedding vectors represent their 512-token prefix.

Keep phase-2 and phase-3 measurements immutable. Phase 4 uses a new aggregate
after a development smoke run, on the same seeded 54-question sample for three
rounds. Do not tune against those test answers. Baseline-relative redline success
does not fix the baseline's existing adversarial failure. The vector control's
13 regressions are a recorded failed gate, not a deployable fallback.

## D021 — Provenance, output bounds and optional arguments

Engineering review found that a flagged single relation could produce only a
generic conflict notice. Enrich hybrid contexts with both flagged opposite
claims and their evidence chunks, prioritize them within the existing bound,
and append both source-labeled statements by code. Do not enrich the pure-vector
control with structured facts. Count queries collect actual edge sources;
Text2Cypher examples request provenance. Alternatives: overwrite one claim or
trust the model to reconstruct the missing claim; rejected.

Fulltext Document hits use the document's own source/URL; Chunk hits use the
parent document. Entity-node hits identify their source by uid prefix. This avoids
losing provenance when a Document has no HAS_CHUNK parent of its own.

Normalize null optional source/uids/label fields to omission, while required
arguments stay validated. Bound API focus strings to 256 characters. Add a
conservative final regex gate for numerical medication doses/direct personal
diagnosis and common non-English Latin-script patterns. These are limited
engineering controls, not comprehensive language or medical classifiers. Keep
thinking disabled on every physical provider call; fail rather than retry
without that setting. Add run_id to the persistent reservation ledger.

## D022 — Runtime verification and termination

Use temporary localhost-only uvicorn for endpoint and SDK trace checks, then stop
only the recorded process after verifying command and venv-launcher ancestry.
Windows venv launches a child at the existing base Python executable; this does
not mean dependencies were installed into that base environment. Final native
Neo4j is checkpointed and stopped after all tests, leaving the populated database
on disk. No persistent service or autostart is created. Docker syntax is inspected
statically; actual compose/build remain for CI, which is unrun remotely because
no push is authorized. Alternative: install Docker/Phoenix or leave unrequested
background services running; rejected.

The owned Neo4j console supports a native Windows console CTRL_C event. Use it
after verifying pid, launcher ancestry and installation path; logs confirm native
shutdown checkpoints and Stopped. No forced database termination was needed.
The temporary API was stopped only after all requests completed and its venv
launcher/base-Python child ancestry was checked. Closed ports are socket-verified.

## D023 — Medication quantity and frequency checks (review R1)

Recognize worded quantities, fractional quantities and common medication schedules
at both input and final-output boundaries. Keep an independent implementation in
the evaluator. Graph entity counts without medication units/instructions remain
allowed. These deterministic patterns do not establish comprehensive clinical
safety. Alternative: rely on the answer prompt alone; rejected because a scripted
completion reproduced an uncaught dosing instruction.

## D024 — FDA ingredient identities and cached repair (review R2)

Match each generic/substance field independently. Multiple unambiguous ingredients
remain separate ABOUT targets; duplicate labels merge associations. Add each name
only to its uniquely matched ingredient. Quarantine brands for combinations,
unmatched/ambiguous ingredients or multiple brand owners. Rebuild Drug aliases
from the canonical CSV baseline and cached FDA responses, with verified file and
graph backups. Reuse alias embeddings by exact text and update corpus association
metadata without changing text or chunk vectors. Alternative: choose the requested
download drug and assign every label name to it; rejected as identity corruption.

## D025 — Template routing and collection semantics (review R3/R4)

Compound gene/drug/disease questions, mixed entity types and multiple non-interaction
anchors go to the planner. Follow-up intent reuse requires the matching anchor
type. Template lists represent a union of results across anchors, with per-row
anchor identity; count templates count distinct targets across that union. The
interaction template retains its one-drug neighborhood/two-drug pair semantics
and rejects larger input lists. Alternative: silently keep the first UID or assume
an intersection for every explicit list; both change the question's meaning.

## D026 — Generated query limits (review R5)

Reject UNION, including nested forms, until a global limiting transformation is
supported. Keep lexical masking so literals/comments do not cause false rejection.
Stream generated results into a bounded list as a second defense. A result at its
declared limit retains the conservative partial-result notice. Alternative: cap
only each UNION branch; rejected after a 200-row verdict returned 400 rows.

## D027 — Exact count scoring and evaluator version (review R6)

Use complete, nonnegative integer tokens with valid optional thousands grouping;
reject decimal, negative, malformed and contradictory values. Separate Sources
metadata from the answer before parsing. Version corrected scoring as
deterministic-2.0. New offline summaries identify saved-output rescoring and never
replace historical measurements. Alternative: accept the first numeric prefix;
rejected because 2.5, 2,000 and -2 could all score as gold count 2.

## D028 — Supporting quotes and legacy assertions (review R7)

Reject blank names/quotes and require both extracted entity strings inside the
verbatim quote. Revalidate linked cached assertions against the quote, chunk and
current entity catalog before loading. Preserve unsupported legacy assertions in
an ignored human-review queue and retain their original backups; do not infer new
relations or call the model to replace them. Alternative: treat a chunk pointer
and whole-chunk co-occurrence as sufficient support; rejected. Quote validation
remains an engineering check, with semantic approval reserved for human review.

## D029 — Conversation accounting (review R8)

Retain every request/result/trace in a scored case. Sum all turn usage and pipeline
latency, and report final-turn and conversation wall latency separately. Carry
history failures and executed statements into the case checks. Historical runs
without preceding-turn records remain explicitly incomplete for accounting;
rescore answers without fabricating missing cost. Alternative: report the final
request's usage as the case total; rejected as an understatement of required work.

## D030 — Relation-family routing and frequency equivalents (follow-up F1/F2)

Medication frequency protection includes numeric calendar frequencies and recurring
morning/evening instructions. The evaluator independently recognizes those forms.
Single-hop templates require one relation family; multiple requested families,
including Drug -> Disease -> Phenotype paths, use the existing planner. Preserve
simple-template controls. Alternative: add only the two literal review strings;
rejected because equivalent ordinary phrases reproduced the same defects.

## D031 — Mention and brand identity boundaries (follow-up F3/F4)

Resolve explicit noun spans independently after exact matches and retain unresolved
mentions. An unresolved interaction anchor returns a clarification response instead
of a one-drug neighborhood query. Collect brand ambiguity globally, including
unlinked/combination labels, before publishing aliases; remove stale unsafe aliases
on repeat parsing. Preserve canonical Drug names. The parser/cascade remains
heuristic; no clinical identity claim follows from a fuzzy threshold.

## D032 — Fresh/cache agreement and scoped reconciliation (follow-up F5/F6)

Both mention spans and linked endpoint identities must be supported by a verbatim
quote. Fresh and cached extraction share the same linked-identity check; extractor
version is openfda-json-1.2. Replace selected chunk evidence in one database
transaction, preserve unselected evidence and unrelated sources, and recompute
affected conflict flags. Alternative: delete every FDA edge for each sample;
rejected because valid assertions outside that sample would be lost.

## D033 — Incomplete aggregates and explicit quality reporting (follow-up F7/F8)

Propagate reference truncation above 25 distinct anchors. Refuse an exact aggregate
derived from incomplete upstream evidence rather than present a partial count as
global. Normalize/reject alternate signed count representations. Version scoring
as deterministic-3.0 and report category correctness separately from composite
quality (faithfulness, refusal, output safety and read-only execution). Keep strict
generated-query procedure rejection; independently whitelist the two code-owned
read index tools for the composite metric. Normalize recognized prose refusals to
an explicit response_status; this is a bounded heuristic, not semantic proof.

## D034 — Development-only alias correction and bounded comparison

The 13-case real-provider development smoke check exposed ordinary English HAS/has
alias contamination and generic ontology-root anchors. Suppress generic-root
aliases in question/answer discourse and require uppercase spelling for a narrow
set of ambiguous short symbols. Preserve direct mention linking for extraction.
Apply the same policy independently in evaluation and in verification. Do not tune
on test answers after freezing the comparison.

The new pilot predeclares 38 identical test IDs: all 15 safety and 15 adversarial
test questions, plus one seed-42-selected question per other category. Three
rounds each compare current-code phase-1 control, phase-3 hybrid and pure vector
on the same repaired graph. The phase-1 control is an ablation, not historical v0.
Cap additional charged tokens at 3 million and wall time at 90 minutes, below the
original 15-million task budget. Reduced retrieval-category coverage is deliberate
given observed provider latency; no general benchmark claim is supported. Preserve
all historical summaries and label the code/data/evaluator fingerprints.

The automatic approval reviewer initially rejected the expanded run because its
destination and payload scope were insufficiently verified. Read-only checks
verified HTTPS open.bigmodel.cn, existing glm-4.5-flash configuration, the original
CODEX_TASK authorization, and public-source benchmark/evidence payloads. The same
reviewed action was then approved; no alternate provider or indirect workaround
was used. Credentials were never printed or added to payloads.

## D035 — Recoverable publication and bounded external workers

Use a staged export, original-file backup, hashes and prepared/graph_applied/complete
journal states for assertion publication. Resume by replaying scoped idempotent
graph reconciliation, then atomically publish the export. Completed publication
also rechecks its target hash rather than trusting a completion marker. The graph
and filesystem do not form one atomic transaction; a recoverable journal makes
that gap explicit. Preserve existing human review files when refreshing samples.

External evaluation workers have a 300-second response deadline and owned-process
cleanup. Persist every completed case and verify matching code, data, configuration
and ordered case IDs before resuming an incomplete evaluation. Alternative: block
forever on readline or retain progress only at the end of a round; rejected.

## D036 — Human calibration and deployment evidence

Prepare local blind copies of the 100-claim judge queue, 30 original extraction
items, 18 quarantined assertions and 80 text drafts. Do not fabricate human labels
or overwrite original evidence. Human-labelled completion remains an external
dependency and judge scores remain uncalibrated. Aggregate trace metadata before
optimizing; nested spans overlap and are not additive capacity measurements.

Build the Python wheel with the existing project environment. Add only the declared
setuptools build dependency when the environment lacks it; do not upgrade base
Python or unrelated packages. Docker is absent locally, so inspect configuration
and packaging, retain the existing CI build checks, and report the missing native
container/remote/Phoenix execution. Installing Docker, pulling images or pushing
the repository remain outside the authorized scope.

The cached repair's already-applied branch must run a read-only artifact check
before returning. Validate the frozen dataset, vector checkpoint hash and shapes,
chunk associations and retained assertion support rather than trusting its marker.
This check does not verify live graph state or clinical correctness.

## D037 — Publication generations and final measurement scope

A later completed outside-sample publication may legitimately change an export.
Reuse matching complete journals, but create a new generation from the current
validated export when repeating an older completed operation. Preserve outside
evidence. Reject drift during incomplete recovery, invalid export structure,
damaged staging and damaged original backups. Concurrent writers remain unsupported.
Alternative: reject every completed-hash change; rejected because normal successive
sample refreshes would make older operations unusable.

The frozen three-system comparison completed before this ingestion-only refinement
was applied. Preserve its exact source snapshot and distinguish measured QA code
from final maintenance code. Final unit/native/FakeLLM and wheel checks cover the
final publication implementation. Report the 38-case sample and historical metrics
separately; zero redline regression and a modest composite-quality difference do not
establish overall retrieval improvement or clinical efficacy.

## D038 — Bounded planning repair and relationship coverage

Repair malformed JSON and invalid tool arguments within the existing retry limit.
After exhausted schema repair, only a resolved, unambiguous graph relationship
question may fall back to the existing guarded Text2Cypher tool. Explicit valid
out-of-scope decisions and provider transport failures remain visible. Never
execute a planner-supplied Cypher argument. Alternatives: silently repair arbitrary
plans or increase retries; rejected because both weaken failure attribution and
increase uncontrolled cost.

Use complete-question Text2Cypher examples for intersections, exclusions and
multi-hop constraints; chained single-hop templates produce a union. Add
parameterized hierarchy, off-label and gene reverse templates. A general entity
introduction uses one-hop expansion, reducing irrelevant evidence and cost.
Generation and verification receive the resolved conversation question and the
exact successfully executed read query and parameters in a separate fenced field,
bounded to 6,000 characters. This describes retrieved constraints without
inventing graph edges. Answer prompts spell out arrow direction and request
canonical target names without synonym arrays or repeated anchor introductions.
Retry feedback includes the bounded Neo4j error message.

## D039 — Alias spans and independent scoring corrections

Derive maximum alias lengths from the actual catalog rather than a 12-word cap.
Store the matched mention and token span; mask that mention during routing so an
entity's canonical name cannot consume relationship words. Keep one winning
fuzzy/vector candidate when unambiguous; preserve competing ambiguous candidates.
Broaden explicit refusal phrasing without treating a dose disclaimer as an empty
answer. These remain finite heuristics, not a medical NER or safety guarantee.

Independent evaluator deterministic-3.3 includes declared history questions when
finding conversation anchors and does not remove an expected target merely
because its alias also names an anchor of another type. Alternatives: score only
the final pronoun question or remove every anchor alias; rejected because both
penalize correct catalog entities. Fictional regression cases cover both issues.
Entity-level automated faithfulness does not establish sentence-level accuracy.

## D040 — Frozen full comparison and human decision import

Compare current phase-3 hybrid with the exact source snapshot taken before these
capability changes, plus current pure-vector retrieval. Share repaired cached data,
provider/model, deterministic-3.3 and all 240 frozen test IDs for three rounds.
The control is the repaired phase-3 system, not historical v0. The test set includes
38 previously reported pilot cases and is therefore not a wholly fresh holdout.
Do not inspect test answers or tune code during the frozen comparison. Retain
per-case checkpoints and immutable old reports. Bound additional charged tokens
to 10 million and elapsed comparison time to four hours, within the task-wide
15-million ceiling. Budget exhaustion produces a documented incomplete comparison,
not a fabricated full result. No new downloads, provider changes or concurrency.

Human blind decisions can be imported only after validating all stable ids and
unchanged evidence. Preserve model labels, accept boolean/null decisions and
bounded notes, save verified backups, and replace each file atomically. Imports
are idempotent; a filesystem failure between files can require rerunning. Import
does not approve or load graph assertions. Alternative: agent-created human labels;
rejected because it cannot supply independent human review or calibration.

## D041 — Private intermediates on failed human imports

Place uniquely named replacement files inside ignored `.cache/human-review-import/`,
not beside the source queue where a `.pending` suffix could escape JSONL ignore
rules. Verify the original source bytes again before replacement and remove the
temporary file after success or ordinary failure. Preserve hash-verified backups.
The cache and source are within the same project filesystem for atomic replacement.
Concurrent writers remain unsupported; the byte check detects ordinary drift but
does not implement a multi-file transaction. Fault tests cover replacement failure
and source drift. This importer-only fix was applied during the frozen comparison;
all frozen QA, score, client, runner and data hashes remain unchanged.

## D042 — Balanced coverage after measured provider latency

The first complete 240-case improved-system round took almost 50 minutes. The
initial nine-full-round schedule would exceed its four-hour wall ceiling and
could leave no completed control comparison. Apply the original task's timeout
sampling instruction: one complete 240-case round per system, then three rounds
of the same 70 test cases (seed 42, cap 5 per non-redline category, all 30
safety/adversarial cases). Selection uses ids/category and the fixed algorithm,
not correctness outcomes. Progress flags were visible; test answers were not
used to change QA, data or scoring.

Reuse actual first-round records and make two new subset rounds. Verify identical
dataset, vocabulary, evaluator and system code fingerprints before combining.
These are actual model runs, not synthetic rounds or newly generated answers.
Preserve the interrupted second-round prefix and original immutable plan; its
cost remains in the conservative ledger but its incomplete round is excluded
from comparative rates. A new separately frozen orchestration plan retains the
original overall token ceiling and absolute four-hour deadline, including the
adaptation interval. No parallel provider calls or new downloads.

Alternative: finish all improved-system repetitions before controls; rejected
because measured latency threatens balanced coverage. The full 240-case results
have one round and cannot estimate repeat variance; report that scope separately
from the 70-case three-round means and standard deviations.

## D043 — Abandoned slot recovery during orchestration changes

Stopping the original owned process tree during an active call left its O_EXCL
request-slot file. The new control's first three attempts waited 120 seconds for
that abandoned slot, without reaching the provider. Identify these operational
failures using timing/error metadata, not answer correctness. Stop the verified
new evaluator tree, confirm no project LLM worker remains, and move the abandoned
lock and invalid partial control records/checkpoint to ignored recovery storage.
Verify source and destination stay inside the project and compare file hashes.
Restart the same frozen control from its first case. Do not erase ledger charges
or reset the original deadline. The original complete improved-system round is
unaffected. Invalid lock-wait records are diagnostics, not comparative samples.

This exposes a crash-sensitive lock implementation. Preserve frozen QA/LLM code
during measurement; any later lock-lifecycle maintenance must be documented and
validated separately, without claiming that it received the earlier real scores.

## D044 — OS-owned local mutex after frozen measurement

After all comparison stages and combinations finish, preserve and byte-verify
the measured source snapshot before changing locking. Replace exclusive-creation
ownership with a file descriptor held by Windows `msvcrt.locking` or POSIX
`fcntl.flock`. Use persistent `.oslock` files and bounded acquisition loops. Never
unlink a native mutex: a second inode could permit concurrent holders on POSIX.
The OS releases ownership when the worker exits, including forced process exit.
Budget reservation and the single-provider slot retain their existing bounds;
provider, model, retries, cooldown and accounting are unchanged.

Refuse an existing legacy lock after a bounded wait; inspect ownership before
manual recovery. Archived legacy and native protocol clients must run sequentially;
mixed protocol concurrency is unsupported. Alternative: remove locks by age or
PID guess; rejected because an old-looking file can belong to a live process.
Windows probes and unit tests verify live-holder exclusion, exception release,
abrupt owned-process exit/reacquisition, and preservation of legacy locks. The
POSIX branch is implemented but remote Linux CI remains unexecuted locally.

## D045 — Provider-independent administrative scope refusal

Use a finite deterministic gate for obvious credential disclosure, system prompt
extraction, instruction overrides, operating-system commands and database writes
before cache, linking, retrieval or model calls. Keep medical safety and language
checks first. Return an explicit `scope` refusal with no failure stage; transport
failures on ordinary questions remain errors. Both hybrid and vector use the same
boundary. This is a narrow scope rule, not a general injection or clinical classifier;
query validation and read-only transactions remain required.

Rules come from development adversarial cases and independent fictional probes,
including normal gene deletion and graph relationship questions. Correct the
fictional article variant `Drop the database.` before applying the patch. No test
question or answer is used to tune rules or prompts. Alternatives: classify every
administrative request with the provider, or mark all transport failures as refused;
rejected because they respectively retain availability dependence or hide errors.

Apply this and D044 only after the frozen comparison. Recheck the fixed 22-case
development selection and all 30 safety/adversarial test ids in three fresh rounds,
with independent output names and final-source fingerprints. Preserve the initial
timeout regression and vector refusal failures. The earlier full and repeated
scores describe the measured capability snapshot; final-source maintenance receives
separate tests and redline evidence.

## D046 — README in wheel metadata

The final package-content check finds that project metadata does not declare the
existing README. Declare `readme = "README.md"` so wheel metadata carries the
current English description, measurements and limitations. Preserve the preceding
code-only build with a matching hash, rebuild offline with existing setuptools,
and inspect names and metadata. This packaging-only change introduces no dependency
or QA behavior change. Alternative: rely on the repository page alone; rejected
because reviewers of an exported Python package would lose its context.

## D047 — Code review fixes (2026-10-07)

A line-by-line review of `src/medkg` and `eval` found defects that the frozen
benchmark could not expose. Each fix has a fictional-entity regression test in
`tests/unit/test_code_review_fixes.py`.

- Safety gates matched entity names instead of situations: "diseases with chest
  pain", "drugs for heart attack", "suicidal ideation as a side effect" and
  "ectopic pregnancy symptoms" were refused. Emergency and crisis rules now need a
  personal or situational cue (method-seeking crisis phrases need none);
  special-population rules need a medication context. A bare article is a dose
  quantity only inside an instruction, so "a drop in blood pressure" no longer
  replaces an answer, and "if you have X" is not a diagnosis. All 25 frozen safety
  controls keep their category.
- One-hop `expand` returned bare neighbor names, so a contraindication could be
  narrated as a use. Rows now carry relation, subject and object, sampled up to four
  per relationship type with explicit truncation; two-hop rows carry their path.
- Alias matching suppressed only nine hard-coded English words. A shared lexicon
  (`medkg_data.lexicon`) now requires upper-case spelling for every alias that is
  an ordinary English word (LET, GET, TEN, ALL, BAD...), in the linker, verifier
  and scorer alike. This also removes the false "cold" -> COPD link.
- Pronoun resolution replaced every "it"/"that"; it now replaces only referring
  uses. `(?<!contra)indicat` keeps contraindication questions on their template.
  More than 25 evidence chunks now marks the answer partial.
- The runtime LLM client enforced the one-off 15M task cap against a lifetime
  ledger and always slept 1 s. `TOKEN_BUDGET` is now opt-in (no clamp) and
  `LLM_COOLDOWN_S` (default 1 for the free GLM tier) is configurable.
- Scoring `deterministic-3.4`: an explicit "Count: N" label is authoritative, so
  list numbering, uid digits or "type 2" in a name no longer void a correct count.

Alternatives: extend the hard-coded word list (rejected: it missed half the
observed collisions) or re-tune safety rules on test questions (rejected: rules are
checked against frozen controls and fictional cases only). Not addressed here: the
benchmark generator still samples only anchors with at most 15 neighbors and has
no lay, brand-name or typo variants; that needs the v2 question set.

## D048 — Same-name readings, reverse side effects and text fallback (2026-10-07)

Real-provider probes after D047 found three gaps the frozen benchmark cannot show.

- PrimeKG often has a Disease and a Phenotype with one name (gout, migraine, type 2
  diabetes). Both readings were marked ambiguous, so the router refused templates and
  the planner refused its guarded fallback; malformed plans then ended in errors. A
  mention whose readings differ only by label is now resolved by the requested
  relation: each reading is routed, and if several match, the requested target type
  ("which diseases ...", "what are the symptoms ...") decides. Several readings of one
  label remain ambiguous. Leading common words no longer form unresolved mentions
  ("let me know which drug"), which had blocked routing.
- "Which drugs have X as a side effect" had no template and relied on generated
  Cypher. `drugs_with_side_effect` (Phenotype <- HAS_SIDE_EFFECT - Drug) now covers it.
- 9,030 of 15,774 diseases have no HAS_PHENOTYPE edge, gout included, so a single
  template could answer "no evidence" while a MedlinePlus summary about the entity
  exists. In hybrid phase 3, an empty single-template result now falls back to
  vector search over documents ABOUT the anchors (`retrieval_fallback`).

Alternatives: ask the user to choose Disease or Phenotype (rejected: the relation
already determines it), or always answer "symptoms" questions from text (rejected:
graph phenotype edges are structured and cited when they exist). Fictional-entity
tests are in `tests/unit/test_label_resolution.py`; no test answers were used.

## D049 — Drug brand names and lay disease names from MeSH (2026-10-08)

Everyday names did not link: "aspirin" (catalog: Acetylsalicylic acid), Tylenol,
Lipitor, "high blood pressure". 11 of 40 common drug, brand and lay disease probes
linked before enrichment; 39 of 40 after (Tamiflu is absent from MeSH).

- Source: MeSH 2026 descriptors (NLM, free with attribution), downloaded by
  `scripts.download_structured`. Drugs (tree D) take preferred and narrower (NRW)
  concepts, which hold brand names and salts; related (REL) concepts are often
  combination products and are skipped. A descriptor is used only when its terms
  match exactly one catalog Drug, retrying without a salt suffix ("Sildenafil
  Citrate" -> Sildenafil, which brings Viagra). Diseases take preferred-concept
  terms only, joined through MONDO xrefs annotated `MONDO:equivalentTo`.
- The optional DrugBank vocabulary (CC0) is joined by DrugBank id when a manually
  downloaded file is present; its site refuses scripted downloads.
- Merge rules (`medkg_data.synonyms.merge_synonyms`): never add an alias owned by
  another entity of the same label or proposed for several; never let a new alias
  join an unrelated entity of another label ("DIC" for dacarbazine, "Seizures" for
  visual epilepsy); skip inverted forms, long chemical names and common words.
  17,522 aliases were added to 3,699 entities (12,516 Drug, 5,006 Disease); 391
  same-label and 154 unrelated cross-label proposals were skipped.
- `scripts.enrich_synonyms --apply` backs up the catalog and alias vectors, then
  updates entities.json, Neo4j synonyms, chunk MENTIONS edges and alias vectors.
  MENTIONS now use the exact alias pass only, which also removes earlier
  common-word links (55,536 -> 45,616 edges).

The entity catalog is also the scorer's vocabulary, so evaluations after D049 have
a new `vocabulary_sha256` and are not directly comparable with earlier summaries.
Alternatives: RxNorm prescribable content (deferred: US prescription focus, 75 MB,
needs a UNII bridge) or hand-written brand tables (rejected: unmaintainable).

## D050 — Structured benchmark v2 (2026-10-08)

v1 (frozen) samples only anchors with 1-15 neighbours, uses ontology names and
template wording, and has one multi-hop shape, so it says little about common
questions. v2 (`eval/generate_v2.py`, `structured_v2.jsonl`, `MANIFEST_v2.json`)
keeps the CSV-only gold rule and the v1 control questions and changes the rest.

- Anchors: 75% from common pools (diseases with a MedlinePlus topic, drugs with an
  FDA label or 3+ indications, the most frequent side-effect/disease phenotypes),
  25% from the long tail. HPO qualifier terms (onset, inheritance, frequency) and
  obsolete entities never anchor a question. 247 common / 73 tail / 80 controls.
- Wording: 2-4 natural templates per relation, phenotype names lower-cased. Half of
  the eligible questions went to the configured LLM for rewording with validation
  (anchors verbatim, both/not/interact/how-many cues kept). It mostly returned the
  question unchanged: 28 reworded, 95 `llm_unchanged` (labels corrected before
  first use), 16 kept the template after failed validation.
- Lexical variation from real usage: 25 US brand names of single-ingredient
  prescription products (cached openFDA labels), 20 MedlinePlus consumer names and
  also-called names ("lazy eye", "grippe", HCV), 15 adjacent-letter typos. The 40
  D049 coverage probes are excluded. `alias_in_catalog` records whether the system
  can link the form; unlinked forms are kept as coverage tests.
- Clinical multi-hop and constraint shapes: drugs for A that interact with drug D,
  drugs for A contraindicated in B, drugs for A not contraindicated in B, drugs for
  both A and B, shared symptoms, side effects of a disease's drugs, gene-mediated.
- `sensitive_terms` (20): third-person knowledge questions with words the pre-D047
  safety rules refused (chest pain, suicidal ideation, pregnancy, seizure, newborn);
  they must be answered.
- Lists longer than 15 are scored on precision plus a partial notice; scoring
  `deterministic-3.5` also accepts a complete 16-25 item list without the notice,
  and subtracts explicit `anchor_uids` (a misspelt anchor cannot be re-linked).

All 320 gold queries were executed read-only against Neo4j and returned exactly the
CSV-computed sets/counts. Split: 160 dev / 240 test (seed 2026). Question texts
were reviewed while the generator was developed; no system answers on v2 have been
inspected. Only test-split summaries should be reported; tune on dev.

## D051 — Catalog synonyms in the pure-vector control (2026-10-08)

Rebuild every PrimeKG entity paragraph with an `Also known as:` sentence from
the current entity catalog. Prioritize the retained `mesh:` additions recorded
in `synonym_additions.jsonl` (D049), then preserve the catalog's remaining order;
normalize for deduplication, omit the canonical name, and retain at most 20 aliases.
An entity without additional aliases says `Also known as: none recorded.` Alias
provenance only orders aliases already in the catalog; it never adds a new alias.
Alternative: reconstruct MeSH proposals or choose aliases using benchmark forms;
rejected because the former could disagree with retained collision decisions and
the latter would tune the control on evaluation questions.

Copy and hash-verify the old corpus, matrix and progress file in
`.cache/vector-corpus-pre-v2/` before rebuilding. `--rebuild` regenerates the corpus
through a temporary file and starts embeddings from zero when paragraph bytes
change. The previous append-only optimization must not reuse old vectors for
rewritten rows. A matching corpus hash can resume interrupted embedding work.
Use the existing cached CPU model, four threads and no downloads. Alternative:
append aliases while retaining old embeddings; rejected because text and vectors
would disagree. Fictional regression tests cover priority, deduplication, catalog
membership, the limit, document preservation and complete vector invalidation.

## D052 — Frozen v2 measurement and task accounting (2026-10-08)

Use the existing evaluator's dev selection unchanged: `--max-per-category 2`
retains all safety/adversarial controls, giving 38 rather than 22 smoke questions.
The smoke finishes with 30 passes, five API-timeout questions and two handled
planning `ValidationError` questions. These errors are preserved. Planning output
leniency is explicitly deferred by T5; do not change schemas or prompts to repair
these dev outcomes in this measurement task. The original provider JSON is not
retained, so do not attribute either validation failure to a particular field.
Alternative: broaden the planning schema now; rejected because T5 reserves that
decision for the user. No test answer has been inspected before the freeze.

Keep the existing provider, model, 30-second timeout and zero SDK retries; set
the requested cooldown to two seconds. The initial conservative cumulative ledger
balance is 5,344,304 tokens. Set the process-local cumulative `TOKEN_BUDGET` to
8,344,304, enforcing at most 3,000,000 additional charged/reserved tokens. Existing
unsettled reservations remain counted; never reset or edit the ledger. The smoke
charges 69,000 tokens (40,607 provider-reported). Historical 240-case hybrid and
vector runs reported 367,791 and 672,139 tokens; reserve approximate ranges of
400,000-900,000 and 700,000-1,100,000 respectively before the new runs, and update
the remaining allowance before each attempt. Failed calls can cost their full
conservative reservation despite reporting zero tokens.

Run hybrid then vector serially in owned background processes. Persist every
60-case milestone, complete per-case records and immutable output names. A round
with more than ten API-error questions is invalid, retained locally, and can only
be retried as a whole after a cooling interval, with a new name and within the
same task allowance. The interface-error set is exactly `APITimeoutError`,
`RateLimitError`, `APIConnectionError`, and `InternalServerError`, checked across
all conversation turns. The paired comparison excludes a question if either
system has one of these errors; other failures still count. Alternative: retry
only failed cases or exclude every answer failure; rejected because those would
change the declared sample and hide model/system failures. After starting test,
QA code, prompts, frozen datasets, catalog and retrieval corpus stay fixed.

## D053 — Resume the interrupted CPU rebuild (2026-10-08)

A desktop turn interruption terminates the owned embedding process and the
first Neo4j console instance. Confirm both process termination and closed ports
before restarting anything. The progress file is valid at 6,720 of 47,668 rows,
with the same rebuilt corpus hash. Resume `scripts.build_vector_corpus` without
`--rebuild`, using the existing matrix and progress under the same corpus hash;
completed vectors are retained, and rows beyond the saved progress are encoded
again if necessary. Preserve the initial log and hash-verified pre-v2 backup;
write a separate `vector-build-resume1.stdout.log`. Restart Neo4j through the
approved script immediately before T3 and record its new process identity.

Alternative: regenerate the corpus or discard partial vectors; rejected because
the unchanged hash and valid flushed progress permit bounded recovery without
new data, model calls, or changed benchmark inputs. No task token balance or
frozen input is reset. Final artifact and matrix checks apply to the completed
resumed corpus, rather than treating the interrupted process as a successful run.

## D054 — Preserve an invalid API round and cool before a whole rerun (2026-10-08)

The first v2 hybrid test attempt completes all 240 questions, recording all four
60-question milestones, but has 44 API-error questions: 24 `APITimeoutError` and
20 `RateLimitError`. It exceeds the declared ten-question limit and is invalid.
Keep its summary, complete per-question records, checkpoint and logs locally;
do not publish it as the formal capability result or select individual successful
answers. Its 15 non-interface failure questions (11 `ValidationError`, four
`CypherSyntaxError`) are also retained; no QA code or prompt is changed after
starting test. Alternative: fix these test failures or retry only API failures;
rejected because either would violate the frozen measurement protocol.

Choose a ten-minute interval without new model calls after the evaluator exits,
then use the new name `v2_test_hybrid_retry1` for another complete 240-question
attempt. Keep the same provider/model, two-second cooldown and runtime parameters.
Select a valid attempt by the API-error rule, never by its pass rate. The invalid
attempt reports 453,534 provider tokens and conservatively charges 739,995 tokens;
with the dev smoke, task charges are 808,995 and 2,191,005 remain. Estimate the
hybrid rerun at 600,000-900,000 and the later vector run at 700,000-1,100,000
conservative tokens before proceeding. All attempts share the same cumulative cap.
Alternative: reset the ledger or change the endpoint to improve availability;
rejected because neither is authorized. Any further attempt requires a new budget
estimate; exceeding the task allowance requires the user's decision under section 4.

## D055 — Complete the independent vector attempt within the remaining allowance (2026-10-08)

The complete `v2_test_hybrid_retry1` attempt also exceeds the API threshold: 30
questions, comprising 18 timeouts and 12 rate-limit errors. Its 16 non-interface
failure questions comprise ten planning `ValidationError` and six
`CypherSyntaxError` events. Preserve this invalid attempt locally without changing
code or prompts. It reports 486,552 provider tokens and charges 719,525 tokens;
combined task charges are 1,528,520, leaving 1,471,480 under the original cap.

Before requesting a larger allowance for more reruns, complete the independently
authorized first vector attempt: estimate 700,000-1,300,000 conservative tokens,
including room for failed-call reservations, within the remaining allowance.
Wait ten minutes without model calls after the hybrid process exits, then run all
240 test questions once in vector mode. Use the task's original
`v2_test_hybrid_summary.json` baseline argument unchanged. The evaluator reads
that baseline only after producing all vector answers; it does not affect QA
inputs, retrieval or scoring. Any recorded redline comparison against that
API-invalid snapshot is diagnostic, not an accepted capability comparison.
The eventual report must compare individual outcomes against a valid hybrid
attempt and exclude the union of both systems' API-error questions.

Alternative: spend the remaining allowance on further hybrid retries before
starting vector; rejected because the next hybrid-plus-vector upper estimate is
2,200,000 and exceeds the remaining allowance, whereas the independent vector
attempt fits. Keep all frozen inputs and runtime parameters unchanged. Reestimate
before further attempts, and ask under section 4 if the remaining allowance cannot
cover them. A run censored by the runtime token cap is not a completed capability
measurement, even if its API-error count happens to be below the threshold.

## D056 — Stop at the task-budget decision before further reruns (2026-10-08)

Stop the first vector attempt after 121 of 240 questions: it already has 17
API-error questions (16 timeouts, one rate-limit error), so the round is invalid
irrespective of later answers. Its 60/120-question milestones, checkpoint,
per-question records and logs remain intact. Signal only its verified owned
hidden console, then stop the owned Neo4j console and its waiting launcher;
verify that owned evaluation processes are gone and ports 7474/7687 are closed.
This deliberately leaves a partial invalid attempt instead of spending the
remaining allowance to finish it. The original vector summary is not produced;
any future vector attempt must restart all 240 questions with a new output name.
Alternative: finish the already-invalid round or resume only its remaining/error
cases; rejected because the former spends the finite allowance without obtaining
a valid measurement and the latter violates the whole-round rerun rule.

The conservative task ledger now charges 2,480,097 tokens, leaving 519,903 under
the unchanged 3,000,000 cap. Provider-reported task tokens are 1,530,119; failed
calls without reported usage retain their full UTF-8-input-plus-output reservation.
These are resource-accounting values, not monetary charges. The same four old
unsettled reservations remain counted; no new reservation is unsettled. The vector
prefix alone charges 951,577 tokens, including its stopped in-flight call, exceeding
the burn implied by the historical-data estimate. Keep that original estimate in
the launch record rather than rewriting it after observing test.

Before any additional model calls, request the user's section-4 decision. Based
on observed usage, estimate a complete hybrid attempt at 600,000-900,000 and a
complete vector attempt at 1,300,000-2,100,000 conservative tokens. Even the lower
combined estimate exceeds the remaining allowance. A proposed total task cap of
6,000,000 would leave 3,519,903 for another full attempt of each system, but it is
not applied without authorization and cannot guarantee a valid API round.
Alternative: reset the ledger, silently count failed calls as zero or change the
provider/model; rejected because these change the authorized resource/protocol
boundaries. Freeze QA code, prompts, data and catalog throughout.

T1/T2 are complete; T3 still has no valid paired measurement. Keep the two complete
invalid hybrid summaries and partial vector records local. Save an answer-free
budget review in `.cache/v2-evaluation-2026-10-08/budget-decision-review.json`.
Do not present these diagnostic scores as v2 capability results or claim T4/T5
completion. The requested results report and README/summary updates await valid
measurements or a new explicit reporting instruction from the user.

## D057 — Apply the approved six-million-token cap without resetting usage (2026-10-08)

The user approves the proposed total task allowance of 6,000,000 additional
tokens after the D056 budget report. Retain the original `start.json`, usage
ledger and budget-decision review. Record the authorization in a separate local
policy overlay; the cumulative runtime cap becomes 11,344,304, from the original
5,344,304 ledger balance plus the approved 6,000,000. Already charged task usage
of 2,480,097 remains counted, leaving 3,519,903 before any new calls. Keep the
provider, model, key, timeout, zero SDK retries and two-second cooldown unchanged.
Alternative: interpret the approval as six million more tokens or reset accounting;
rejected because the approved proposal was a total task cap, including prior work.

For further attempts, stop the owned evaluator as soon as more than ten completed
questions have an API error on any turn. Preserve that invalid prefix, its logs,
checkpoint and any 60-question milestones; record the stop and process exit.
Wait at least ten minutes without calls before a new whole 240-question attempt
under a new name. The first post-approval attempt already follows over thirty
minutes without calls. This rule depends only on the declared API threshold,
never answer quality or pass rate; it does not retry individual cases or change
the frozen evaluator. Alternative: finish known-invalid rounds; rejected because
this consumes the finite approved allowance without making a valid result possible.
Continue to estimate full-round cost before every launch and preserve all prior
attempts locally. QA code, prompts, datasets, catalog, corpus and human queues
remain frozen. Any accepted formal result must still contain all 240 questions.

## D058 — Bound provider waiting consistently for the next valid pair (2026-10-08)

The first post-approval hybrid attempt (`v2_test_hybrid_retry2`) reaches 11 API-error
questions after 24 completed questions: two timeouts and nine rate-limit errors.
Stop and retain this invalid prefix. It reports 5,479 provider tokens and charges
45,482 conservative tokens; total task charges become 2,525,579. The evaluator
exits after the console interrupt and its cleanup; no new reservation is unsettled.

The task fixes the provider, model and two-second cooldown but leaves the provider
timeout unspecified. Supersede the 30-second choice in D052/D057 for subsequent
attempts: set the existing process-local `LLM_TIMEOUT` configuration to 60 seconds
for both systems. Retain zero SDK retries, the 300-second worker deadline and all
frozen code, prompts, datasets and retrieval inputs. Do not edit `.env` or change
the endpoint/key. This responds only to API-error counts and the timeout/limit
sequence, not answer text or pass rates; it does not establish why the endpoint
throttles. Longer waiting may reduce timeout-driven repeated requests, but cannot
guarantee availability. Alternative: repeatedly spend the finite allowance with
the same 30-second cutoff; rejected after four API-invalid test attempts. Increasing
SDK retries or changing QA output handling is also rejected.

All earlier 30-second attempts remain invalid and local. Require the same new
60-second setting in both accepted full rounds, record it beside latency results,
and exclude worker-deadline or budget-censored incomplete runs from formal results.
Keep the API invalidation rule, ten-minute interval between invalid attempts and
full-round immutable restart names. Preserve the original freeze metadata as the
historical record; store the runtime amendment in new per-attempt metadata.
Only the private background wrapper changes. Its interrupt cleanup is bounded:
after 20 seconds, terminate only its still-owned evaluator process tree if needed.

## D059 — Publish the first valid v2 pair with explicit denominators (2026-10-08)

Accept `v2_test_hybrid_retry3` and `v2_test_vector_retry1`, each with all 240 frozen
test IDs, the same 60-second provider timeout and four saved progress milestones.
They have seven and zero API-error questions, respectively. Select by the declared
API threshold rather than pass rate; keep four earlier invalid attempts local.
Hybrid passes 194/240 (80.83%) and vector 78/240 (32.50%). Exclude the union of
seven API-error IDs across all conversation turns for the paired comparison:
194/233 (83.26%) versus 76/233 (32.62%). Keep hybrid's ten validation and seven
query-syntax failure questions in the paired denominator. Alternative: remove
each system's errors independently or pool successful answers from invalid runs;
rejected because those compare different samples or conceal failures.

Read lexical subgroup sizes from the frozen test metadata: 17 brand-name, 14
lay-name and five typo cases. The brand/lay groups have 20 catalog-present and
11 catalog-absent forms; typo cases lack `alias_in_catalog` and are reported as
`not_recorded`, without inferring values or modifying the dataset. Alternative:
assume proportional subtype splits or treat missing annotations as false;
rejected because neither matches the frozen metadata. State that catalog presence
does not guarantee inclusion under the vector alias cap, retrieval or QA success.
Vector's 0/36 lexical result is retained without a post-test repair or a claim
that the synonym rebuild demonstrated a performance gain.

Both systems falsely refuse 1/12 sensitive-term knowledge questions (1/11 on the
paired subset). Report vector's adversarial regression on `v2-0373` directly;
neither an execution-error explanation nor zero forbidden-content/query counters
changes that failed control. Publish full category rates and paired rates, and
sum latency/token usage over all turns. Keep the frozen evaluator's percentile
convention. One accepted round does not establish stability or clinical efficacy.

Update README with the v2 results table first, four limitations and one historical
v1 paragraph linking archived reports. Correct its old 24-paraphrase statement to
distinguish v1 from v2's 28 rewordings. Append the v2 snapshot to the delivery
summary; preserve historical sections and record all invalid attempts, runtime
deviations and costs in `docs/reports/v2-results.md`. Alternative: replace archived
measurements or compare v1/v2 headline rates as a matched experiment; rejected
because the cases and scoring differ. Commit only accepted aggregates and docs.

The handoff's T5 count of 18 absent brand/lay forms differs from the frozen
metadata's 16 rows marked false (11 test, five dev). Report this discrepancy and
defer reconciliation; do not assert that the handoff count was verified or change
labels/catalog entries to make the counts agree. This does not change the
test-subgroup denominators above. Alternative: silently repeat 18 as a measured
dataset count; rejected because the current frozen annotations do not support it.

Final additional task accounting is 3,356,704 provider-reported tokens and
4,404,356 conservative ledger tokens, including the dev smoke and every invalid
attempt, below the approved 6,000,000 cap. The four historical unsettled
reservations remain counted; no new one is unsettled. Artifact checks pass, and
frozen inputs and all seven human queues remain unchanged. Stop owned evaluators
and Neo4j, verify closed ports 7474/7687, and stop at T5 without new improvements.

## D060 — Resume T5 with cached-source aliases and bounded index refresh (2026-10-08)

The user's subsequent instruction to continue authorizes the deferred improvements.
Keep the section-4 boundaries and the approved six-million-token total allowance.
Use existing cached sources only; no DrugBank vocabulary is present. Do not read
test answers for tuning, change frozen datasets or fill human review queues.

Extend synonym enrichment with optional `--cached-labels` and an immutable
`--output` preview containing the catalog fingerprint and each proposed source id.
For openFDA, all generic/substance names must resolve to one Drug; never trust the
search request's drug uid as the label's identity. Restrict this expansion to
prescription labels, veto a brand also found on an unresolved/combination/OTC
product, and retain collision checks. For MedlinePlus, use also-called names only
when the English topic title matches a canonical Disease name, allowing removal
of a terminal `(disease)` or `(disorder)` qualifier. ABOUT links and existing
acronym aliases alone are insufficient evidence of synonym equivalence.

The first preview had 151 candidates. Source review exposed broad-class and
acronym joins, so it was not applied. MeSH drug joins now require a preferred
concept/canonical drug match, with salt normalization only as fallback; narrower
terms cannot anchor a chemical class to a drug, and existing aliases still veto
other-entity conflicts. Simultaneously proposed aliases cannot join unrelated
labels either. Alternatives: append the initial candidates, use benchmark gold
anchors, or hand-write missing brands; rejected for identity errors or leakage.

Apply the final 94 additions to 80 entities: 20 openFDA, 73 MedlinePlus and one
MeSH. Back up the catalog, alias index/matrix, provenance ledger and unlinked
mentions before applying. Synchronize graph synonyms and document MENTIONS;
verify all 94 graph aliases and 45,636 retained mention edges. Encode 87 new alias
texts, reusing existing text vectors, for 138,893 alias-index rows. Source-backed
names remain a retrieval vocabulary, not independently reviewed clinical equivalence.
The pre-existing 40 coverage probes remain 39/40; the missing probe is unresolved.

Refresh the vector control with `scripts.refresh_synonym_corpus`: require only
additive synonym changes, an exact previous paragraph prefix, and a complete
hash-matched corpus/matrix. Preserve every relationship suffix and document row.
Use the unchanged embedding recipe and the existing cached model offline with
two CPU threads. Back up and hash-check all three corpus artifacts before staged
replacement. Re-encode 75 changed paragraphs and preserve 47,593 vectors exactly;
independently verify equality and unit norms. This narrow refresh is unsuitable
for model, relation, document or canonical-name changes; those require a full rebuild.
Alternative: repeat all 47,668 embeddings; rejected because unchanged text with
the same cached model does not require new inference. The 20-alias cap remains.

After application, four of the five dev rows originally marked catalog-absent now
link their anchors exactly. This is a dev linking diagnostic, not an answer score
or a new test result. Keep original `alias_in_catalog` annotations and historical
v2 results intact. The catalog and corpus have new fingerprints, so the published
test table describes the earlier measured snapshot only.

## D061 — Separate population knowledge lookups from medication advice (2026-10-08)

Keep population-plus-medication questions blocked by default. Allow an explicit
impersonal graph lookup beginning with which/what/how many/list/show and containing
a recorded/listed/associated/linked/indicated/contraindicated/side-effect/interaction/
target cue. Any personal cue or medication-advice/action wording overrides that
exception, including mixed requests that append a recommendation to a lookup.
Crisis, emergency, dosage, diagnosis and final-output gates remain in force.
Alternative: remove the population gate or allow every third-person question;
rejected because neither preserves the professional-assessment boundary.

Use fictional disease/drug regressions for the overlapping population/medication
phrases, plus advice controls checked before any model or graph call. All eight
dev sensitive-term questions pass the input gate; this checks routing, not answer
quality or clinical safety. The rule is deliberately narrow and may still refuse
other knowledge phrasings. No held-out answer was used to select regex terms.

## D062 — Normalize only unambiguous planner boolean formats (2026-10-08)

Normalize template `count` integers 0/1 and case-insensitive true/false strings to
booleans. Omit null because this optional flag defaults to false. Reject other
integers, floats, numeric strings, containers and truthy words; an arbitrary number
might be an expected answer or row limit rather than a boolean. Make those flag
semantics explicit in the planner prompt. Keep allowed argument names, tools,
backward references, phase constraints and guarded execution unchanged.
Alternative: cast every value with `bool()` or accept all numbers; rejected because
`"false"` becomes true and result limits become aggregation requests. Fictional
tests check both meanings and show a normalized plan needs no repair call. The
previous dev ValidationErrors did not retain raw provider JSON, so do not attribute
all of them specifically to numeric `count` or claim all format failures are fixed.

## D063 — Share bounded provider backoff without retrying failed answers (2026-10-08)

After a connection/timeout, HTTP 429 or HTTP 5xx failure, persist a pacing deadline
under the existing cross-process provider mutex. Subsequent calls wait 10, 20, 40,
then at most 60 seconds for consecutive transient failures. Respect numeric or
HTTP-date Retry-After hints within the same 60-second ceiling. A successful call
resets the sequence; non-transient errors do not trigger exponential pacing.
Use atomic state replacement and cap waits even after wall-clock changes.

Preserve zero SDK retries: each failed request is still returned as a failure,
charged conservatively when usage is absent, and not secretly replaced by a later
answer. Log only its exception class and delay, never response bodies or prompts.
Keep the provider/model/key and the evaluation's two-second ordinary cooldown and
60-second provider timeout. Alternative: automatically retry each failed evaluation
answer or change provider; rejected because those hide failures or require a new
authorization. Fake-clock tests cover shared clients, escalation, cap, reset,
provider hints, unchanged call count and token accounting. These prove scheduling
behavior, not availability of the free endpoint; real API failures remain reportable.

## D064 — Verify the resumed work on dev and preserve the test snapshot (2026-10-08)

Run one hybrid smoke on the same predeclared 38 dev IDs as D052, retaining every
dev safety/adversarial control. Estimate and enforce at most 200,000 additional
conservative tokens within the existing cumulative cap of 11,344,304; do not reset
the ledger. Keep provider timeout 60 seconds, ordinary cooldown two seconds,
zero SDK retries and cache off. Also bound the whole smoke to 20 minutes. Do not
change QA source or retrieval artifacts while it runs. Alternative: rerun test to
advertise a new score; rejected because that split has already been used.

The smoke completes in 547.42 seconds with 35/38 passes, all 20 safety/adversarial
controls passing, two API timeouts and no other execution errors. A dev typo still
returns no supporting evidence. Preserve those three failures and do not selectively
rerun them. Calls report 47,088 tokens and conservatively charge 61,607; cumulative
additional task charges become 4,465,963 of the approved 6,000,000, leaving 1,534,037.
There are no new unsettled reservations. Two observed ten-second backoffs confirm
that the live pacing path was exercised; they do not prove an availability gain.

Publish development-only aggregates and `docs/reports/t5-improvements.md`, linking
them from README and the historical v2 report. Keep every prior test score and
annotation intact; explicitly mark the measured table as the pre-improvement
snapshot. Vocabulary, prompts and scheduling changed together, so a dev score
difference cannot identify an individual change's effect. No new vector or test
score is claimed. Nine artifact checks pass; verify source/vocabulary fingerprints,
unchanged human queues/datasets, exact reuse of unchanged vectors and live graph
aliases independently. Ruff and 361 non-integration tests pass (15 deselected,
one pre-existing warning). Shut down owned processes and verify closed ports.

## D065 — Repair drug mention extraction and bounded spelling variants (2026-10-08)

The user authorizes all four follow-up steps after T5. Keep the current branch,
frozen v1/v2 datasets, existing provider and six-million-token additional cap.
Continue numbering decisions, and keep new audit/review artifacts separate from
existing human queues. No test-split tuning or external data download is needed.

The dev typo failure has two independent causes: modal constructions can leave a
drug mention unexamined, and adjacent-letter transpositions fall below the existing
token-sort similarity cutoff. Add can/could/may as mention cues and stop mention
spans at be/been/being/used/using/prescribed. Exact catalog mentions still run first.
Before the existing fuzzy fallback, allow Damerau-Levenshtein distance one only
for alphabetic Drug tokens of at least eight characters, excluding known ordinary
words. Limit this new correction path to Drugs; short symbols and other labels
keep the existing rules. Alternative: lower the global similarity cutoff or map
specific benchmark spellings; rejected because both can silently increase false
matches or encode evaluation examples.

Consider every one-edit candidate before selecting: multiple aliases of one drug
are one candidate, but several drugs remain ambiguous regardless of normalized
score differences. Preserve at most five alternatives with the ambiguity flag;
the normal clarification boundary handles them. Do not correct document mentions
in the exact-only ingestion pass. Fictional tests cover transpositions, missing,
extra and replaced letters, similar drug names, exact-match precedence, short
symbols, ordinary words and unknown anchors. All ten dev typo anchors now link
correctly without ambiguity (previously zero); this is a linking diagnostic, not
ten demonstrated correct answers. Full dev evaluation follows after freezing code.

## D066 — Audit historical aliases without assigning human verdicts (2026-10-08)

Add a read-only audit over the complete catalog and recorded enrichment provenance.
Check normalized same-label collisions, different-name cross-label collisions,
short acronym collisions, ordinary/generic words and MeSH joins that cannot be
reproduced under the current stricter rules. Do not read benchmark questions or
answers. A flagged join is not automatically false: genuine equivalence, source
changes and catalog ambiguity need inspection. Alternative: remove every flagged
alias; rejected because mechanical flags do not establish clinical equivalence.

The audit examines 42,975 entities and 95,995 synonym strings, flagging 2,389
entity/alias pairs. Overlapping flags: 402 unreproduced MeSH joins, 511 same-label
collisions, 1,497 different-name cross-label collisions, 228 acronym collisions
and 33 ordinary/generic words. Preserve all flags locally. Create a deterministic
first batch of 100 review tasks, prioritizing unreproduced joins, with decision,
reviewer and notes left null. The remaining 2,289 flagged pairs remain available
outside that first batch; it is not a complete manual audit. Keep the catalog,
vector artifacts and seven older human queues byte-identical. The user alone
assigns human decisions under section 4; no labels are inferred from the flags.

## D067 — Isolate fixture integration and freeze a complete dev diagnostic (2026-10-08)

Run the 13 synthetic integration tests and read-access check against a separate,
authenticated, loopback Neo4j database with all writable paths inside a new ignored
cache directory. Run the remaining CSV-count test read-only against the existing
research graph. All 15 pass. Alternative: load fixtures into the research database;
rejected because test entities would contaminate evaluation. Stop the isolated
server before starting the research server on the same local ports. Preserve both
process identities and logs; only stop this task's owned processes, retaining the
isolated database rather than deleting existing cache files.

Freeze QA source and artifacts before one complete 160-question hybrid dev run.
Keep timeout 60 seconds, cooldown two seconds, zero SDK retries and cache off.
Estimate 450,000-650,000 conservative tokens, enforce an 800,000-token run allowance
and a 90-minute deadline. The run begins at cumulative ledger 9,810,267, beneath
the existing 11,344,304 task cap; accounting is never reset. No selective failure
reruns, fresh vector performance claim or used-test rerun is planned. Alternative:
repeat only the corrected typo questions; rejected because it would omit broader
development regressions and error accounting. New authoring tools and documents
may be prepared while the run is active; measured QA/evaluator code stays frozen.

## D068 — Prepare a human-authored independent evaluation, without invented labels (2026-10-08)

Create 100 blank slots with predeclared quotas: 28 graph questions (seven each
single-hop/reverse/count/multi-hop), 12 lexical variants (four each brand/lay/typo),
15 text-only, 15 graph-plus-text, 10 out-of-scope, 10 safety and 10 adversarial.
Use cached sources and the frozen candidate only. Alternative: generate another
template dataset automatically or relabel the observed v2 test as independent;
rejected because neither addresses evaluation independence. The user authors and
reviews questions/gold; the assistant leaves identities, attestations and labels
null. The same human can conduct a separate review pass, disclosed as a limitation.

Add an offline authoring/readiness tool, immutable source manifest, blank JSONL
queue and readable CSV copies. Fingerprint source, graph CSV, catalog, text and
vector artifacts. Compare hashes of normalized old question wording only; no old
test answers are inspected. The gate rejects incomplete review, duplicate wording,
changed quotas, unknown evidence/target IDs and source drift. It never executes
gold queries or authorizes provider calls; semantic correctness and novelty remain
human checks. Tests use fictional labels only. CSV formula-like strings are escaped.

Predeclare blinded human answer scoring for the 30 text/mixed cases as primary;
strict phrase matching stays a diagnostic. Report structural, refusal and redline
results separately. A reviewed immutable dataset, blinded scoring forms and an
explicit finite run/budget registration are needed before future model calls.
Preparation is complete when the blank packet and gate work; human authoring,
clinical expertise and new held-out performance remain unclaimed. Do not change
existing human queues, datasets or aliases automatically.
