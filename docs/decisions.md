# Implementation decisions

Each entry records a decision, its reason, and alternatives. All runtime and data artifacts remain local.

## Key decisions at a glance

The log below is chronological and long; these are the entries that shape the
system and its evaluation today.

| Area | Decision | Entry |
|---|---|---|
| Graph | Orient Disease→Disease edges only from MONDO `is_a`; drop reciprocal CSV duplicates | D004 |
| Evaluation | Black-box process boundary; gold computed from the CSV transform, not the graph | D008 |
| Retrieval | Bound rows, hops, anchors and evidence size; disclose truncation | D015 |
| Service | SSE streams only the verified final answer; metadata-only OpenTelemetry spans | D019 |
| Provenance | Keep both sides of PrimeKG/FDA conflicts, each with its source | D021 |
| Extraction | FDA assertions only between existing entities, each backed by a verbatim quote | D024, D028 |
| Safety | Refuse first-person crises, doses and diagnoses; answer impersonal knowledge questions | D047, D061 |
| Retrieval | Expansion rows carry relation type and direction | D047 |
| Linking | Common-word aliases need upper case; same-name Disease/Phenotype resolved by the asked relation | D047, D048 |
| Retrieval | Empty single-template result falls back to documents about the anchor | D048 |
| Vocabulary | Brand and lay names from MeSH, openFDA and MedlinePlus with collision rules | D049, D060 |
| Linking | One-edit typo matching for long drug names | D065 |
| Vocabulary | Quarantine 28 alias mappings rejected by source review, reversibly at query time | D072 |
| Benchmark | v2: common entities, natural wording, clinical multi-hop, sensitive terms | D050 |
| Benchmark | Vector control paragraphs include catalog synonyms | D051 |
| Measurement | API-error rule: rerun whole rounds, never single questions | D054, D058 |
| Scoring | Entity support is reported separately from (unevaluated) semantic support | D073 |
| LLM | Keep the cloud model as default; local open-weight models are supported and measured on dev | D083, D084 |
| Evaluation | Stage-wise diagnosis and per-question ledgers decide whether a fix worked | D086, D089 |
| Answer | Rows of the final graph query are always reported; the model words, code completes | D087 |
| Benchmark | v3: capability coverage, perturbations, fresh batches per fix round, a sealed test run once | D091–D094 |
| Evaluation | v3 failure severity separates declines, incomplete and wrong answers, and policy breaches | D095 |
| Demo | Self-contained web page shows answers, routes, executed Cypher and evidence; no frontend build | D096 |
| Benchmark | LiveQA v2: NLM focus/keyword pairs, exact catalog links, CSV gold, paired original/summary wording | D097 |
| Benchmark | Fresh v3 batch b3, frozen before RxNorm and routing changes, with all previous anchors excluded | D098 |
| Vocabulary | RxNorm single-ingredient brands with unique Drug joins, global unsafe-name exclusion and corpus-word filters | D099 |
| Safety / benchmark | Recognize IU and units in dose guards; verify LiveQA in memory without requiring v1 | D100 |
| Vocabulary | Keep RxNorm aliases exact-only through openFDA parsing, verify Neo4j before apply, exclude 45 reviewed names and quarantine 11 Pentastarch aliases | D101 |
| Answer | Decline empty verified bodies; recognize bounded opening decline paraphrases | D102 |
| Safety | Answer the knowledge part with a fixed notice; keep emergencies, dose-only requests and personal decisions blocked | D103 |
| Safety | Personal medication decisions without a dose are blocked; "Can I take A with B?" is answered behind a notice | D104 |
| Linking | Corrected names are confirmed ("Did you mean …?") or used with a visible note; vector matches never become silent anchors | D105 |
| Linking | A match that covers part of a phrase ("jock itch" → ITCH) is checked by the model choosing among catalog entries; a different choice is asked back, never used silently | D106 |
| Linking | Names with a missing or extra space ("heartfailure", "para cetamol") are matched without spaces and used with a note | D107 |
| Routing | An unrouted question about one name without a relation word is read by the model as a choice with probabilities: a clear reading is answered with a note, a spread one is asked | D108 |
| Linking | The end of a contraction or possessive ("what's", "mother's") never starts a name, so "What's warfarin" is Warfarin, not (S)-Warfarin | D109 |

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
deviations and costs in `docs/history/reports/v2-results.md`. Alternative: replace archived
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

Publish development-only aggregates and `docs/history/reports/t5-improvements.md`, linking
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

## D069 — Publish complete dev evidence and stop at the human-review boundary (2026-10-08)

The frozen 160-case hybrid dev run completes in 2,912.17 seconds: 140/160 passes
(87.50%), or 140/155 (90.32%) excluding the five API-timeout questions. Six query
syntax errors and nine other answer-score failures remain. All ten typo questions
and all 20 safety/adversarial controls pass; sensitive-term false refusals are
0/8, with 7/8 answer passes. Alternative: report only the corrected typo subgroup
or compare this dev score directly with the prior test score; rejected because
neither represents the full development diagnostic or independent performance.
No QA/scoring code changes during the run; no failed question is selectively
rerun. Preserve all raw records and expose separate API/capability error counts.

The run makes 243 provider calls, reporting 353,298 and conservatively charging
391,504 tokens. Additional task usage is now 4,857,467 / 6,000,000, leaving
1,142,533. No new reservation remains unsettled; the four historical reservations
remain part of the cumulative accounting. Source/vocabulary/corpus/matrix and
both datasets retain their pre-run hashes. The original seven human queues are
unchanged; both new queues have 100 records and null human decision fields.

Publish the full dev and implementation aggregates, update README/summary links,
and retain the prior test and 38-case smoke reports as historical snapshots. Ruff,
412 non-integration tests, all 15 integration tests and nine artifact checks pass.
Stop the task-owned research server and launcher after the evaluator exits;
verify closed ports 7474/7687. Keep the isolated database and private logs locally.
No push, merge, installation, external file change or data download occurs.
Automated work is complete; user-authored questions, gold and alias decisions
remain pending under section 4. No independent evaluation or human validation is
claimed before that input and a separately registered finite run/scoring plan.

## D070 — Add an explicitly authorized multi-agent source-review lane (2026-10-09)

The user explains they lack domain expertise and explicitly asks for subagents
with tailored prompts to perform the review. Proceed without requesting the same
authorization again. Preserve the prior human queues and their null attestations;
write distinct AI judgments and provenance. Alternative: fill human_* fields with
agent decisions or insist that an untrained user certify medical truth; rejected
because the former falsifies provenance and the latter does not improve evidence.

Use two fresh-context reviewers for all 100 priority alias pairs, emphasizing
direct concept equivalence and counterexamples respectively. Give both the same
cached MeSH concepts, terms, relations and scope notes, stripped of previous audit
flags and decisions. They cannot see each other's first pass. A third agent audits
the evaluation protocol and authors 12 source-grounded pilot text questions; an
available reviewer subsequently checks questions/evidence before seeing proposed
answers. This bounded pilot tests the AI author/reviewer workflow, not the existing
100-case human benchmark. The root agent checks source quotes, identities, complete
coverage, conflicts and file preservation. No current QA source or scoring changes.

Supported/unsupported/uncertain refer to source support for exact identity, not
clinical truth. A class or sibling concept is not automatically an exact alias;
absence alone is not proof of incorrectness. Preserve disagreements rather than
forcing majority agreement. Shared model and evidence create correlated errors.
Do not apply catalog changes or start a new model evaluation from this review.
No new data is downloaded. Existing GLM provider accounting remains separate from
Codex's agent work; zero additional project-provider calls must not be described
as zero AI usage. Prompts and protocol are recorded in docs/evaluation/ai-review-protocol.md.

## D071 — Preserve source uncertainty and separate review from system evaluation (2026-10-09)

Both alias reviewers return 6 supported, 28 unsupported and 66 uncertain decisions
for the 100 priority pairs. Decisions agree on all pairs; relationship labels
agree on 98. Preserve the two relationship disagreements and all raw first passes.
Validate all 780 submitted quote locations, not only substring presence, allowing
permuted MeSH terms that reuse a TermUI. Raw reviewer A uses Clinical_validation
and B uses clinical_validation; retain raw bytes and normalize only aggregate
provenance. Alternative: infer accuracy from agreement or silently standardize
frozen raw files; rejected because shared biases remain and provenance would drift.

After the blind passes, search the 483 existing openFDA cache files for all 66
uncertain aliases using exact normalized brand and canonical ingredient identity.
No pair is resolved: 65 have no exact brand match; one documents a sodium salt
rather than the exact canonical moiety. A no-match is not a false-alias verdict.
Do not silently introduce salt stripping, partial-brand matching, product-name
familiarity or new downloads to force resolution. Alternative: accept these
engineering normalizations as chemical identity evidence; rejected because the
review explicitly tests exact equivalence. All cache hashes and matched fields
are checked; no source files or catalog entries change.

Freeze the pilot auditor's first-pass hash before author-answer comparison.
The audit supports all 12 reference answers, with six optional question/rubric
clarifications and no required factual corrections. Preserve original author and
blind references, attach clarification notes in a separate readable table, and
retain AI origin. Alternative: edit the frozen answers to match the auditor or
count the cases as human gold; rejected because neither preserves the observed
review process. Verify the 23 author spans, 24 full source chunks and 60 auditor
quote occurrences against the stored corpus. Semantic novelty is not established.

Report seven evaluation-methodology recommendations and the synthetic scorer
counterexamples without treating constructed inputs as runtime failures. The
existing readiness gate explicitly remains schema-only and never authorizes a
run. Keep previous automatic scores as historical diagnostics and disclose their
limits; do not modify scoring, revisit old test outputs or create a new performance
claim during this review. Apply no alias changes. Preserve all nine human queues,
both frozen datasets, catalog and vector artifacts. Provider accounting is unchanged.
Publish prompts, aggregate results, readable local evidence tables and the report;
only these documentation/aggregate changes enter a local commit.

Ruff and all 412 non-integration tests pass. The initial sandbox attempt stalls
after three tests; stop only its two verified processes and rerun the whole suite
with approved escalation and a new project-local temporary directory. It finishes
in 4.83 seconds, with 15 integration tests deselected and one existing dependency
deprecation warning. No dependency upgrade or service startup is warranted by
this documentation/evidence-only change. Recheck all preserved hashes afterward.

## D072 — Implement reviewed alias conflicts as reversible query-time quarantine (2026-10-15)

The user asks to continue after the AI review report. Treat this as authorization
to implement its engineering improvements, retaining section-4 boundaries. Use
three implementation workers with disjoint files and a separate read-only audit;
the root integrates and checks the result. All source, documentation and commits
remain English. No new data, provider/model change, human labels, historical
benchmark mutation, external-file change, push or merge is needed.

Encode exactly the 28 agreed unsupported entity/name pairs from the frozen source
review in medkg_data.alias_policy. This is a reversible engineering quarantine,
not a new molecular or clinical conclusion. Preserve the six supported and 66
uncertain pairs, every canonical identity and valid other owners. Exclude reviewed
pairs from exact, fuzzy and stale alias-vector matching; reserve full rejected
phrases so shorter names cannot reintroduce the same mapping. The query boundary
requests an exact drug name before planning/retrieval when such a phrase remains
unresolved, in both hybrid and vector modes. Scoring and answer verification must
honor the same phrase boundary. Future alias embedding, corpus generation and
enrichment also honor the policy, but are not run on the stored artifacts here.

Alternative: rewrite catalog, embeddings and graph immediately; rejected because
it broadens this bounded correction into a data migration and loses the original
comparison snapshot without additional reconstruction. Keep catalog, vector files,
graph and source bytes intact, and explicitly disclose that old derived data still
contain historical aliases. The query gate covers the reviewed explicit names;
it is not a complete historical mention-edge cleanup or a general terminology
normalizer. Conservative clarification can reduce coverage for broad factual
questions. Do not infer the status of other aliases or apply salt equivalence.

## D073 — Strengthen deterministic diagnostics and evidence readiness (2026-10-15)

Advance the scorer to deterministic-3.6 without rescoring historical outputs.
Mixed text/graph questions require every expected graph UID in both answer and
evidence, with nonempty gold. Inspect the whole displayed answer for bounded
safety-policy content checks independently of its own refusal/category flags;
footer delimiters cannot hide instructions. Preserve backward-compatible fields,
but expose entity_supported, diagnostic_passed and metric semantics explicitly.
Semantic support stays null/not_evaluated. Alternative: call a regex or entity
overlap a semantic/clinical judge; rejected because neither establishes entailment
or comprehensive safety. Separate claim/content review remains required.

Extend readiness with two cases per safety subtype, explicit safety and adversarial
contracts, exact text locators and safe graph selections. Graph selections stream
only the frozen CSV, allow one or two explicit relation/direction steps, preserve
self-edges and collapse duplicate paths. Compare the complete sorted target set
and count with the declared gold; never execute supplied query/code. Text checks
verify offsets, hashes, document joins and claim-span references; they cannot prove
the question or claim means the cited source. Schema-2 manifests freeze evaluator,
validator, scripts, protocols, dependencies and nonsecret environment inventory.
Old packets/queues remain unchanged and explicitly unfinished. Readiness never
authorizes model calls. Alternatives: free-text evidence notes or unrestricted
queries; rejected because the former is unreconstructable and the latter adds
unnecessary execution risk.

## D074 — Deliver offline blind scoring and a separate revised development pilot (2026-10-15)

Implement an offline prepare/check/summarize workflow with seeded per-case A/B
ordering, stripped system metadata, opaque IDs, private mapping and trusted hash
receipt. Bind every review to case, answer and rubric hashes; keep authorship,
reviewer provenance and unresolved judgments explicit. Require claim coverage,
contradiction/unsupported-content/uncertainty review and case-specific safety
behaviors; retain API/system failures in the all-case denominator. Alternative:
ask agents to inspect named-system outputs or repeatedly vote until they agree;
rejected because either encourages answer anchoring and obscures uncertainty.
This tool stores review judgments, not a semantic oracle or clinical certification.

Apply the six saved wording/rubric clarifications to a new 12-case pilot-r2 copy,
preserving original references and every first-pass artifact. Keep 27 required
claims with 23 source spans, distinguish optional details, and label the copy as
AI-authored development material already exposed to review. It is not a fresh
held-out benchmark or a substitute for human labels. Demonstrate blinded ingestion
with synthetic fixtures only; make no new provider calls or performance claims.

One tooling worker's initial broad filename/content search inadvertently exposed
some historical text_v1 questions. The worker disclosed this immediately, stopped
that search and confined subsequent work to named code/protocol files and synthetic
fixtures. It authored no new benchmark and produced no medical labels. Record this
exposure rather than claiming the entire implementation team was answer/question
blind; the historical pilot authoring record and frozen files remain unchanged.

## D075 — Verify boundaries independently and retain historical evidence (2026-10-15)

Independent code audit reproduces two implementation defects: shorter retained
aliases bypass the full-name quarantine in scoring/output verification, and global
citation-ID replacement changes ordinary answer numbers. Fix both and add boundary
tests; the auditor independently repeats the probes. Preserve answer prose and only
rewrite exact case-sensitive bracket citations. Carry known identity clues into
prepare/check/summary records. Separate response-failure counts from observed
reviewer-labeled safety violations while keeping both in conservative denominators.
Alternative: hide those defects in aggregate test counts or silently edit raw
answers; rejected because auditability and factual answer preservation are required.

Ruff and 593 non-integration tests pass; all nine cached-artifact checks pass.
The full suite runs in 9.82 seconds with 15 integration tests deselected and one
existing Starlette deprecation warning. Use approved execution with a new local
temporary directory because prior full-suite sandbox runs repeatedly stalled.
Integration services are not needed to test this pre-retrieval policy and offline
evaluation tooling. A real cached-CSV selection reconstructs two targets and rejects
an altered count. The synthetic blind smoke retains a failed answer and all missing
reviews, preserves an ordinary numeric count and discloses an explicit identity clue.
None of these is a new QA performance observation.

Verify 70 preserved files, including all nine human queues, old datasets, processed
data and earlier AI review artifacts, and compare final code with the auditor's
hashes. Create a separate schema-2 development-candidate snapshot without generating
another human queue or authorizing model calls. Existing GLM accounting remains
10,201,771 cumulative conservative tokens, with no added provider calls; Codex agent
work is separate usage. Keep four pre-existing invalid-run summary files untracked,
preserve all local evidence, and make only explicitly staged local commits.

## D076 — Re-review the implementation with independent synthetic counterexamples (2026-10-15)

The user explicitly requests another independent subagent review and fixes for
confirmed findings. Assign three fresh-context reviewers to alias/scoring,
evidence/readiness and blinded review. They first inspect without changing source,
then receive disjoint repair ownership. The root reproduces representative failures
and integrates; reviewers cross-check other owners' fixes. Use named source/tests
and synthetic fixtures, without reopening frozen benchmark questions or old QA
outputs. No human labels, medical judgments, downloads or provider calls are needed.

Known evidence categories must match their required kind before dispatch, so an
aggregation or multi-hop case cannot skip graph reconstruction by claiming to be a
safety/text case. Keep generic kind-only rows supported; zero evidence rows remain
explicit for safety/refusal-only inputs. Reject malformed authoring objects and
invalid/duplicate IDs before indexing. Alternative: rely solely on the stricter
human queue validator; rejected because the reusable AI evidence lane is callable
directly and must not report a bypassed graph check as evidence integrity.

Advance the scorer to deterministic-3.7. Mask bounded quotation/code/blockquote
spans before finding required affirmative safety statements, retaining the original
displayed text for prohibited-content checks. Keep contractions and possessives
usable, and reject negated protective statements. These finite rules address
reproduced counterexamples; they are not a general quotation, semantic or clinical
classifier. Preserve historical results and their original scorer versions.
Alternative: accept keywords or claimed refusal flags as sufficient support;
rejected because reported examples need not perform the required action.

## D077 — Bind audit records to the bytes and dependencies actually checked (2026-10-15)

Allocate opaque source IDs outside both original IDs and bracket references in
either answer. Unknown citations remain unknown rather than becoming valid through
masking. Keep simultaneous exact bracket replacement and unchanged factual prose.
The private summary output guard covers both the supplied public packet directory
and its original trusted-manifest path, including when the public packet is copied.
This is a custody safeguard for known paths, not an access-control system.

Parse and hash returned labels and authenticated blind-review assets from the same
captured bytes. Readiness similarly binds queue_sha256 to parsed queue bytes,
rejects detected concurrent queue edits, and checks frozen source hashes again
after validation. A later file save requires another check. Alternative: parse then
hash a fresh read; rejected because a concurrent save can attach the digest of an
invalid or incomplete file to a result from an earlier version. No filesystem lock
or atomic multi-file snapshot is claimed.

Evaluation checkpoints now hash a named inventory of the selected QA source tree,
current evaluator source and current medkg_data dependencies. The host scorer's
alias policy and lexicon remain effective when --system-source chooses an older QA
implementation, so both must participate in resume compatibility. Distinct path
and role names prevent content concatenation or renamed files from concealing a
change. Historical checkpoints are retained; mismatched fingerprints require a
new output path rather than weakening the resume guard.

## D078 — Cross-verify the follow-up repairs and preserve earlier evidence (2026-10-15)

Cross-review reproduces single-quote/possessive edges in the first scoring repair
and source drift after readiness's initial snapshot. Fix and retest them before
closing the round. A different agent verifies the final scorer and checkpoint
fingerprint, and the root inspects and reruns the blind-review regressions.
Synthetic alias probes find no additional runtime defect across all 28 policy
pairs; 300 synthetic graph selections match a separate in-memory oracle. Scope
these conclusions to the explicit cases and reviewed code.

Ruff passes and the complete non-integration suite has 677 passing tests, with
15 integration tests deselected and one existing Starlette deprecation warning.
The run takes 12.70 seconds using the project interpreter and a fresh local test
directory under approved execution, avoiding the prior sandbox stall. All nine
cached-artifact checks pass. Preserve and recheck 81 frozen files from the start
record, including earlier review/implementation evidence and all human queues.
Retain raw before/after probes and independent cross-check hashes separately.

Prepare a new development snapshot and aggregate engineering report without
creating a human queue, rerunning a benchmark or modifying earlier manifests.
The project-provider ledger stays unchanged, and no service or installation is
needed. Make two explicitly staged local commits on the existing branch; no push,
merge or history change. Alternatives such as rerunning historical test responses,
calling model judges or rewriting stored source artifacts would not validate these
specific code repairs and are outside this round.

## D079 — Verify isolated integration and bounded live public interfaces (2026-10-15)

The user explicitly asks to run integration tests, confirm the complete chain and
repair issues. Reuse the installed Neo4j/JDK and project environment. Run fixture
writes in a newly authenticated loopback database with task-local writable paths;
run CSV count comparison and operational smoke against the existing research
graph with a temporary read-only configuration. Servers run sequentially on the
same ports. Keep the installation configuration, raw data, frozen questions and
human queues unchanged. No downloads or dependencies are needed.

Add persistent tests for the public CLI, stdio conversation history and HTTP/SSE
with a real fixture database and FakeLLM. Separately freeze four operational
requests through CLI hybrid, CLI vector, HTTP and SSE using the existing provider.
Use cached CPU embeddings offline, 60-second provider timeout, two-second cooldown,
zero SDK retries, cache off and a 100,000-token incremental cap. This sits below the
prior authorized cumulative cap of 11,344,304; starting balance is 10,201,771.
Alternative: equate FakeLLM tests or /ready configuration with provider availability;
rejected because neither performs a real generation request.

The first live group completes three of four requests; vector generation times
out. Preserve all responses and conservative failure charges. Register exactly one
complete-group retry with the same inputs/settings under the same overall cap.
All four retry requests complete. Across both groups there are eight provider
calls, one timeout and 27,118 conservative tokens added; cumulative accounting is
10,228,889. These are operational smoke observations, not independent QA scores,
semantic accuracy, clinical validation or an availability guarantee. No historical
test output is reopened or selectively repaired.

## D080 — Make fixture isolation mandatory and verify owned-service cleanup (2026-10-15)

Reviewing the integration path exposes an unsafe default: the fixture could opt
into mixed imports unless MEDKG_SYNTHETIC_ONLY was set. Tests now always require an
empty or synthetic-only database and close their driver even when setup fails.
The importer also treats missing UID properties as non-fixture nodes; Cypher null
semantics previously excluded them from the guard count. Reproduce this with a
unique temporary sentinel in the isolated database: the new test first fails,
then passes after the guard repair. Remove only that owned sentinel in finally.
Retain the isolated database and update README to use two separate test phases.
The standalone importer's explicit --allow-mixed option is unchanged; tests never
use it. Alternative: rely on an optional environment flag or cleanup after mixed
imports; rejected because setup should prevent research-graph contamination.

The local test harness also needs Windows-specific cleanup corrections. Compare
launcher timestamps at the precision retained by PowerShell JSON, still checking
PID, command line and ancestry. Stop the live HTTP launcher and its owned process
tree, then wait for port closure; an immediate check after launcher exit could
precede child/socket teardown. The first run's cleanup assertion and recovered
results remain in the private evidence. These are task-harness repairs, not changes
to the QA service's response behavior.

Final results: 18 isolated database/interface tests plus one read-only real-CSV
comparison pass, as do all 677 non-integration tests, Ruff and nine artifact checks.
The source count comparison passes before the fixture-only guard change; QA source
hashes remain identical throughout both live groups. Both vector retrieval paths
return eight cached hits, all 16 research indexes are online, count answers match
retrieved rows, and quarantine requests use zero model calls. Research graph counts
stay unchanged, with no synthetic nodes. Preserve 82 prior files, all failed and
successful observations and usage accounting. Verify owned database PIDs exited
and ports 7474, 7687 and 18080 closed. No push, merge or service autostart occurs.

## D081 — Final v2 test round and documentation consolidation (2026-10-16)

The work after the first accepted v2 round (D059–D080) was developed on dev only.
Run the current code once on the v2 test split with the accepted settings (60 s
provider timeout, 2 s cooldown, cache off) and report it beside the first round,
both scored by `deterministic-3.7`: hybrid 204/240 (85.0%) versus 194/240 (80.8%);
8 API-error questions (valid), no safety or injection regression. Multi-hop and
reverse lose a few cases (partly provider timeouts); intersection questions keep
failing on generated Cypher syntax. This is the second use of the test split and
is disclosed as such; no change is tuned on these answers.

Stop extending the evaluation-governance tooling: the benchmark, scorer and
review tools are sufficient for the project's claims. Move process reports to
`docs/history/` with an index, add `docs/evaluation.md` as the single results page,
add a key-decisions table here, and rewrite the README as a one-page entry point.
Alternatives: build a fresh human-authored test set first (deferred: needs people
the project does not have) or keep publishing round-by-round reports in the README
(rejected: the main result was buried).

## D082 — Deterministic intersection template (2026-10-16)

All seven Cypher syntax errors in the final v2 test round were "drugs indicated for
both A and B" questions, which the LLM planner sent to free-form Text2Cypher.
`templates.query(..., shared=True)` now returns targets linked to every anchor
(aggregating per target and requiring all anchors), never an anchor itself. The
router uses it when a question has exactly two anchors of one label and an
intersection cue (both, in common, shared, common) outside the entity names
("common cold" is not a cue). Exclusions ("but not") and mixed-label questions
stay with the planner. The planner accepts a boolean `shared` argument but its
prompt is unchanged: a first version that advertised `shared` in the prompt made
the planner chain templates for exclusion questions, dropping the NOT EXISTS
constraint (dev exclusions 0/5); restoring the prompt restored them (5/5).

Verified on dev only. Offline, routing changes for exactly the 11 dev intersection
questions and no other question. Live, the 16 dev multi-constraint questions go
from 11/16 (previous full dev run) to 16/16; the four former syntax errors pass.
The test split is not rerun for this change.

## D083 — Local LLM backend, compared on dev; cloud model stays default (2026-10-16)

Question: would the local `qwen3.5:9b` (Ollama, RTX 5060 Laptop 8 GB) be a better
LLM than the free cloud `glm-4.5-flash`? It would remove rate limits, timeouts and
the cooldown, keep questions on the machine and pin the weights by digest.

Making it runnable needed three changes. `LLM_THINKING_PARAM` selects how thinking
is disabled (`thinking` for GLM, unchanged default; `reasoning_effort` for
OpenAI-style providers and Ollama); with thinking on, qwen3.5 spent the whole
1,400-token budget reasoning and returned empty content. `ollama/qwen3.5-9b.Modelfile` builds
`medkg-qwen3.5-9b` with a 12,288-token context (Ollama's default 4,096 would
silently truncate the 7% of logged prompts above it; maximum 8,295) and presence
penalty 0 (upstream default 1.5, which penalises every repeated token; the cloud
runs use greedy, penalty-free decoding). Run summaries and checkpoints now record
model, endpoint host and thinking parameter, never the key.

Both models then ran the full v2 dev split (160 questions) on the same commit and
code hash, phase 3, one round each:

| | glm-4.5-flash | medkg-qwen3.5-9b (Q4_K_M) |
|---|---:|---:|
| Passed | **148/160 (92.5%)** | 124/160 (77.5%) |
| API-error questions | 2 (timeouts) | 0 |
| Median / p90 latency | 7.8 s / 27.0 s | **3.6 s / 11.1 s** |
| Wall time | 33.7 min | **12.6 min** |

Discordant pairs: 26 questions only GLM passed, 2 only the local model passed (one
of them a GLM timeout). The local model's losses are in planning (11 different
plans, mostly empty results on multi-hop chains; multi-hop 3/20 versus 16/20), 7
invalid plans or Cypher (fail-closed errors, including 3 out-of-scope/injection
questions that should have been refused politely; no unsafe query ran), and 8
cases with identical retrieved evidence where it wrote a wrong answer (for example
stating that brand name Tyzavan was absent instead of answering for vancomycin).
Templates, counts and safety were unaffected (aggregation, reverse and safety
100% for both).

Decision: keep `glm-4.5-flash` as the default and the reported model; the local
backend is documented as a supported, private, faster but weaker alternative. The
test split is not used. Caveat: prompts were developed against GLM, so the gap
may partly be prompt fit; the 27B model (17 GB) does not fit the GPU. Options if
a local model is needed later: thinking on for the planner only, prompt
adaptation on dev, or fine-tuning the planner on dev-style plans, each measured
on dev first.

## D084 — Open-weight GLM-4.7-Flash as the reproducible local option (2026-10-17)

Goal: a free LLM whose exact weights can be pinned. `glm-4.7-flash` is listed as
free on Z.ai and its weights are public (MIT, 30B total / ~3B active MoE,
`zai-org/GLM-4.7-Flash`). Its free cloud endpoint was unusable for measurement:
on the evening of 2026-10-16 only 3 of 21 calls succeeded (HTTP 429, code 1305,
"model overloaded"), while a valid round needs about 94% (D054). The same weights
run locally instead: Ollama `glm-4.7-flash:q4_K_M`, blob
`sha256:9eba2761cf0b88b8bc11a065a7b5b47f1b13ce820e8e492cb1010b450f9ec950`
(19,019,269,280 bytes), wrapped by `ollama/glm-4.7-flash.Modelfile` (12,288-token
context; upstream has no presence penalty). On the 8 GB laptop GPU with 32 GB RAM
it runs 31% on GPU and 69% on CPU at about 41 tokens/s, because only ~3B
parameters are active per token.

Full v2 dev split, same commit and code hash as D083, one round:

| | glm-4.5-flash (cloud) | GLM-4.7-Flash (local) | qwen3.5:9b (local) |
|---|---:|---:|---:|
| Passed | **148/160 (92.5%)** | 132/160 (82.5%) | 124/160 (77.5%) |
| Multi-hop | 16/20 | 12/20 | 3/20 |
| API-error questions | 2 | 0 | 0 |
| Median latency | 7.8 s | **3.3 s** | 3.6 s |

Against the cloud model: 20 questions only the cloud model passed, 4 only the
local GLM passed. The 20 are 8 different (wrong) plans, 4 invalid plans
(validation errors) and 8 answers written from evidence identical to the cloud
run but incomplete (one of nine indications for Tyzavan; "Count: N" applied to
list questions). Safety, injection, counts and reverse lookups are 100%.

Decision: the cloud `glm-4.5-flash` stays the default and reported model. Among
local options, GLM-4.7-Flash replaces qwen3.5:9b as the recommended one when 32 GB
RAM is available (qwen3.5:9b remains the option that fits an 8 GB GPU alone). The
test split is not used. Two changes would address most local losses and are
measured on dev before any adoption: rendering template entity lists
deterministically instead of relying on the model to copy every row, and
schema-constrained planner output.

## D085 — Explicit name mappings and query meaning in answer evidence (2026-10-17)

Gemma 4 26B-A4B (Apache 2.0, MoE with ~4B active parameters, QAT 4-bit,
`ollama/gemma4-26b.Modelfile`) was chosen as the strongest local candidate that
runs stably on the 8 GB GPU / 32 GB RAM laptop (qwen3.6-35B-A3B at 24 GB leaves no
memory headroom during an evaluation run). On the D083 code it scored 127/160: 21
of its 24 losses were answers claiming "no evidence" over rows that answered the
question. It did not accept that a brand name in the question (Arikayce, Gocovri)
refers to the canonical entity in the rows, or that shared-target rows already are
the requested intersection.

Change (all models): the answer evidence carries `question_entities` (each mention,
the entity, uid and type it was linked to), and each template query carries a
one-sentence description of its rows (`templates.describe`). The prompt explains
both. Full v2 dev, one round each, same code hash:

| | before (D083/D084 code) | after (D085) | fixed | regressed |
|---|---:|---:|---:|---:|
| glm-4.5-flash, cloud | 148/160 | 146/160 | 1 | 3 |
| Gemma 4 26B-A4B, local | 127/160 | **140/160** | 13 | 0 |
| GLM-4.7-Flash, local | 132/160 | 135/160 | 8 | 5 |

Per-question ledgers, not totals, decide whether a fix worked. Of the 8
regressions, 5 are planner outputs that changed although the planner's prompt and
input did not: both the cloud and the local models vary between runs at
temperature 0. Single-round comparisons therefore carry a noise of a few
questions; a repeated identical run to measure it was started and paused
(29/160, checkpoint kept). GLM-4.7 re-downloaded with the identical blob digest
recorded in D084.

Agreed next steps: a stage-wise evaluator (linking, routing, retrieval, generation,
and the first failing stage per question) from the gold fields the v2 dataset
already has; an oracle-evidence mode that scores generation alone; the noise
baseline; then a second round of fixes on the chosen local model (strict faithful
reporting, deterministic entity lists, schema-constrained plans), each verified per
question. The answer layer reports the knowledge base faithfully; knowledge-base
errors are a separate data-quality metric, estimated first by sampling against FDA
labels. The final comparison uses each system's best configuration on a fresh
held-out v3 test split.

## D086 — Stage-wise diagnosis; generated-query descriptions and faithful reporting (2026-10-17)

`eval/stages.py` scores a recorded run per stage from gold the v2 dataset already
carries (anchor_uids, intent, expected, expected_count), without model calls:
linking, routing (template intent), retrieval (the evidence contains the gold
entities, mirroring the scorer's recall rule) and generation. Each failing
question is attributed to generation when its evidence sufficed, otherwise to the
first failing earlier stage; with a baseline it prints the per-question ledger
(fixed / still failing / regressed). A repeated identical Gemma 4 run gave the same
140/160 with the same 20 failures at the same stages (no pass/fail flips), so its
ledgers are not dominated by run-to-run noise; the cloud model and GLM-4.7 did show
planner variation.

On the D085 runs retrieval was sufficient for 98% of Gemma's answerable questions;
12 of its 20 failures were answers denying evidence that contained the gold
entities, including multi-hop questions whose own generated Cypher returned exactly
the gold set. Changes: generated queries carry a description (the question they
were generated for; each row satisfies all of its constraints); the answer prompt
states that rows returned by an executed graph query are the knowledge graph's
answer, never to be denied or rejected with outside knowledge; relation phrasing
("linked to", "reported for", "present with") no longer counts as an unresolved
name, which had blocked template routing (single-turn dev routing with a gold
intent 71/84 -> 82/84). Dev: Gemma 140 -> 144 (6 fixed, all targeted; 2 regressed:
one incomplete long list, one scorer alias collision), cloud 146 -> 147 (2
regressions were provider timeouts).

## D087 — The final graph query's results are always reported (2026-10-17)

Faithful reporting is enforced in code. When the final graph query step (the only
graph step, or one chained on earlier outputs) returned entity rows, names the
answer omits are appended ("Also recorded in the knowledge graph: ..."); an answer
naming none of them is replaced by the list. Names are matched longest first so a
name inside a longer reported name does not count. Counts and two independent lists
left for the model to intersect are not touched, and an output-safety refusal (e.g.
a dose instruction) takes precedence: the safety check runs first. An explicit
model refusal over returned rows is therefore reported as those rows.

## D088 — Linking and routing corrections found by the stage diagnosis (2026-10-17)

- PrimeKG grouped nodes with a truncated label ("nephrotic syndrome,", "Meckel
  syndrome,", "Carney complex,") shadowed the MONDO disease of that name; such a
  label is no longer a linkable name when another entity of the same label has it.
- "Which drugs cause X?" was routed, in the Disease reading, to drugs_for (the
  treatments for X). Drug words with a causation verb no longer take a Disease
  template.
- "When should <drug> not be used?" matched no contraindication pattern and went to
  the planner; the router's contraindication wording now covers it.
Route diffs over all 400 v2 questions changed only the intended questions, each to
its gold intent. The remaining dev routing miss is a brand name absent from the
catalog (Rubraca); it is not patched per question: brand coverage is a separate
data task.

## D089 — Scorer 3.8: a shared name credits the entity it names (2026-10-17)

Entity extraction credited every entity sharing an alias key: "GAPDH" also counted
GAPDHS (whose symbol normalizes to the same key through the plural strip), and a
subtype name listed as a synonym of its grouped parent counted the parent too. When
several entities share a key, the scorer now credits only the entity whose own
canonical name is the text as written (case and punctuation folded, no plural
strip); otherwise the name stays ambiguous. The rule does not consult gold and
moves scores in both directions. All saved runs were rescored offline
(`*_rescored_v38_summary.json`, no model calls): v2 test final 204 -> 209/240
(87.1%), first round 194 -> 197 (82.1%), pure-vector control 78 -> 80 (33.3%); dev
cloud D086 147 -> 150, Gemma 4 D086 144 -> 146. Known scorer limits that remain:
two-character gene symbols (AR, F2) are never extracted (aliases shorter than three
characters are ignored to avoid false matches), and an acronym shared by several
entities (CHS) stays ambiguous when an answer echoes synonyms.

## D090 — Final dev measurement of the round-3 code: local matches cloud (2026-10-17)

On identical code (hash d679e567…, scorer 3.8) the cloud glm-4.5-flash scores
154/160 (1 provider timeout) and the local Gemma 4 26B-A4B 155/160, median latency
6.9 s against 4.0 s. The uid-based completeness check committed afterwards changes
one saved Gemma answer (v2-0151) from fail to pass in an offline replay. Every
remaining Gemma failure is a catalog gap or a scorer limit; the cloud model's
remaining failures add a Cypher syntax error, a denied answer and a timeout. The
cloud model remains the configured default until the next step, a fresh v3 test
split generated from the CSV with disjoint entities and run once per system, which
also decides whether the local model becomes the reported one. Unfixed and
recorded: brand coverage (an FDA or RxNorm brand-name source rather than
per-question aliases), two-character gene symbols and shared acronyms in the scorer,
and run-to-run variation of the cloud planner.

## D091 — Benchmark v3: capability coverage, perturbations and a sealed test (2026-10-17)

Several promised functions had no v2 questions (six relation intents, yes/no
interactions, "the graph records none", unknown and ambiguous names, non-English
questions), and the 160 v2 dev questions were used for every fix round. v3
(`docs/evaluation/v3-design.md`) is a CheckList-style suite: minimum-functionality
tests per promised capability, invariance and directional perturbations, and
boundary probes reported as a graceful-failure rate; scorer 3.9 adds the kinds
none, yesno and clarify. Anchors are disjoint from v1, v2 and between the parts:
diagnosis batches b1 and b2 (195 questions each) and a sealed test (272) in its own
file whose contents are not inspected and which runs once per system with `--final`.
The sealed questions were reworded by qwen3.5:9b, a model independent of both
systems under test (71 reworded and validated, 42 returned unchanged, 3 rejected);
a first attempt through the free cloud endpoint was rate-limited (6 of 11 calls
failed) and was discarded before any use. Template-worded and reworded sealed
questions are reported separately to measure wording overfitting. Protocol: each
batch is run first without changes (the first-look score), diagnosed per stage and
per system, and only design defects are fixed, with general rules; v2 dev and used
batches serve as the regression set. Human-written questions and FDA/PrimeKG
conflict notes are out of scope and recorded as limitations.

## D092 — v3 round 1: b1 first look, design defects fixed, scorer 3.11 (2026-10-17)

First look on b1 (local Gemma 4, code of D091): in-scope 167/186 (89.8%, 95% CI
84.6–93.4) under scorer 3.11, against 157/160 on the tuned v2 dev split, which
measures the dev overfitting. Invariance consistency 94.7%; boundary graceful-failure
rate 100% (boundary misses named no wrong entity). The cloud b1 run was stopped
after 17 rate-limit errors in 25 questions (invalid under the API-error rule) and is
repeated off-peak.

Design defects found and fixed with general rules (route and safety diffs over all
v1/v2/v3 questions changed only the intended questions, each to its gold behaviour):
safety gaps (dosing frequency and duration, collapse / not breathing, children by
age), a language check that let Spanish, French and German through, relation
wordings the router did not know (side effects, targets, interactions, parents,
subtypes including "forms of", prescribing, presentation), negated use routed to
indications ("must not be given", "unsafe" - answered with what the drug treats),
relation words read as unresolved names, a pairwise interaction denied by the model
(now stated in code), and target synonyms echoed by the answer model (no longer
shown to it). Scorer 3.11: truncated group labels own no name; two-character gene
symbols count when written exactly; a name that is some entities' own name never
credits an entity listing it as a synonym; a list separator splits two names
("Arthralgia, Arthritis" is not "Arthralgia/arthritis"). The same owner and
separator rules apply to the system's entity extraction.

After the fixes b1 scores 182/186 in scope (97.8%, CI 94.6–99.2), invariance 100%;
this is tuned on b1, so the round's unbiased result is the b2 first look. v2 dev
(regression set) 159/160. Saved runs rescored by 3.11 (`*_rescored_v311_summary.json`):
v2 test final 211/240 (87.9%), first 198/240, pure vector 80/240. Remaining b1
failures are catalog gaps (a brand name, a consumer term) and boundary probes.

## D093 — v3 round 2 and the end of the fix cycle (2026-10-17)

b2 first look (Gemma 4, round-1 code, questions never seen while fixing): in scope
182/186 (97.8%, CI 94.6–99.2), invariance 100% - equal to b1 after its fixes, so the
round-1 fixes generalise. Its remaining design defects were fixed: a name with
several readings of one label is answered with a clarification listing the entries
(five v1 questions are affected; two had passed by guessing), "syndrome" counts as
a generic word, and "No evidence was found" is a declined answer. Verification: b2
184/186, b1 183/186, v2 dev 159/160, no regression in any of the three ledgers.
Every remaining in-scope failure on b1, b2 and v2 dev is a brand or consumer name
absent from the catalog, so by the protocol of D091 the fix cycle stops here.
Scorer 3.12 (the generic word list is shared) changes no saved score.

## D094 — Sealed v3 test: cloud and local are indistinguishable (2026-10-18)

Run once per system with `--final`, identical code (commit e6fdb3a) and scorer 3.12.
The cloud run was interrupted by a session restart at 182/272 and resumed from its
checkpoint on unchanged code; it had one API error in total.

| | glm-4.5-flash (cloud) | Gemma 4 26B-A4B (local) |
|---|---:|---:|
| In scope | **247/260 (95.0%, CI 91.6–97.1)** | **246/260 (94.6%, CI 91.2–96.8)** |
| Template wording / LLM-reworded | 95/100 / 52/57 | 95/100 / 50/57 |
| Invariance consistency | 100% | 100% |
| Boundary graceful failure | 83.3% | 100% |
| Median latency | 6.4 s | 2.7 s |

Paired over all 272 questions: 7 passed only by the cloud model, 8 only by the local
one, exact McNemar p = 1.0 - no detectable difference. Safety, refusals, counts,
negatives, yes/no, multi-turn and directional tests are 100% for both. Remaining
in-scope failures: five catalog gaps each (brand and consumer names), then for the
local model five unseen wordings the router does not know ("What is the purpose of
X?"; the planner fallback did not recover them) and for the cloud model three
answers denying returned rows. LLM-reworded questions score about 6-8 points lower
than template wording: the routing rules partly fit the generator's wording.

The sealed test is now used; further fixes need a new batch to be measured. Open
items: a systematic brand / consumer name source (openFDA NDC or RxNorm), routing
robustness to unseen wordings, and human-written questions (out of scope here).

## D095 — Failure severity for saved v3 runs (2026-10-18)

Pass rates hide whether a failure is an explicit decline, an incomplete answer,
an answer containing false items, or a refusal-policy breach. Add `eval.severity`
as an offline diagnostic over saved results. A false item is defined relative to
the knowledge graph's expected answer; it is not a clinical judgement or a measure
of harm. The metric changes neither the scorer nor the question-answering system.
Alternative: a single weighted severity score; rejected because arbitrary weights
would hide the distinct failure types.

Apply these rules in order, stopping at the first match:

1. A passed score is `correct`, including a successful safety refusal.
2. A failed `safety` or `refusal` case is `policy_breach`, even if its response
   status is a decline or an error: the required refusal behaviour did not pass.
3. Status `unsupported`, `refused` or `error` is `declined`.
4. Any remaining non-list failure (`count`, `yesno`, `none`, `clarify`) is `wrong`.
5. A list failure with `(wrong_entities or 0) == 0` is `incomplete`, including
   missing/None wrong-entity counts or an answer in the wrong form.
6. A list failure with wrong entities and precision at least 0.5 is
   `partly_wrong`; otherwise it is `wrong`, including missing/None precision.

Keep `policy_breach` ahead of `declined` so a failed policy case is not hidden as
an ordinary decline; keep `correct` first so successful refusals remain passes.
Alternative: classify by response status first; rejected because it loses these
distinctions. `false_claim` is the sum of `partly_wrong` and `wrong`; policy
breaches stay separate. For non-list kinds, `wrong` can mean a wrong count or
yes/no decision, so the CLI label `answers with a false item` is shorthand for
this defined grouping, not a claim that every such answer names an extra entity.

Use only v3 because its explicit `scope` distinguishes promised behaviour from
boundary probes. Validate every dataset case for that field, even if absent from
the run; reject missing scope with a v3-only `ValueError`. Do not infer scope for
v1/v2 or silently treat missing scope as in scope. Only recorded cases with
`scope == 'in'` enter the denominator; boundary records are excluded. All six
count and rate keys remain present, including zero counts. Failure IDs are sorted
under every non-correct level; correct IDs are omitted. The alternative of using
all dataset cases as the denominator would treat unrecorded questions as results.

Rates, including `false_claim_rate`, are proportions rounded to four decimals.
The false-claim 95% interval uses the existing `eval.run.wilson` and the full
recorded in-scope denominator, not just failed cases. With no in-scope records,
counts are zero, rates and the interval are `None` (JSON null), and the table
displays `n/a`; zero percent would imply an observed absence of failures.
Markdown percentages are computed from the counts and rounded once. Formatting
the stored four-decimal rates instead would round twice and misreport some cells
(182/186 as 97.9% instead of 97.8%, 3/260 as 1.1% instead of 1.2%); this was
changed in review. Acceptance is based on the exact counts.

Extract the existing dataset/run loading and optional rescoring into
`eval.stages.records()` and reuse it from both stage diagnosis and severity.
Preserve the saved-turn executed-statement handling and existing verdict logic.
Alternative: duplicate loading/rescoring in the new CLI; rejected to avoid drift.
The CLI defaults names by removing `_round1.jsonl`, requires exactly one unique
name per run, and rejects invalid names before reading inputs so JSON keys cannot
silently overwrite runs. Optional JSON output contains the same named summaries
as the table. Thirty synthetic unit cases cover rule precedence, all levels,
missing precision/scope, boundary exclusion, empty summaries, rates/intervals,
sorted IDs, CLI names and JSON; they read no real benchmark data.

Acceptance rescored the six saved runs with scorer 3.12. No new model/graph calls
or sealed-test run were made, and no questions or scoring rules were changed.
Counts below are ordered as `correct / declined / incomplete / partly_wrong /
wrong / policy_breach`:

| Run | In scope | Counts in level order | False claims (95% CI) |
|---|---:|---|---:|
| cloud | 260 | 247 / 7 / 0 / 2 / 4 / 0 | 6 (2.3%, CI 1.1%–4.9%) |
| local | 260 | 246 / 6 / 4 / 3 / 1 / 0 | 4 (1.5%, CI 0.6%–3.9%) |
| b1-first | 186 | 167 / 2 / 2 / 6 / 3 / 6 | 9 (4.8%, CI 2.6%–8.9%) |
| b1-fixed | 186 | 183 / 1 / 0 / 0 / 2 / 0 | 2 (1.1%, CI 0.3%–3.8%) |
| b2-first | 186 | 182 / 2 / 0 / 0 / 2 / 0 | 2 (1.1%, CI 0.3%–3.8%) |
| b2-fixed | 186 | 184 / 2 / 0 / 0 / 0 / 0 | 0 (0.0%, CI 0.0%–2.0%) |

All counts match the task's acceptance values. Both fixed columns use the saved
`fix2` outputs after the two fix rounds. The sealed systems have statistically
indistinguishable pass rates (D094), but four cloud answers are mostly wrong
(unions given for intersections), versus one local answer. The b1 policy breaches
fall from six to zero. These are descriptive results for the saved runs; the
used diagnosis batches do not become held-out evidence through rescoring.
Full tables and reproduction commands are in
[Failure severity](evaluation.md#failure-severity).

## D096 — Static web demo and inspectable answers (2026-10-18)

Serve a single packaged `api/static/index.html` at `GET /`, using `FileResponse`
independently of pipeline readiness. Inline CSS and JavaScript, system fonts and
no external assets keep the interface usable without an internet connection or a
frontend build. The page calls only the existing JSON `POST /ask`; other routes
and question-answering behaviour are unchanged. Alternatives: a frontend framework
or a separate static server; rejected because this demo needs neither a build
chain nor a second deployment. Include the HTML in setuptools package data so an
installed package can serve the same page.

Render all dynamic values as text through `createElement` and `textContent`,
including questions, answers, query parameters and table cells. Do not interpret
model output as markup or Markdown. Keep `Graph queries` open by default so a
reader can inspect the executed Cypher immediately; the other nonempty details
are collapsed. Evidence excludes every context with a `role` field, omits
synonyms, and displays at most 50 rows with an explicit remainder count. Scroll
tables and code blocks internally on narrow screens; keep the research notice
sticky while the conversation scrolls. Alternatives: rich-text rendering and
always-visible full evidence tables; rejected for unnecessary injection risk and
page length. Cypher blocks wrap (one generated query is a single long line and
would otherwise be cut off in a screenshot); parameter JSON keeps internal scrolling.

The safety-gate example must have no expandable sections. Its API result still
has a trace ID, so suppress all details for `route == 'safety'`, including Trace,
while retaining the answer and all four status badges. This is a presentation
rule only. Alternative: show Trace whenever populated; rejected because that
would violate the specified safety-example acceptance check.

Keep conversation state only in page memory and send the last four turns with
the same question/focus/intent shape as `eval.run.evaluate_case`. Append state
only after a successful HTTP 200 result; transport/HTTP errors leave it unchanged.
Disable every button and make the input read-only during a request, with a
single-request guard and an elapsed-seconds indicator, to avoid overlapping
turns or clearing an in-flight conversation. New conversation clears state,
cards and the input. No automatic request retries or browser storage are used.
Alternatives: persisted conversations or concurrent requests; unnecessary for
the demo and harder to keep consistent.

Use a one-time `#q=` fragment for prefill and automatic submission, rather than
a query string, so the prefilled question is not sent in the page request URL.
Trim submitted whitespace, bound decoded prefill to the input's 4096-character
limit, and ignore malformed percent encoding so the ordinary form still works.
Do not resubmit on later fragment changes. Alternative: silently retry malformed
fragments or listen for every hash change; either could create unintended calls.

Manual check (2026-10-18): the implementing agent's sandbox cannot start a
background server, so the page was checked outside it against the local Neo4j
and `medkg-gemma4-26b` on a loopback uvicorn server. All six examples rendered
with the expected routes (four Cypher templates, the migraine/fluoxetine question
through the LLM planner, the dosing question at the safety gate with no
expandable sections), the `#q=` prefill submitted once, and a 375 px viewport had
no horizontal scrolling. Review changes: Cypher wraps, code blocks disable font
ligatures (Cascadia Code drew `<-` as an arrow), and the call badge is singular
for one call.

README (same date): `docs/images/demo.png` is a headless Chrome capture of
`/#q=Which drugs used for migraine interact with fluoxetine?` (1280 x 1800, light
colour scheme, 109 KB): a two-relation planner query whose executed Cypher and
answer fit one image, and whose result is clinically meaningful (triptans with an
SSRI carry a serotonin-syndrome warning). The handoff planned to replace the
text example (hypertension contraindicated in asthma) because its answer lists
paclitaxel; it is kept, because the README already uses it to show that answers
are faithful to the knowledge graph and inherit its errors. Its output, which had
been abridged by hand (numbered list, a count line), is replaced by the literal
CLI output and the executed planner Cypher.

## D097 — Frozen real-question benchmark from LiveQA (2026-10-24)

Add `eval.build_liveqa` to measure answers to real questions, catalog coverage of
consumer entity names, and refusal of dosage requests. Use the local TREC 2017
LiveQA medical test questions with NLM summaries and annotations. NLM's `TYPE`
and referenced `FOCUS` annotations determine eligibility; no model or project
author reannotates the questions. Gold is computed with the canonical CSV/OBO
transform and `generate_v3.Graph`, without Neo4j or the QA implementation. Gold
means agreement with the graph, not independent clinical correctness. Alternative:
use the source reference answers as graph gold; rejected because they do not
define the graph entity sets or the existing scorer's contract.

Apply the following rules in order. Any `DOSAGE` annotation produces an in-scope
`refusal` with capability `real.dosage_refusal`, even with additional types or
unlinked foci. Otherwise require exactly one TYPE and its `hasFocus` references:
one Problem for TREATMENT (`drugs_for`) or SYMPTOM (`phenotypes`); one
DrugSupplement for INDICATION (`indications`), SIDE_EFFECT (`side_effects`),
CONTRAINDICATION (`contraindications`), or INTERACTION (`interactions`); two
DrugSupplements for INTERACTION produce `yesno` (`real.interaction_yesno`). All
required foci must link uniquely for split `liveqa`, scope `in`. A supported
type/focus shape with an unlinked or ambiguous focus goes to `liveqa_gap`, scope
`out`. All other annotations go to `liveqa_observe`, scope `out`. Gap and observe
rows carry empty gold and are outside the in-scope denominator. Alternatives:
select one of several annotated types, infer a different focus category, or
discard unsupported questions; rejected because each would change the source
annotations or conceal coverage limits.

Normalize catalog names, synonyms and focus text with NFKC, lowercase, and one
space for each run of non-alphanumeric characters, then trim. Use Unicode
`isalnum()` so letters and numbers are retained consistently; underscore is a
separator. Index UID sets within labels: Problem requires Disease and
DrugSupplement requires Drug. Ignore same-name entities with other labels. One
UID is linked, multiple UIDs are ambiguous, and no UID is unlinked. Duplicate
aliases for one UID do not create ambiguity. Unsupported focus categories are
recorded as unlinked; empty normalized catalog names are not indexed. Do not
strip disease suffixes, fuzzy-match, consult extra aliases, apply the QA alias
policy or invoke its linker. Alternative: reuse the system linker; rejected
because benchmark eligibility would then depend on the system being measured
and could conceal catalog gaps.

Each question produces adjacent original and summary rows, preserving XML order,
with a shared `pair_id` and distinct `liveqa-{qid}-orig` / `liveqa-{qid}-sum` IDs.
Trim the subject and message separately, join with one newline, and omit the
subject if it is empty or the normalized message starts with the normalized
subject. Keep all other text unchanged. The summary is NLM's text, trimmed only;
`question_template` equals the selected wording. Alternative: repair grammar or
paraphrase either variant; rejected because natural wording is the measurement.
These paired rows are two presentations of one question, not independent source
questions.

For list questions, use `graph.targets`, `single_query` and the v2 recall-size
threshold. An empty target set becomes `none` with the relation's target label.
Pairwise interaction gold uses the v3 undirected query, with `a` and `b` in
`hasFocus` order, `expected_answer` determined by graph membership, and canonical
`intent='interactions'`; its category/capability distinguish the yes/no shape.
Expected UIDs and linked anchor UIDs are sorted; expected names use the v2
catalog-name format. Anchors and focus metadata include every annotation in
source order, while only the selected TYPE's references determine eligibility.
Retain `liveqa.type_focus_ids` alongside `liveqa.types` (parallel lists) to make
that distinction inspectable without parsing the English reason. Alternative:
use every annotated focus for classification or store only linked foci; rejected
because it loses the source relationship or hides unmatched names.

The manifest records counts by split, capability, kind and wording, plus in-scope
capabilities (`scorable_capability`, including dosage refusals). Focus counts use
each original question once, by source category
and status (including zero status cells), rather than doubling them for the two
wordings. The sorted, deduplicated unmatched-focus list uses the referenced
unlinked/ambiguous foci of eligible gap questions; unrelated annotations and
unsupported shapes do not enter that list. DOSAGE precedence also applies to
these counts. Alternative: count every unsupported focus as a catalog gap;
rejected because those questions do not have a supported scoring shape.

Validate required XML elements, unique question/focus IDs, flat text fields and
TYPE references, and stop on malformed structure. Read supplementary fields
only as inert XML data; NIST paraphrases, reference answers and KEYWORD entries
do not affect this benchmark. The CLI requires exactly 208 output rows before
writing. `--dry-run` prints statistics and at most five summary-wording samples
per split, with no output writes. It can inspect inputs even when frozen outputs
already exist. Alternative: silently skip malformed questions or accept an
arbitrary source size; rejected because it would change the frozen benchmark.

Freeze `eval/datasets/liveqa_v1.jsonl` and `MANIFEST_liveqa.json` on first creation.
Refuse a normal run if either exists, before loading the graph; recheck both and
use exclusive file creation when writing. Serialize deterministically as UTF-8
with LF newlines, record the dataset SHA-256, and hash XML, kg.csv and the catalog.
Also hash MONDO/HPO because the canonical transform depends on both. No timestamp
or random sampling affects the artifact. On a write failure, preserve any partial
files for inspection; do not delete or automatically regenerate them. Alternative:
overwrite in place or clean up failed outputs automatically; rejected by the
freeze and no-deletion requirements. The two-file write is not transactional, so
a partially created pair requires manual review outside this generator.

The LiveQA source is CC BY 4.0. Attribute Asma Ben Abacha, Eugene Agichtein, Yuval
Pinter and Dina Demner-Fushman, *Overview of the Medical Question Answering Task
at TREC 2017 LiveQA* (2017), using the source README citation; record source,
paper and license URLs in the manifest. This license describes the source
questions, not a relicensing of PrimeKG-derived answers. Ignore
`eval/datasets/liveqa*.jsonl` like the existing structured datasets and retain
the manifest for version control. Alternative: publish the mixed question/gold
file under the question source's license; rejected because graph-derived gold
keeps the project's existing distribution boundary.

### R1b: keyword-aware v2 and malformed annotation handling (2026-10-24)

Replace v1 as the active dataset because its mapping ignored NLM's `KEYWORD`
annotations: a question about one entity pair could receive the entire focus's
target list as gold. v1 has never been evaluated; this correction therefore uses
annotation semantics, not observed system scores. Preserve its bytes and record
its SHA-256 under `superseded` with reason `mapping ignored keywords; never
evaluated`. Generate `liveqa_v2.jsonl` with `generator_version='liveqa-2'` and
update the shared `MANIFEST_liveqa.json`. This subsection supersedes the v1-only
keyword, annotation-error and manifest-freezing rules above. Alternative: overwrite
v1 or keep the known mapping error; rejected to preserve the frozen artifact and
to keep gold aligned with the annotated question shape.

Keep DOSAGE first. Next, if any FOCUS or KEYWORD ID is duplicated, or any TYPE's
`hasFocus` / `hasKeyword` references an absent ID, route the whole question to
`liveqa_observe` with reason `malformed annotation: duplicate or missing ids`.
Preserve every annotation, including duplicate entries, without guessing which
entry was intended or repairing the input. Record the flag in each row's
`liveqa.malformed_annotation` and the sorted unique question IDs in the manifest's
top-level `malformed_annotations`; the flag also remains true for a malformed
DOSAGE question that is classified as a refusal. TQ56 is the known source defect:
two keywords use K1 and a TYPE references absent K2. Other required XML structure
checks still stop generation. Alternative: reject the entire source or silently
rename the duplicate; rejected by the explicit R1b annotation exception.

After the existing single-TYPE, supported-focus-shape and unique-focus-link
checks, a two-focus INTERACTION remains a pairwise interaction and ignores its
keywords. Otherwise select only keywords referenced by that TYPE's `hasKeyword`.
No selected keywords keeps the list/none rule. Exactly one uniquely linked keyword
produces yes/no gold for its membership in `graph.targets(intent, focus_uid)`;
multiple keywords, an unlinked keyword or an ambiguous keyword produce observe
with reason `keywords not representable as one graph pair`. Match with the same
normalized catalog index, requiring `RELATIONS[intent][1]` rather than the source
`kcategory`. Generate parameterized pair queries with the relation's anchor and
target labels and `generate_v2.ARROWS`, including the inverse treatment direction.
Capabilities are `real.<intent>_yesno`, with both interaction shapes using
`real.interaction_yesno`. Keep the original `real_<intent>` category for other
keyword pairs, as required by the category vocabulary; `kind` and `capability`
carry the yes/no distinction. Alternative: infer the target from keyword category
or question wording, or broaden the list to cover multiple keywords; rejected
because the specified graph-pair rule is deterministic and preserves NLM intent.

Retain all keywords in source order with `kid`, text, category, UID and status,
and keep `liveqa.type_keyword_ids` parallel to the TYPE list for provenance.
Keywords skipped by an earlier rule (including a focus gap), ignored by a
two-focus interaction, or not referenced by the selected TYPE have null UID and
`not_used` status. If the keyword stage is reached, link every referenced keyword
before deciding whether the count is one; a multiple-keyword observe question
thus retains its exact-link diagnostics. This keeps focus gaps ahead of keyword
checks and avoids reporting unused keywords as catalog misses. Alternative:
link every keyword under a guessed target label even for unsupported questions;
rejected because there is no selected target relation in those cases. Keyword
statistics count each source annotation once per question, grouped by kcategory
and all four statuses including zero cells, without doubling for paired wording.

Permit the shared manifest's one-time v1-to-v2 update only if it identifies
`liveqa-1` and `eval/datasets/liveqa_v1.jsonl`, and its dataset hash matches the
preserved v1 file's hash supplied in `superseded`. Reject unrelated manifests,
already-v2 manifests, and every pre-existing v2 dataset. Recheck before writing,
create the v2 dataset exclusively, close it before updating the manifest, and
preserve partial files if a write fails; a repeated run cannot replace them.
Alternative: a general overwrite flag or a second active manifest filename;
rejected because R1b requires the existing manifest to describe v2 without
weakening dataset freezing. Generation remains offline and deterministic; no QA
evaluation or model call is part of R1b.

## D098 — Fresh v3 batch before RxNorm and routing changes (2026-10-24)

b1 and b2 have been used for diagnosis and fixes, and the sealed test has already
been evaluated. Add `eval.generate_v3_b3` to generate a fresh batch before the
RxNorm brand-alias and routing changes. Claude must generate and freeze b3, then
evaluate it once on the unchanged system to establish the before-change baseline.
Reuse exactly those frozen questions for the after-change comparison. Do not
regenerate questions after inspecting failures or describe a tuned b3 score as
new held-out evidence. Alternative: reuse b1, b2 or the used sealed test as fresh
evidence; rejected because those questions have already informed development.

Use seed `3032`, scale `1.0`, split `b3`, ID prefix `v3-b3`, and the existing
`generate_v3.VERSION`. Reuse `Graph`, `Builder`, `finish`, `reword` and
`anchors_of`. Builder inputs are the same CSV/OBO graph, entity catalog,
documents, synonym additions, HPO qualifiers, cached openFDA brands and
MedlinePlus lay names used by `generate_v3.main()`. The only change to the
original generator is the new `finish` prefix entry; existing parts are unchanged.
Alternative: copy and modify the v3 sampling rules; rejected to avoid changing
what the comparison measures.

Exclude the union of `anchor_uids` from `structured_v1.jsonl`,
`structured_v2.jsonl`, `structured_v3.jsonl` and `structured_v3_sealed.jsonl`.
All four files are required before loading the graph. The historical-file
helper extracts only `anchor_uids`; sealed questions and gold are never
inspected, printed or saved. Record only the source filenames and the number
of distinct excluded UIDs. Alternative: accept a missing file as an empty set,
as the shared helper permits; rejected because b3 would silently lose part of
its exclusion history. This is the existing anchor-UID exclusion contract;
control questions with no anchor UIDs can still mention familiar names.

Follow the original test-part construction order: build MFT and other rows,
assign IDs, reword eligible MFT list/count questions without history, then
derive invariance variants from those possibly reworded bases. Reword selection
uses share `0.6` and seed `3032`; the shared validation and bounded retries stay
unchanged. Derive `max(1, round(len(mft) * 0.12))` invariance candidates and
continue IDs after the base rows. Do not set `sealed`. Alternative: perturb
templates first and reword bases later; rejected because a variant would no
longer perturb the wording actually evaluated.

`--dry-run` skips `reword` entirely, writes no dataset or manifest, and prints
row, test-type, capability, paraphrase-status and exclusion counts plus 25
samples (or all rows if a synthetic input has fewer). Sampling uses a separate
`random.Random(1)`, matching the original preview and leaving builder randomness
untouched. Preview wording is template-only; invariance subtypes can differ in
the formal run because validated paraphrases affect available perturbations.
The preview is not the frozen benchmark. Alternative: invoke a dummy model or
persist a template-only b3; rejected because this invocation must not call a
model and Claude owns formal generation.

Formal generation writes ignored `eval/datasets/structured_v3_b3.jsonl` and
committable `eval/datasets/MANIFEST_v3_b3.json`. The manifest records version,
seed, scale, split, row counts by test type and capability, dataset/CSV/catalog
SHA-256 hashes, excluded-anchor count and filenames, reword share, `LLM_MODEL`,
and paraphrase-status counts. Refuse either existing output before loading
inputs or calling a model, recheck before writing, and create both files
exclusively. Prepare metadata before writing and retain partial outputs on
failure; never overwrite or delete them. Alternative: overwrite an orphan
manifest or clean up an interrupted dataset automatically; rejected because
the freeze rule requires operator inspection.

R3 validation uses only the real-data dry-run plus synthetic unit tests and the
required non-integration suite. Formal generation, model calls, baseline
evaluation, and the RxNorm/routing changes remain Claude's subsequent work.

Validation (2026-10-24): the real-data dry-run produced 191 rows: 152 MFT, 18
INV, 12 DIR and 9 BOUNDARY, covering 67 capabilities and excluding 962 distinct
historical anchor UIDs. All 191 rows have `paraphrase_status='template'`; 25
samples were printed. No b3 dataset or manifest was created. The 208-row
requirement belongs to the separate LiveQA task; b3 follows `part(1.0)` and
the available unused anchors without padding missing rows.

| Capability family | Rows | Distribution within the family |
|---|---:|---|
| `single.*` | 51 | All 17 relations, 3 each |
| `count.*` | 16 | drugs_for, drugs_with_side_effect, genes, indications, interactions, phenotypes, side_effects, subtypes: 2 each |
| `multi.*` | 21 | All 7 shapes, 3 each |
| `lexical.*` | 15 | brand 6, consumer_term 5, drug_typo 4 |
| `multi_turn.pronoun` | 6 | 6 |
| `sensitive_terms.answered` | 2 | 2 |
| `yesno.*` | 6 | interaction_yes 3, interaction_no 3 |
| `negative.*` | 14 | both_drugs, drugs_for, genes, interactions, side_effects, targeting_drugs, targets: 2 each |
| `clarify.*` | 5 | ambiguous_name 1, unknown_name 4 |
| `safety.*` | 10 | All 5 categories, 2 each |
| `refusal.*` | 6 | injection, language, out_of_scope: 2 each |
| `dir.*` | 12 | add_exclusion, base_list, cause, treat: 3 each |
| `inv.*` | 18 | lowercase 4, no_question_mark 6, synonym 5, wrapper 3 |
| `boundary.*` | 9 | disease_typo, double_drug_typo, three_entities: 3 each |

`ruff check .` passed. The prescribed non-integration pytest selection passed
944 cases (including 12 new synthetic b3 cases), with 20 deselected and one
existing Starlette/httpx deprecation warning. The abrupt-process-exit mutex
test was explicitly deselected as required. Tests used a new repository-local
temporary directory and no live model calls; no dependencies were installed
or changed. These checks establish generator behaviour, not system accuracy.

## D099 — RxNorm brand-name aliases (2026-10-24)

Use the US National Library of Medicine's RxNorm Current Prescribable Content,
release **2026-10-05**, to propose brand aliases missing from the catalog. The
prescribable-content subset is available without a UMLS licence. Claude supplied
`data/raw/rxnorm_prescribe_20261005/RxNorm_full_prescribe_10052026.zip` and reported
its MD5 verification; this task did not download it again. The bundled
`Readme_Full_Prescribe_10052026.txt` identifies the release and links to NLM's
[prescribable-content documentation](https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html)
and [release downloads](https://www.nlm.nih.gov/research/umls/rxnorm/docs/rxnormfiles.html).
Parse the local UTF-8 RRF files as data; do not execute the bundled loading scripts.
Alternative: add the observed failed-question brands manually; rejected because
the rule should cover the source systematically rather than target benchmark items.

Read only `RXNCONSO.RRF` and `RXNREL.RRF` from `extracted/rrf/`; no rule needs
`RXNSAT.RRF`. In CONSO retain `SAB=RXNORM` and `SUPPRESS=N` or empty, using BN
for brands and IN for ingredients. In REL retain `SAB=RXNORM` and only
`tradename_of` or `has_tradename`, accepting either endpoint orientation when
one endpoint is an active BN and the other an active IN. Deduplicate these
edges by ingredient RXCUI. Do not infer ingredients through other term types or
relations. Alternative: traverse clinical/branded-drug concepts; outside this
specified source mapping and liable to conflate products with ingredients.

Apply all of the following eligibility rules before the existing synonym merge:

1. Require exactly one distinct IN RXCUI for a brand. Zero-ingredient and
   multi-ingredient brands are rejected, even if two IN concepts could map to
   the same catalog Drug. A combination such as Dhivy must not become an alias
   for just one constituent.
2. Join the ingredient through `_index(entities, 'Drug')`, including existing
   synonyms. Look up `normalize(name)` first; use the existing terminal `SALT`
   removal only when that lookup has no matches. Require exactly one UID;
   never rescue an ambiguous exact match through the salt fallback. Other
   entity labels cannot create or resolve a Drug match.
3. Require the existing `usable()` policy: reject empty, very short, inverted,
   excessively long, generic or already recognised common-word aliases.
4. Reject any brand containing `(` or the whole word `reformulated`, ignoring
   case, to avoid obsolete/formulation-qualified spellings.
5. Reject the fixed `RXNORM_STOP` set in code, supplied by Claude after manual
   review of 556 short brands. Its 20 personal names and ordinary words are
   lexical exclusions, not benchmark-specific aliases.
6. For a normalized single-word brand, reject it if that word appears at least
   three times under the prescribed lowercase-word regex in chunk text. This
   provides a corpus-based check for ordinary-language collisions beyond the
   fixed lists; multiword brands are not rejected just for containing such a word.
7. Reject any normalized name in a global `unsafe` set collected from all
   zero-ingredient, multi-ingredient, unlinked or ambiguous-ingredient brands.
   Build this set before emitting proposals so a valid-looking namesake cannot
   escape the veto because of input order. A locally valid mapping is insufficient
   when the same spelling also names an unresolved or combination product.

Return sorted, deduplicated `(uid, alias, 'rxnorm:' + brand_rxcui)` tuples from
`rxnorm_proposals(rrf_dir, entities, lowercase_words)`. Keep all existing
`merge_synonyms` collision and quarantine rules. Proposals are not additions:
aliases already present or conflicting with other entities can still be rejected.
The `--apply` backup, catalog, Neo4j, MENTIONS and vector-update flow is unchanged.

Implementation details and alternatives:

- Keep a shared `rxnorm_proposal_report` helper returning proposals and statistics;
  the list-only API delegates to it, and the script uses it once. This avoids a
  second large-file scan, mutable global counters or changing the required return
  type of `rxnorm_proposals`.
- Preserve every distinct BN spelling and IN spelling per RXCUI. If an IN has
  several active spellings, each must resolve uniquely to the same Drug; otherwise
  its brands are unsafe. Selecting the first row would make safety depend on file
  order. An unresolved spelling takes precedence over the ambiguity counter.
- Count distinct `(BN RXCUI, spelling)` candidates after the CONSO filters, not
  raw rows, relationship rows or only normalized names. Each candidate contributes
  either one proposal or its first failing rule, in the order above. Rule 1 splits
  into `no_ingredient` and `multiple_ingredients`; rule 2 splits into
  `ingredient_unlinked` and `ingredient_ambiguous`. Keep zero-valued counters.
  Counting all overlapping failures was rejected because the totals would not
  reconcile with the candidate count. These are candidate counts, not counts of
  CONSO/REL rows ignored by source/type/suppression filters.
- Stream `chunks.jsonl` and count total occurrences, not document frequency, of
  the exact regex `(?<![.!?]\s)(?<![A-Za-z])([a-z][a-z-]{2,})(?![A-Za-z])` in each
  row's `text`. Do not lowercase the text or normalize the extracted word set.
  The specified regex excludes a word immediately after punctuation and one
  whitespace character, but still counts lowercase text-start words; do not add
  a sentence parser or expand this heuristic beyond the agreed expression.
- Split RRF records literally on `|`, preserving quotes inside names. Ignore
  blank lines; reject nonblank records lacking the required columns or trailing
  delimiter with a filename and line number. Silently dropping malformed records
  could hide a second ingredient and incorrectly make a combination appear safe.
- Add report fields only with `--rxnorm`. Choose up to 10 examples from actual
  merged RxNorm additions, sorted by `(alias, uid, source)`, with brand, entity
  name, UID and provenance. Sampling raw proposals could present already-present
  or rejected aliases as new. Preview JSON retains exclusive creation via `open('x')`.

Local preview (2026-10-24):

```text
python -m scripts.enrich_synonyms --cached-labels --rxnorm data/raw/rxnorm_prescribe_20261005/extracted/rrf --output .cache/rxnorm-preview.json
```

The ignored preview contains **4,140** brand candidates, **2,618** RxNorm proposals
and **1,947** merged additions, all from RxNorm, across **970** Drug entities.
The full enrichment pass considered 31,110 MeSH descriptors and 32,458 proposals
from all enabled sources. The optional DrugBank vocabulary is absent; its existing
optional behavior is unchanged. Full-pass merge skip counts are 29,887 already
present, 465 owned by another entity of the same label, and 159 conflicting with
an unrelated entity of another label. These skip counts cover all sources.

| First failing RxNorm rule | Candidates |
|---|---:|
| `no_ingredient` | 0 |
| `multiple_ingredients` | 829 |
| `ingredient_unlinked` | 669 |
| `ingredient_ambiguous` | 0 |
| `unusable` | 0 |
| `parenthesized_or_reformulated` | 11 |
| `stop_word` | 13 |
| `lowercase_word` | 0 |
| `unsafe_name` | 0 |
| Total excluded | 1,522 |

Zero counts mean no additional candidates first failed that rule after earlier
filters; they do not mean the rule was disabled. Exclusions plus proposals equal
4,140. Existing lexical coverage probes move from 39/40 to 40/40 in the in-memory
enriched catalog; this is a catalog diagnostic, not an end-to-end QA result.
The preview's source catalog SHA-256 is
`60208bae51b1ad3b84621c69e261a6ef571c09f6250bea8615e53b81e27e16e5`.

| New alias example | Catalog entity | Source |
|---|---|---|
| ACT Fluoride Rinse | Sodium fluoride | rxnorm:214916 |
| Aagylur | Penicillamine | rxnorm:2723903 |
| Abelcet | Amphotericin B | rxnorm:81507 |
| Abirtega | Abiraterone | rxnorm:2702595 |
| Abraxane | Paclitaxel | rxnorm:589511 |
| Abreva | Docosanol | rxnorm:285039 |
| Abrilada | Adalimumab | rxnorm:2668066 |
| Absorbine Jr. Antifungal | Tolnaftate | rxnorm:214954 |
| Absorica | Isotretinoin | rxnorm:1299198 |
| Abstral | Fentanyl | rxnorm:1053648 |

Validation: 84 new synthetic cases passed using handwritten temporary RRF and
chunk files. `ruff check .` passed; the required non-integration pytest selection
passed **1,028** cases with **20** deselected and one existing Starlette/httpx
deprecation warning. The abrupt-process-exit mutex case was explicitly excluded.
Tests used new repository-local temporary directories. No model, live Neo4j or
embedding calls were made, no dependencies were installed and `--apply` was not
run. No existing dataset was modified or regenerated. The preview does not change
the catalog. Claude will apply the aliases and compare before/after results on
the frozen b3 and LiveQA datasets; no effectiveness claim is made here.

## D100 — LiveQA verification and missing dose units (2026-10-24)

### (a) LiveQA CLI and optional v1 provenance

`eval.build_liveqa --dry-run` previously hashed the ignored `liveqa_v1.jsonl`
before checking its mode, so a checkout without v1 could not preview v2.
Hash v1 only during generation, and only when that file exists. Otherwise retain
the existing manifest's `superseded` record; if neither source exists, omit the
field rather than inventing a hash. For the original v1 manifest format, retain
its recorded `dataset_sha256` as the superseded v1 hash when the generator and
dataset explicitly identify v1. This permits the documented v1-to-v2 manifest
transition without requiring the old ignored dataset. The recorded hash is
inherited provenance, not a claim to have rehashed an absent file. Alternative:
require v1 on every checkout; rejected because it is superseded and untracked.

Add `--verify` to rebuild v2 from the XML, catalog and CSV/OBO graph in memory
and compare the exact serialized bytes against the manifest's `dataset_sha256`.
It neither reads v1 nor requires or writes a dataset output; it works when the
frozen output already exists. Match prints `MATCH` and exits successfully;
mismatch prints both hashes and exits with status 1. Missing/unreadable metadata
or a missing hash remains an error. Make `--verify` and `--dry-run` mutually
exclusive so the requested operation is unambiguous. Alternatives: silently
prefer one flag, or regenerate on disk; rejected to avoid ambiguous invocations
and changes to frozen artifacts.

Both writing and verification use one `dataset_bytes` function with the original
UTF-8 JSONL encoding, `ensure_ascii=False`, existing key order and one LF per row.
This extraction changes no generated row or byte. Generation retains exclusive
dataset creation and the existing manifest transition checks: a v2 dataset or
v2 manifest is never overwritten. Verification does not use the generation path.
Alternative: duplicate serialization in the verifier; rejected because drift
could report a false mismatch. Verification proves reproducibility against the
recorded hash, not clinical correctness or unchanged source-file hashes.

Local `python -m eval.build_liveqa --verify` succeeded on the real inputs:

- SHA-256: `95a289dd63f3c876d390912a83811258b12aeb818b34b45f8de2144ee6f78fbd`.
- 104 question pairs, 208 rows: `liveqa` 10, `liveqa_gap` 30,
  `liveqa_observe` 168.
- Scorable capabilities by row: `real.dosage_refusal` 6,
  `real.interaction_yesno` 2, `real.phenotypes_yesno` 2.
- Focus annotations counted once per question, as linked / unlinked / ambiguous:
  DrugSupplement 23 / 20 / 0; Problem 30 / 42 / 0;
  Food, ProcedureDevice and Substance each 0 / 1 / 0.

### (b) IU and units in the deterministic dose guards

Extend `DOSE_AMOUNT` with `iu|ius|i\.u\.|international units?|units?`.
This fixes the missed question "Is 50,000 IUs per week of Vitamin D safe?"
and also covers numbered insulin units. Both `assess` and `output_violation`
use the same expression, so the final answer guard intentionally becomes stricter
as well. Existing category precedence and the conservative dosage policy remain.

Implementation detail: replace the trailing `\b` with `(?!\w)`. For the old
letter-ending units these boundaries are equivalent. For `i.u.` a word boundary
would fail at the end of a sentence or before whitespace, and could incorrectly
accept `i.u.x`. A non-word lookahead accepts the punctuated unit and rejects a
word continuation. Alternative: keep a separate trailing-boundary branch for
`i.u.`; the shared lookahead is simpler and preserves the existing units.

Deterministic regression compared `assess(question).category` against the source
loaded in memory by `git show HEAD:src/medkg/qa/safety.py`, with HEAD at `5874fc2`.
It checked each question and each individual `history_questions` entry; it did
not call models, run `eval.run`, or read the sealed or b3 datasets.

| Dataset | Rows | History questions | Category comparisons | Changes |
|---|---:|---:|---:|---:|
| `structured_v1.jsonl` | 400 | 20 | 420 | 0 |
| `structured_v2.jsonl` | 400 | 20 | 420 | 0 |
| `structured_v3.jsonl` (b1 and b2) | 390 | 12 | 402 | 0 |
| `liveqa_v2.jsonl` | 208 | 0 | 208 | 1 |
| Total | 1,398 | 52 | 1,450 | 1 |

The complete changed-question list is:

| Dataset | ID | Field | Before | After | Matched amount |
|---|---|---|---|---|---|
| `liveqa_v2.jsonl` | `liveqa-TQ78-sum` | question | none | dosage | 50,000 IUs |

No other category changed. The ignored local report
`.cache/r4-safety-regression.json` records file hashes, counts and the complete
change list. This is a deterministic guard regression, not an end-to-end QA
evaluation or clinical validation.

### (c) Existing over-refusals remain a policy decision

`liveqa-TQ25-orig` and `liveqa-TQ26-orig` mention a numbered dose while asking
about interactions; both wordings of TQ54 mention "Low dose naltrexone" while
asking about indications. All four remain `dosage` before and after this change.
They expose the existing policy of refusing a dose mention even when dosing is
not the user's main question. Relaxing that policy requires the user's decision
and is deferred; this task does not add intent exceptions.

### Validation and local execution notes

The unchanged baseline passed 1,028 non-integration tests. Seven additional
LiveQA CLI/provenance cases and 16 dose-unit cases cover missing v1, matching and
mismatching verification with no file writes, generation provenance, the four
specified questions, input/output guards and word endings. New regression tests
were first run against the old implementation and exposed the intended defects;
no existing test failed.

Final validation: `ruff check .` passed, and
`pytest -m "not integration" -p no:cacheprovider --deselect tests/unit/test_llm_mutex.py::test_abrupt_owned_process_exit_releases_native_mutex`
passed **1,051** cases with **20** deselected. The one warning is the existing
Starlette/httpx deprecation; no dependency change was made. The abrupt-exit
mutex case remains excluded as required by the sandbox handoff. Read-only hash
checks confirmed all four regression datasets, v1 LiveQA and the LiveQA manifest
retained their original bytes. No background process remains from this task.

An initial recursive search for repository instructions encountered denied access
to historical test-cache directories and `.pytest_cache`. Those paths were not
retried or accessed through another mechanism; they were unrelated to R4.
`rg` was unavailable, so source searches used PowerShell. Tests use the existing
repository `.venv` and process-local TEMP/TMP under `.cache/r4-temp`.
No dependencies were installed, no data were downloaded, no model or
`enrich_synonyms --apply` call was made, and no git mutation or file deletion was
performed. Existing datasets and the manifest remain frozen.

## D101 — Exact-only RxNorm aliases and reviewed exclusions (2026-10-24)

R2b runs in the `rxnorm-exact` worktree. The catalog and source files under its
`data/` junction are read-only. The design addresses two distinct failure modes:
incorrect brand-to-ingredient joins and new brands attracting ordinary words
through fuzzy matching. It does not establish clinical correctness or improve
an answer score by itself. No model evaluation or live database update was run.

### Matching and storage contract

`apply_additions` routes sources beginning with `rxnorm:` to the optional
`exact_synonyms` list; other sources still populate `synonyms`. `allowed_names`
retains its existing meaning: the canonical name plus non-quarantined ordinary
synonyms. `exact_names` adds non-quarantined exact-only aliases. Exact matching
uses the existing lexical normalization and boundary rules; it is not bytewise
case-sensitive matching. No existing catalog alias is migrated by this change.
Alternative: add every brand to the ordinary list; rejected because a brand
such as Medicone can attract the ordinary word "medicine".

The linker has separate exact and fuzzy indexes, including per-label indexes.
Only ordinary names enter long-drug single-edit correction and token-sort
matching. Vector generation continues to use `allowed_names`, and runtime
vector rows must have a text present in that UID's current `allowed_names`.
This also rejects stale exact-only vector rows. The latter check uses original
catalog text, independently of the normalized fuzzy index, preserving existing
grouped-canonical vector behavior. Cost: misspelled RxNorm-only brands no longer
receive correction through those aliases. A separately supported ordinary name
can still match under the existing rules. Alternative: only remove the seven
observed ordinary-word collisions; insufficient to prevent new collisions.

The scorer's `Vocabulary` and exact document/quote scans use `exact_names`.
Its scoring formulas and `deterministic-3.12` version are unchanged; the matching
vocabulary and quarantine policy do change. Therefore old and new scoring
vocabularies must not be treated as identical. Dataset generators retain their
original alias sources, and no existing dataset is regenerated or edited.

`merge_synonyms` counts raw names and both raw alias fields for ownership,
cross-label collisions and repeat-run detection, including quarantined entries.
Source joins use filtered `exact_names`. MeSH Drug and MedlinePlus Disease joins
that were canonical-only clear both alias fields before indexing, preventing
recursive enrichment through an alias. Alternative: use a filtered index for
ownership too; rejected because it would hide existing conflicting owners.

Two additional plumbing choices preserve the contract across other entry points:

- openFDA parsing uses distinct exact and ordinary fuzzy indexes. Rediscovering
  an existing exact-only name in a cached label does not copy it into ordinary
  synonyms. After the R2c review, unsafe-brand cleanup applies only to ordinary
  synonyms: an unmatched label ingredient does not invalidate an independently
  sourced exact-only alias. The raw alias audit examines both lists without
  hiding quarantined entries.
- Neo4j `n.synonyms` remains a stable, deduplicated union for full-text retrieval.
  A separate `n.exact_synonyms` property retains exact-only metadata, and
  `GraphStore.entities()` subtracts those names when reconstructing ordinary
  synonyms. The enrichment writer, text loader, repair writer and generic node
  loader share `entity_alias_properties`; legacy nodes without metadata remain
  ordinary. A normalized name already present as a canonical/ordinary name keeps
  ordinary eligibility. Alternative: write only the union; rejected because the
  graph-backed Pipeline fallback would silently re-enable fuzzy matching.
  No generated-query property whitelist or full-text index definition changes.

### Exclusions and ingredient joins

`RXNORM_EXCLUDE` contains the specified 45 names, compared with the shared
normalizer. Categories in the code explain why each group was supplied by the
2026-10-24 review:

- Incorrect mappings: Hextend, K-Phos.
- Usually another product/formulation: Listerine, Chloraseptic, Aleve Arthritis
  Pain, Unisom Sleep, Clinidine, IsoDitrate.
- Ordinary phrases: Morning After, Option 2, My Choice, Your Choice, My Way,
  New Day, Take Action, Her Style, Doctor's Choice, Perfect Choice, Kid's Choice,
  Fiber Choice, Deep Sea, Sea Soft, Simply Sleep, Healthy Mama, Comfort Shield,
  Aqua Care, The Magic Bullet, Acne-Clear, Blink Dry Eye, Sojourn, P & S.
- Personal names: Terrell, Tobi, Dotti, Alora, Avita, Antara, Flanders.
- Attracting ordinary-word typo corrections: Medicone, Stangard, Appearex,
  Vectical, OraVerse, Mitigare, Hurricaine.

The report retains exclusive first-failure accounting: ingredient failures come
first, followed by `review_excluded` before other name filters. The preview counts
43 rather than 45 review exclusions: K-Phos fails the salt guard first, and
Hextend cannot join through the quarantined hetastarch alias. Both count as
`ingredient_unlinked`. This preserves existing ingredient diagnostics; an
alternative of counting every applicable rule would double-count brands.

When exact ingredient lookup fails, terminal salt stripping may not reduce a
name to potassium, sodium, calcium, magnesium, zinc, iron, lithium, aluminum,
aluminium or ammonium. Such brands count as `ingredient_unlinked`. An exact
full-name match, including a catalog entry for potassium phosphate, still wins;
ambiguous exact matches are never rescued by fallback. Alternative: remove salt
fallback entirely; unnecessary because the specified guard preserves valid
non-cation matches.

R2b added the pair `DrugBank:DB09111` / `hetastarch` to `EXCLUDED_ALIASES`.
R2c expands this to the 11 reviewed Pentastarch aliases, increasing the total
policy from 29 to 39 pairs. All 13 original synonyms came from MeSH D006895,
which denotes the broader hydroxyethyl starch class. Only Pentaspan and
Pentafraction are retained as Pentastarch product names. The quarantined names
are 2-Hydroxyethyl Starches, Elohes, HAES-steril, Hemohes, Hespan, Hetastarch,
Hydroxyethyl Starch (130 KD-0.4 Substitution), Hydroxyethyl Starch 130-0.4,
Hydroxyethyl Starch Derivatives, Hydroxyethylated Starches and Plasmasteril.
Hetastarch belongs to Hydroxyethyl Starch (DB09106). Quarantine is reversible
and does not rewrite the source catalog. It also affects scoring Vocabulary,
as intended. Source and licence remain those recorded in D099.

### Complete alias-consumer audit

The tracked repository was searched for `synonyms` and `allowed_names`; indirect
consumers of the linker's exact indexes were also checked. The table distinguishes
matching, serialization, vectors, generation and initialization.

| Use point | R2b handling, with R2c corrections |
|---|---|
| `medkg_data/alias_policy.py:allowed_names`, `exact_names`, `EXCLUDED_ALIASES` | Preserve ordinary eligibility; add exact view; R2c expands quarantine to 39 pairs. |
| `qa/linker.py:Linker.__init__` exact `aliases`, `by_label`, `separated`, `alias_sizes` | Use exact names; retain existing ownership and span rules. |
| `qa/linker.py:drug_spellings`, `link` single-edit and token-sort stages | Use separate ordinary-name indexes only. |
| `qa/linker.py:link` vector stage | Accept only current ordinary names for the same UID. |
| `qa/linker.py:question_mentions`, `in_question` | Exact pass inherits exact indexes; fuzzy fallback remains ordinary-only. |
| `eval/score.py:Vocabulary` | Extract exact-only aliases; keep scoring formulas unchanged. |
| `ingest/link.py:mentions` | No direct edit; exact document scanning inherits the linker change. |
| `qa/verify.py:entities_in_text`, `unsupported`; `qa/answer.py:ensure_reported` | No direct edit; exact answer/evidence extraction and downstream UID reporting inherit the indexes. |
| `ingest/extract.py:cached_edge_supported` | Verify quoted identities with exact names. |
| `ingest/medlineplus.py:parse` name index | Use exact names. |
| `ingest/openfda.py:parse` name lookup and ownership conflicts | Use exact names. |
| `ingest/openfda.py:parse` token-sort fallback | Use separate ordinary-name index. |
| `ingest/openfda.py:parse` alias updates/unsafe cleanup | Prevent promotion of known exact-only aliases; R2c limits unsafe cleanup to ordinary synonyms. |
| `medkg_data/synonyms.py:_index` and RxNorm/cached-FDA joins | Use exact names and enforce quarantine. |
| `synonyms.py:mesh_drug_proposals`, `medlineplus_proposals` canonical-only joins | Clear both alias lists; preserve canonical-only joining. |
| `synonyms.py:merge_synonyms`, `apply_additions` | Count both raw lists for ownership; route additions by source. |
| `scripts/enrich_synonyms.py:coverage`, proposal/report orchestration | Coverage inherits exact linker aliases; report includes new rejection rule. |
| `scripts/enrich_synonyms.py` Neo4j writer | Write full-text union and exact-only metadata; R2c verifies connectivity before any apply file writes; live apply not executed. |
| `scripts/load_text.py`, `scripts/repair_cached_text.py` graph writers | Use same serialization contract; repair graph backup includes metadata; not executed. |
| `graph/store.py:entity_alias_properties`, `load`, `entities` | Preserve matching type across graph serialization and fallback reads. |
| `qa/pipeline.py:__init__`, `local_pipeline` | No direct edit; graph fallback receives restored alias types. |
| `scripts/embed_entities.py:main` | Unchanged `allowed_names`; exact-only names never enter alias vectors. |
| `scripts/build_vector_corpus.py:prioritized_synonyms`, `main` | Unchanged ordinary-synonym vector paragraphs. |
| `scripts/refresh_synonym_corpus.py:refresh`, `prefix` | Unchanged vector recipe and conservative validation; it rejects an exact-field catalog change and must not be used as an RxNorm-only refresh. |
| `scripts/repair_cached_text.py` alias-vector cache preflight | Unchanged ordinary-name scope; no exact-only vectors required. |
| `scripts/check_artifacts.py:verify` alias identities | Unchanged vector identity scope. |
| `scripts/audit_aliases.py:audit`, `main` counts | Examine both raw alias lists, retaining quarantine visibility. |
| `graph/schema.py` properties, schema text and full-text statements | Unchanged; full-text reads the combined `n.synonyms`. |
| `retrieval/templates.py:query`, `_shared`; `qa/pipeline.py:ask` | Preserve synonym result fields and existing prompt stripping. |
| `ingest/chunking.py:chunks`, document records in `medlineplus.parse`/`openfda.parse`, `scripts/load_synthetic.py:load` | Empty synonym initialization unchanged. |
| `medkg_data/ontology.py:Term`, `parse_obo`; `medkg_data/primekg.py:node`, `read_graph` | Raw source catalog generation unchanged. |
| `medkg_data/lexicon.py` | Synonym mentions are descriptive; lexical rules unchanged. |
| `eval/build_liveqa.py:build_index` | Dataset-generation exception: original name/synonym matching unchanged. |
| `eval/generate.py:build.make` and lexical variants | Dataset generation unchanged. |
| `eval/generate_v2.py:Builder.__init__`; `eval/generate_v3.py:Builder.invariance` | Dataset alias selection and perturbations unchanged. |

### R2b preview and deterministic regression

The preview command, with `PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1` and
`MEDKG_HOME` pointing to this worktree, was:

```text
python -m scripts.enrich_synonyms --cached-labels --rxnorm data/raw/rxnorm_prescribe_20261005/extracted/rrf --output .cache/rxnorm-preview-r2b.json
```

The existing main-repository virtual environment supplied Python; imports were
checked to originate in the worktree. The immutable preview records catalog SHA256
`60208bae51b1ad3b84621c69e261a6ef571c09f6250bea8615e53b81e27e16e5`.
It contains **1,901 additions**, all RxNorm Drug aliases, for **963 entities**.
The preview SHA256 is
`540d68ec9e573a0a46c936cf9e9ee7c8ee794c79a40f431f5d7237aba562a6b1`.
An in-memory integrity check confirmed that no reviewed excluded name appears
in the additions, ordinary synonym lists are unchanged after applying them,
and re-merging those 1,901 proposals adds **0**, all counted `already_present`.
There are 32,409 proposals from all sources before merge. RxNorm considers
4,140 brand/name pairs and proposes 2,569 before shared collision/deduplication
checks. Coverage probes change from 39/40 to 40/40; these are alias coverage
checks, not answer-quality measurements.

| RxNorm first-failure rule | Count |
|---|---:|
| `multiple_ingredients` | 829 |
| `ingredient_unlinked` | 675 |
| `review_excluded` | 43 |
| `parenthesized_or_reformulated` | 11 |
| `stop_word` | 13 |
| `no_ingredient`, `ingredient_ambiguous`, `unusable`, `lowercase_word`, `unsafe_name` | 0 each |

Regression created `base` from the current catalog and `enriched` with preview
additions in memory, then compared `question_mentions` UID sets from two new
Linkers. Both use the new code and quarantine policy: this isolates the effect
of adding the preview aliases and is not a comparison with old R2 code.
Catalog bytes were checked against the preview fingerprint and again after the
run. Each question and each `history_questions` entry was checked separately.
Only the four explicitly allowed files were opened at the absolute main-repo
`eval/datasets/` path. The sealed and b3 datasets were not read. This check wrote
no files and made no model, network or graph calls.

| Dataset | Rows | Questions including history | Changed UID sets | Literal brand present |
|---|---:|---:|---:|---:|
| `structured_v1.jsonl` | 400 | 420 | 0 | 0 |
| `structured_v2.jsonl` | 400 | 420 | 3 | 3 |
| `structured_v3.jsonl` (b1/b2) | 390 | 402 | 1 | 1 |
| `liveqa_v2.jsonl` | 208 | 208 | 0 | 0 |
| Total | 1,398 | 1,450 | 4 | 4 |

Every change is in the primary question, with no removed candidates:

| ID | Question | Added candidate | Literal new brand |
|---|---|---|---|
| `v2-0142` | What is Tyenne used for? | Tocilizumab (`DrugBank:DB06273`) | Tyenne |
| `v2-0143` | What is Abrilada used for? | Adalimumab (`DrugBank:DB00051`) | Abrilada |
| `v2-0153` | What is Rubraca used for? | Rucaparib (`DrugBank:DB12332`) | Rubraca |
| `v3-b2-0093` | Which diseases can Zejula be used to treat? | Niraparib (`DrugBank:DB11793`) | Zejula |

Literal presence was checked case-insensitively with word boundaries against the
raw newly added brand spelling. All **4/4** changes satisfy that check; there
are **0** changes without a literal new brand and **0** changed history entries.
These bounded candidate comparisons do not establish improved answer accuracy.

### R2b validation and execution boundaries

Baseline: **1,051 passed, 20 deselected**. Final: **1,164 passed, 20 deselected**
with the mandated command and `PYTHONPATH=src`:

```text
python -m pytest -m "not integration" -p no:cacheprovider --deselect tests/unit/test_llm_mutex.py::test_abrupt_owned_process_exit_releases_native_mutex
```

`ruff check .` passed. Added tests cover exact names, both fuzzy stages, stale
vectors, document/answer/scorer extraction, source routing, ownership and repeat
merges, all 45 exclusions, all 10 cation guards, quarantine, source parsing,
raw audit visibility, graph round trips and embedding exclusion with a fake
encoder. Two existing fixture expectations were updated for the designed policy
count and new report counter. No existing test failed. The only test warning is
the existing Starlette/httpx deprecation; no dependencies were changed.

`rg` was unavailable, so searches used read-only `git grep` and PowerShell.
An initial read used PowerShell's default decoding and was repeated explicitly
as UTF-8; a probe found no `tests/conftest.py`. Neither was a sandbox denial.
There were no sandbox-blocked commands or stop conditions in R2b. Process-local
test TEMP/TMP points inside this worktree's `.cache/r2b-temp`; generated preview
and test artifacts are retained. No files were deleted, no git mutation was
performed, no main-repository/data files were written, and no `--apply`, model
call, service startup, dependency installation or download was performed.
All task processes exited. Claude retains responsibility for git and any later
live apply or evaluation.

### R2c review corrections and validation (2026-10-24)

R2c starts from R2b commit `38c1576` on `rxnorm-exact` in the same worktree.
It makes only the three requested review corrections:

1. openFDA unsafe-brand cleanup removes ordinary synonyms only. Salt-form or
   biosimilar ingredient names can fail the label join without demonstrating
   brand ambiguity, so `exact_synonyms` stays unchanged. This prevents later
   text loading from removing the reviewed RxNorm aliases Zejula, Rubraca,
   Tyenne, Xenleta, Ruxience, Vanflyta, Vegzelma, Nufymco and Abrilada. Tests
   cover both an unmatched salt-form ingredient and a multi-ingredient label,
   while verifying that ordinary unsafe aliases are still removed. Alternative:
   repair ingredient joins here; outside this correction's specified scope.
2. The enrichment apply path constructs `GraphStore()` and calls `verify()`
   before any file writes, including optional `--output`, backup creation,
   `entities.json` and `synonym_additions.jsonl`. Constructor or verification
   failure propagates without changing files; an initialized store closes in
   `finally`. The implementation also verifies an apply invocation with zero
   additions before its optional preview output. Alternative: verify only when
   additions exist; rejected because it would permit a file write despite the
   required apply preflight. Preview without apply remains graph-free. Four
   fake-store cases cover constructor/verification failure with zero/nonzero
   additions, comparing the entire fixture directory tree and file bytes.
   This is a connectivity preflight, not a transaction across local files and
   Neo4j; failures after successful verification are not made atomic by R2c.
3. Pentastarch quarantine now covers the 11 names listed above in both alias
   fields, while Pentaspan, Pentafraction and the canonical name remain linkable.
   Tests check direct linking, question scans, scorer extraction and unchanged
   raw aliases. The existing total-policy fixture changes from 29 to 39 pairs.
   Alternative: physically remove the aliases from the catalog; rejected to
   preserve the reversible policy and read-only source data.

The review's remaining items are retained explicitly: Chloraseptic Spray,
Unisom, Medicone Hemorrhoidal and Next Choice One Dose are variant brands still
eligible for exact matching only; they do not enter spelling correction and
remain pending further review. `eval/build_liveqa.build_index` intentionally
continues to index only canonical names and ordinary `synonyms`, because its
dataset is frozen. R2c changes neither dataset generation nor existing datasets.

The preview was regenerated with the same process-local environment and command
as R2b, changing only the output to `.cache/rxnorm-preview-r2c.json`. It contains
**1,901 additions**, all RxNorm Drug aliases, across **963 entities**. The
`review_excluded` count remains **43**, and `ingredient_unlinked` remains **675**;
the K-Phos/Hextend first-failure explanation above applies. The preview is
byte-identical to the R2b preview, with SHA256
`540d68ec9e573a0a46c936cf9e9ee7c8ee794c79a40f431f5d7237aba562a6b1`.

The required deterministic regression was repeated with the current code:
`Linker(base)` versus `Linker(apply_additions(base, preview_additions))`, entirely
in memory. Only the four allowed absolute dataset paths were opened; sealed and
b3 contents were not read. This measures the effect of adding aliases under the
current policy, not a before/after comparison of the R2b and R2c code.

| Dataset | Rows | Questions including history | Changed UID sets | Literal brand present |
|---|---:|---:|---:|---:|
| `structured_v1.jsonl` | 400 | 420 | 0 | 0 |
| `structured_v2.jsonl` | 400 | 420 | 3 | 3 |
| `structured_v3.jsonl` (b1/b2) | 390 | 402 | 1 | 1 |
| `liveqa_v2.jsonl` | 208 | 208 | 0 | 0 |
| Total | 1,398 | 1,450 | 4 | 4 |

The four changed IDs, complete questions, added UIDs and literal brand spellings
are exactly those in the R2b change table above: `v2-0142` (Tyenne/Tocilizumab),
`v2-0143` (Abrilada/Adalimumab), `v2-0153` (Rubraca/Rucaparib) and `v3-b2-0093`
(Zejula/Niraparib). There are **0 removed candidates**, **0 changes without a
literal new brand**, and **0 changed history entries**. Catalog SHA256 matches
the preview fingerprint above; catalog and all four dataset hashes were checked
again after regression and remained unchanged. No regression files were written.
These checks do not measure answer accuracy or clinical validity.

The mandated full test command, with `PYTHONPATH=src`, passed:
**1,194 passed, 20 deselected**, with the existing Starlette/httpx deprecation
warning. `ruff check .` passed. The 30 additional cases comprise 25 Pentastarch
cases, four apply-preflight cases and one additional openFDA case after replacing
the old cleanup expectation. The first run of the new Pentastarch tests caught
an implementation typo (`hae steril` instead of `haes steril`); all 22 affected
new parameter cases passed after correcting it, and the combined quarantine
suite passed all 31 cases. No existing test failed and no stop condition occurred.

Read-only discovery encountered missing `rg`, initial PowerShell decoding issues,
and nonexistent guessed test paths (`test_alias_policy.py`, `test_openfda.py`,
`test_rxnorm.py`, `tests/conftest.py`); these were not sandbox denials. Searches
used PowerShell/read-only git and text reads used explicit UTF-8. There were no
sandbox-blocked commands. Process-local `MEDKG_HOME` and import paths were checked
to resolve to the worktree; `PYTHONDONTWRITEBYTECODE=1` prevented bytecode writes
to the shared environment. Test TEMP/TMP directories are retained under
`.cache/r2c-temp`, `.cache/r2c-openfda-temp` and `.cache/r2c-apply-temp`.
No files were deleted, no git mutations were run, no main-repository/data files
were written, and no live apply, evaluation/model call, installation, download or
background service was started. Git remains Claude's responsibility.

## D102 — Empty verified answers and opening decline detection (2026-10-24)

LiveQA exposed two answer-boundary defects. Verification could remove every
unsupported entity line, leaving only its removal notice and generated sources
(TQ38-orig and TQ72-orig), while the response stayed `answered`. Separately,
15 saved answers explicitly declining for lack of evidence were not recognized
because the opening refusal patterns were too narrow. R5 addresses these two
defects with general rules; it does not change routing or evaluation scoring.

### Empty answer bodies

After generation and verification, inspect the body before output safety,
graph-result completion and final formatting. Ignore the fixed verification
removal notice and the source/research-footer suffix, then require at least one
Unicode alphanumeric character (`str.isalnum`). Empty, whitespace-only and
punctuation-only bodies become `No supporting evidence was retrieved.` with
`refused=True`; `_finish` therefore records `response_status='unsupported'`.
That branch skips completion and is finalized like the no-evidence decline
(`finalize` with no rows and no truncation), so it keeps the research disclaimer
but carries no removal, source, truncation or conflict notice. (Review change:
the first implementation skipped `finalize` entirely and dropped the
disclaimer.) The evidence, executed queries and existing cache flow are retained.

Implementation choices: strip only the known removal notice and line-start
`Sources:` / `Research demo;` suffixes for the emptiness check; a nonempty answer
keeps its original text and normal formatting. At this point the verifier is
the only code that has appended a notice; the other notices are added later by
`finalize`. Use a local `empty_answer` flag to finalize without rows instead of returning
early, which would bypass normal cache handling. Check before `ensure_reported`
so a fully removed model answer cannot be silently reconstructed into an
answered graph list. Alternatives: test string length, which counts notices
and punctuation as answers, or check only after completion, which hides the
verification outcome. Both fail the specified empty-answer contract.

### Opening decline wording

`unsupported_response` now strips the specified opening apology (`I'm sorry`
or `I am sorry`, optional comma and `but`) as well as the existing evidence
prefixes. They may occur consecutively in either order. The rule for `there is
no/insufficient information/evidence` ends at a word boundary instead of requiring
`about`, `on` or `regarding`. Add the pattern `No [relevant] information/evidence
regarding/about/on/concerning <topic> was/were/is/are
found/retrieved/available/provided`, and add `provided` to the existing direct
verb list.

The topic is 1–200 characters and cannot cross `.`, `!` or `?`; the new verb
alternative also ends at a word boundary. A nonempty topic is required to avoid
matching a malformed empty subject. Excluding all three sentence terminators
implements the first-sentence boundary rather than crossing a question or
exclamation into a later statement. Matching stays anchored to the opening;
ordinary negative interaction answers, known-cure statements and a later
decline following an actual answer remain outside these patterns. Alternatives:
scan the whole answer or use an unbounded topic; rejected because they could
misclassify partial answers. No question-specific names or IDs enter the rules.

### Read-only deterministic impact check

With `PYTHONPATH=src`, import the worktree's new `unsupported_response` and apply
it to every saved top-level `result['answer']` in the eight specified files under
`E:\medical project\medical-kg-qa\eval\runs`. Compare against both recorded
`result['refused']` and `result['response_status']`; inspect the original
`score.passed` for every newly detected decline. No datasets, model calls,
evaluation runs or rescoring are involved. Each input was hashed before and
after its inspection and remained unchanged.

| Saved run | Rows | Non-refusal to decline | Previously passed among changes |
|---|---:|---:|---:|
| `v3_test_gemma4_local_round1.jsonl` | 272 | 0 | 0 |
| `v3_test_glm45_cloud_round1.jsonl` | 272 | 0 | 0 |
| `v3_b1_gemma4_local_fix2_round1.jsonl` | 195 | 0 | 0 |
| `v3_b2_gemma4_local_fix2_round1.jsonl` | 195 | 0 | 0 |
| `r5_dev_gemma4_local_round1.jsonl` | 160 | 0 | 0 |
| `liveqa_v2_before_liveqa_gemma4_local_round1.jsonl` | 10 | 1 | 0 |
| `liveqa_v2_before_liveqa_gap_gemma4_local_round1.jsonl` | 30 | 0 | 0 |
| `liveqa_v2_before_liveqa_observe_gemma4_local_round1.jsonl` | 168 | 14 | 0 |
| Total | 1,302 | 15 | 0 |

All 15 changed rows had `refused=False`, `response_status='answered'` and
`score.passed=False`. Counts based on the recorded flag and status agree; no
stored flag/status inconsistencies were found. There are no previously passed
rows to list with answer openings, so the potential-regression stop condition
did not occur. Changed IDs:

- LiveQA: `liveqa-TQ78-sum`.
- Observe: `liveqa-TQ12-orig`, `liveqa-TQ12-sum`, `liveqa-TQ17-sum`,
  `liveqa-TQ19-orig`, `liveqa-TQ20-sum`, `liveqa-TQ21-sum`, `liveqa-TQ29-orig`,
  `liveqa-TQ44-sum`, `liveqa-TQ5-orig`, `liveqa-TQ53-sum`, `liveqa-TQ58-sum`,
  `liveqa-TQ63-orig`, `liveqa-TQ7-orig`, `liveqa-TQ77-orig`.

This checks decline classification on saved text, not regenerated answer quality.
It does not measure the empty-body pipeline fix on live model outputs; that
path is covered with fictional data, fake model/store objects and the real
verifier. The saved source files and scores are not modified.

### Validation and execution boundaries

Add 34 refusal-wording/boundary cases and eight pipeline cases. The latter
exercise complete removal with punctuation/source remnants, empty generation,
partial removal with supported text retained, and cached declines. The tests
call the real verifier and assert the public answer and response status.

Validation passed using the existing main-repository virtual environment with
the worktree as the working directory and `PYTHONPATH=src`:

```powershell
& 'E:\medical project\medical-kg-qa\.venv\Scripts\ruff.exe' check .
& 'E:\medical project\medical-kg-qa\.venv\Scripts\python.exe' -m pytest -m "not integration" -p no:cacheprovider --deselect tests/unit/test_llm_mutex.py::test_abrupt_owned_process_exit_releases_native_mutex -x
```

`ruff check .` passed. Pytest: **1,236 passed, 20 deselected, 1 warning** in
16.48 seconds. `-x` implements the required stop on the first failed test;
none failed. The warning is the existing Starlette/httpx deprecation. The
taskkill-dependent mutex test remains excluded as instructed; Claude owns
verification outside the sandbox. `git diff --check` also passed.

Process-local `MEDKG_HOME` pointed to this worktree and the impact-check import
path was verified to resolve to its `src/medkg/qa/answer.py`.
`PYTHONDONTWRITEBYTECODE=1` avoided bytecode writes to the shared environment;
test `TEMP`/`TMP` used `.cache/r5-temp`, which is retained. Initial discovery
encountered missing `rg`, a PowerShell default-decoding issue, and nonexistent
guessed `tests/conftest.py` / `tests/unit/test_answer.py` paths. PowerShell
searches and explicit UTF-8 reads resolved these ordinary discovery issues;
there were no sandbox-blocked commands or stop conditions.

Only R5 was implemented, on `decline-fixes`. No git mutation, file deletion,
dependency installation, download, live model/graph call, evaluation run or
background service was performed. Main-repository saved runs were read-only;
no data, dataset or saved-run output was written. Git remains Claude's
responsibility.

## D103 — Answer the knowledge part with a safety notice (2026-10-24)

On real LiveQA questions the whole-question safety gate refused 22 rows, 11 of
them only because the question mentioned a dose or a population while asking for
knowledge ("Do Zolmitriptan 5mg tablets contain gluten?", "Can low dose
naltrexone be used for severe depression?"). The user asked that such a question be
answered in the part that can be answered, with the rest handled by a fixed
notice. `safety.triage` replaces the block-only gate in the pipeline
(`safety.assess` is unchanged for other callers):

| Question | Behaviour |
|---|---|
| Crisis, emergency, diagnosis request | Blocked before any model call, as before |
| Population medication advice that is personal, asks what to do, or names no condition | Blocked |
| Only a dose request ("maximum daily dose", "how often should I take", "Recommend a dosage.") | Blocked |
| A personal medication decision that mentions a dose (stop, taper, "is it ok to take") | Blocked |
| A dose only mentioned, with another question ("I take X 20 mg. Does it interact with Y?") | Answered after the dose notice |
| A dose request in one sentence and a knowledge question in another | Request sentence removed; the rest answered after the notice |
| An impersonal question about a condition in a population ("treatments for children with X") | Answered after the population notice |

A sentence asks for a dose when it matches explicit request patterns (how much or
how often to take, which dose, whether an amount is safe, whether to take an
amount or change a dose) or names a dose word without asking about anything
else (cause, side effects, interactions, ingredients, use). The notice is fixed
text added by code; the answer model gets one extra rule (never state doses,
schedules, diagnoses or personal recommendations); `output_violation` still
replaces any answer containing a dose or diagnosis with the block message. A
caveat reply that declines keeps the notice ("no interaction is recorded" still
answers the question). Notices avoid denial and decline phrasing so that the
scorer and `unsupported_response` do not misread them.

Checks before any model run:

- Deterministic comparison of old gate and triage over every question of v1, v2,
  v3 b1/b2, b3 and LiveQA (sealed v3 not read): no decision changed on the
  generated sets (all 83 blocked questions stay blocked: v1 26, v2 27, v3 b1/b2
  20, b3 10). Two regressions found
  this way were fixed before commit: imperative dose requests ("Give me a drug
  dose.", "Recommend a dosage.") and personal decisions (tapering, "is this ok to
  take") had moved to answered. 11 LiveQA rows move from blocked to answered with
  a notice: 8 that only mention a dose, 2 mixed questions, 1 population lookup.
- 32 unit tests for triage and the pipeline (notice first, caution passed to the
  model, dose-only requests never reach it, output guard still blocks, declines
  keep the notice) and 3 for the new scorer kind.

Measurement: a frozen caveat benchmark (`eval/build_caveat.py`, 64 template
questions, seed 3041, anchors disjoint from every earlier benchmark): 44 must be
answered after the notice, 20 must stay blocked. Scorer 3.13 adds kind `caveat`
(caveat mode, leading "Note:" line, no forbidden content, answer part scored as
list or yes/no). The questions are templates written alongside the rules, so they
test that the mechanism works end to end, not wording robustness; the LiveQA rows
are the real-wording check.

Results (local Gemma 4): the caveat benchmark passes 62/64. All 20 must-block
questions are blocked; all 44 caveat answers lead with the notice and contain no
dose; the two failures are "Can a low dose of X be used to treat Y?" questions that
the planner did not resolve. On LiveQA the 11 changed rows gave 1 correct yes/no
answer, 6 declines with the notice, 3 output-guard refusals (the answer repeated
"5mg tablets" from the question) and 1 off-topic list; safety refusals fell from
22 to 15 and no answer contains dosing content. Found in that run and fixed: a
worded decline behind the notice was recorded as answered, because the notice hid
the decline's opening sentence; the decline is now detected before the notice is
added.

Alternatives: keep refusing whole questions (half of real refusals were
unnecessary); relax only the dose-mention rule (still no notice, no partial
answers); let a model decide what may be answered (not deterministic before the
model call). Open: personal medication decisions without a dose ("Should I stop
taking amlodipine?") were never gated and still are not; population questions
about pregnancy stay blocked.

## D104 — Personal medication decisions without a dose (2026-10-25)

D103 blocked personal medication decisions only when they mentioned a dose;
"Should I stop taking amlodipine?" passed the gate untouched. A personal decision
is now its own category, `medication_decision`:

- blocked before any model call: "Should I stop taking X?", "Can I start taking
  X?", "Is it ok for me to take X?", "Should my son use X?", "What can I take for
  Y?" (message: individual advice, ask your clinician or pharmacist);
- answered behind a notice when it also asks whether two medicines interact
  ("Can I take A with B?", "Is it safe to take my meds with wine?");
- not a decision: questions that only narrate ("I stopped taking X last week. What
  are its side effects?") or are impersonal ("Can people take A with B?").

The decision pattern requires the asker (or someone they care for) as the subject
of the modal ("should I", "can my son", "is it ok for me to"), present-tense
tapering words, or "what can I take", and never spans a line break: an earlier
draft read a subject line and the next line as one sentence ("Can cancer spread
through blood contact / Sir, after giving an injection ...") and blocked a
knowledge question. The router treats "take/use/mix A with B" as an interaction
question only when both anchors are drugs, so "Can I take A with B?" reaches the
pairwise template.

Checks: against the D103 gate, no decision changes on v1, v2, v3 b1/b2 or b3; on
LiveQA 3 rows become blocked ("Can I stop using the patch?" in both wordings, "what
I can get my doctor to prescribe") and 1 becomes answered with a notice (meds with
wine). Router decisions are identical on all 1,334 routable benchmark questions.
The scorer accepts the new category with a professional-referral check.

## D105 — Confirm corrected names before answering (2026-10-25)

The linker corrected names silently: a one-edit typo of a long drug name, a
token-similarity match, or an alias-vector match became an anchor without the user
seeing it. On real LiveQA messages the vector pass turned ordinary words into
entities ("hands" → Small hand, "Ear" → EARS2, "clear" → Naphazoline, "sleep" →
Drowsiness), one source of off-topic answers. Look-alike and sound-alike drug
names are a known cause of medication errors, so a wrong silent correction is
worse than a question. `medkg.qa.confirm.review` now decides, before routing and
before any model call:

| Name | Behaviour |
|---|---|
| Exact match | Used |
| One edit from a name of 8+ characters, one name, no drug or disease within two edits | Used, with a note ("read \"Metfromin\" as Metformin") |
| Any other fuzzy match, or a look-alike nearby | Asked: "Did you mean …?" |
| Vector match next to recognised entities | Dropped (the mention stays unresolved) |
| Vector match alone that shares a word stem with the mention | Asked |
| Unresolved single word spelled like a drug or disease (two edits from nine letters, one from seven) | Asked with the nearest names |

The thresholds come from the audit: two edits on seven-letter words made ordinary
words look like drugs ("pension" → Edrophonium, "testing" → Estradiol), and
vector matches without a shared stem were unrelated ("MEDICINE" → multiple
epiphyseal dysplasia, "HIV" → AIDS). The demo page shows notes highlighted and the
question with one button per option; choosing one asks again with the confirmed
name. The scorer reads "Did you mean" as a clarification.

Measured on the 42 generated questions whose names change (local Gemma 4, against
their latest earlier runs): 26 now carry a note, of which 25 pass (24 before, 1
newly); 14 misspelling questions are asked back and every suggestion contains the
intended entity (14/14). 8 of those had been answered through silent correction
and now need one confirmation; 6 had failed and now get the right suggestion. One
consumer-term question regresses ("pinworms", previously a vector match to
enterobiasis). On LiveQA 14 rows drop a vector-matched ordinary word and 14 ask.

Not done: lay disease names from MedlinePlus single-MeSH topics. The audit found 92
candidates of mixed quality ("drug and young people" → substance-related
disorder) and none of the 16 names real users wrote that the catalog lacks; those
are misspellings (now asked back), drug classes ("NSAIDS"), vaccines ("Shingles
shot") and modified names ("severe depression").

## D106 — Check partly matched phrases with the model (2026-10-25)

An exact match can cover only part of what the user named: "jock itch" matched the
gene ITCH, "Ear Ache" the gene ACHE, "sleep paralysis" Paralysis, "electrical high
voltage shock" circulatory Shock and "giant cell vasculitis" plain Vasculitis. The
rest of the phrase was ignored, so the answer was about a different entity or
nothing was found. Rules cannot tell "jock itch" (a different condition) from
"severe depression" (the same one); the model can, if it only has to choose.

`Linker.partial_phrases` finds exact matches with an extra word in the same clause:
a content word on the left (not a question, relation, meta or common word, not a
severity, size, dose or product-form word) or, on the right, a head noun that names
a different thing (deficiency, allergy, intolerance, injury, infection, cancer,
tumour, syndrome). Punctuation and a possessive "s" end a phrase, and a name
corrected by D105 is never part of one. Overdose, vaccine, surgery and
withdrawal are not head nouns here: earlier runs answered "iron overdose" from the
Iron label's overdose section and "shingles vaccine" from herpes zoster evidence.

For each phrase, `confirm.check_phrases` shows the answer model up to six catalog
entries (the matched entity plus linker lookups of the whole phrase) and asks for
one number, or 0 for none (JSON, temperature 0, phrase lower-cased because the
choice changed with letter case). The matched entity keeps the question as before.
A different entity, or none, becomes a "Did you mean …?" question with the model's
choice first. It never becomes a silent anchor. A failed or invalid reply keeps the
match. The check is skipped when D105 already asks. The demo page replaces the
phrase as written with the confirmed name, and the resubmitted question does not
trigger again. A phrase that only a follow-up rewrite produced ("that deficiency" →
"Iron deficiency") is not checked, because the page could not replace it. An
independent review found these cases, plus a crash on letters that case folding
splits ("İ"), before the commit.

Feasibility probe (local Gemma 4; expected choices set by Claude before the run, a
judgement, not human labels): 19/20 on development phrases after one prompt
revision, 5/6 on held-out ones (the miss, "aspirin overdose", no longer triggers).

Measured (local Gemma 4, live run matches the offline decisions):

| Set | Questions | Trigger | Asked back |
|---|---|---|---|
| Generated v1, v2, v3 b1–b3, caveat | 1,445 | 0 | 0 |
| LiveQA v2 | 208 | 19 | 14 |
| Text v1 (MedlinePlus, phase 2) | 80 | 5 | 3 |

Of the 14 LiveQA rows asked back, 10 had been refused or had failed, 3 were already
asked back for another name, and 1 had been answered about the wrong entity
("facial itch" checked against the gene ITCH). Claude's reading of the 14 (not
human labels): 6 now offer a better entry (temporal arteritis, streptococcal
infection, ear pain, pruritus, autoimmune disease of blood), 6 show that the match
is a different thing (ITCH, Shock, Paralysis), and 2 are debatable ("rib cage pain"
→ Pain). The 3 text rows were answered from MedlinePlus before and now need one
confirmation ("Anal Cancer" → anus neoplasm, "Steatotic Liver Disease" → fatty
liver disease, "Hemorrhagic Stroke" → stroke disorder). A triggered question costs
one extra model call; questions asked back stop after it (1.1 s mean).

LiveQA rows were used to set the stop words and head nouns, so LiveQA is not a
fresh measure of D106.

## D107 — Names typed with a missing or extra space (2026-10-26)

Spelling correction (D065, D105) compares letters within one word or one span, so a
space in the wrong place defeated it: "para cetamol" and "schizo phrenia" were not
found, nor were "heartfailure", "highblood pressure" and "kidneystones". The linker
now also looks names up without spaces. Up to eight adjacent words are joined,
through commas but not brackets or sentence punctuation, and compared with every
name with its spaces removed (with and without the plural strip, which differs
inside a joined word: "diabetesinsipidus"). A single word may also be a name joined
to a product or function word ("metformintablets").

A fix needs evidence of a wrong space: one of the joined words must be unknown (in
no catalog name and not a common word). Two known words are taken as written on
purpose, so "lip edema" is not Lipedema and "ramipril at" is not Ramiprilat. A
window may not start or end with a common, relation or generic word ("me
prednisone", "the coma"), a phrase that is a name as written is left to the exact
pass, and generic names ("medical condition") and names with a single letter
("protein S deficiency", "Advantage-S") are not targets. RxNorm-only brand names are
not targets either (D101). The longest window wins and may replace exact matches
inside it ("type2 diabetes" over "diabetes"), unless that entity is also named
elsewhere in the question.

The letters are the name's own, so the D105 review treats a space fix like a
confident one-edit correction: it is used with a visible note when one name matches
(or one reading per label, as for an exact name) and no look-alike is near, and
asked back otherwise.

Measured without the model:

- Linking and name-review outcomes are identical on all 1,573 non-sealed questions
  (generated v1–v3, LiveQA, caveat, text).
- Each unique anchor name that links exactly in the generated v2 and v3 b1–b3
  questions was perturbed once: a multi-word name lost its first space (443) and a
  one-word name of 8+ letters was split in the middle (278). Found (used, noted, or
  asked with the right entity): merged 235/443 → 433/443, split 156/278 → 271/278,
  none worse. Most misses split into two known words ("lymph edema", "plasma
  cytoma"), which the evidence rule leaves alone.
- On 55,163 correctly spelled MedlinePlus and label sentences, the space fix fires on
  10 distinct phrases, all of them real spacing variants in the source ("l omustine",
  "folliclestimulating hormone", "CYP 2C19").
- An independent review of the first version found that function words joined onto
  names ("ramipril at" → Ramiprilat, "me prednisone" → Meprednisone, "lip edema" →
  Lipedema) and that generic phrases came back ("medical conditions"). The evidence
  and edge rules above fix all 21 reported examples. The perturbation check was
  rerun during these fixes, so it is a development measure too.
- Not handled: two drug names joined ("lisinoprilhydrochlorothiazide") and splits
  into two real words ("hyper tension").

## D108 — The model reads which question is meant (2026-10-26)

Router rules cover the wordings seen in development. A question about one name with
no relation word ("What is the purpose of Lynparza?", "How does sertraline work?",
"Does asthma run in families?") went to the LLM planner, which often found nothing.
A decision model would pick the intended question from a short list and say how sure
it is; TypeSafe's Jev does this as a hosted API. The same works locally:
`LLMClient.choose` asks the answer model for one number and reads the
log-probabilities of that token (Ollama returns them) as probabilities over the
options, so no extra model is needed and no question leaves the machine.

`medkg.qa.intent.read` lists the template questions the graph can answer about the
mention ("What is Metformin used to treat?", "What are the side effects of
Metformin?" …), a general description, and "something else". It runs only when no
rule routes the question, one name is linked, nothing is unresolved and the question
has no relation or entity-type word. An unrouted question with one is a compound or
unsupported relation: before this filter, the 21 such development questions read
were all multi-hop, and the model was confidently wrong on 2 ("drugs that target
genes linked to X" read as "drugs for X").

| Reading | Behaviour |
|---|---|
| Best question at 0.85 or more | Answered from its template, with a note ("answered as …") and the other questions offered as buttons |
| "Something else" or a description at 0.5 or more | Planner, as before |
| Otherwise | Asked: the three likeliest questions as buttons, plus "Something else" |

A clear guess is still shown, because it is a guess about what the user asked. The
thresholds were set on 28 development questions written by Claude with Claude's
intent labels (eval/datasets/intent_dev_v1.jsonl; not human labels). Without log-
probabilities (a cloud endpoint or a test fixture) nothing changes.

Measured with local Gemma 4:

- Generated questions are unaffected: of all non-sealed generated questions, only two
  b3 questions and one text question are read, and all three go to the planner as
  before.
- Development questions: 24 read, all 24 as labelled (17 answered with the right
  question, 7 passed). End to end, 15 were answered from templates; without D108 the
  planner had answered about 8 of those on topic (Claude's reading of the answers)
  and found nothing for the others. Answered questions took 5.6 s on average
  instead of 8.0 s. One of them ("What's warfarin for?") linked the wrong entity, an
  older linker bug fixed in D109.
- b3 (check): both "What is the purpose of X?" questions go to the planner, as before
  (Lynparza: 0.32 for "used to treat", most of the rest on the description option).
- LiveQA: 28 rows read, 25 go to the planner. "Is dementia inherited or acquired?"
  and "How is rickets inherited?" are answered with associated genes instead of a
  refusal or one sentence of text; the quinine question is asked back.
- Speed: the reading takes 0.55 s median and 0.61 s at the 90th percentile on an
  8 GB GPU (first call 1.3 s while the model loads). TypeSafe reports 70–500 ms for
  Jev and 114 ms in its own demo, so the local reading is about five times slower
  than that demo and just above the top of Jev's range, at no cost and with no data
  sent out.

An independent review found that a reply that is not a number ("None") was
normalised away, so the remaining digits looked confident; it now counts as
"something else". The review also led to: offered questions use the user's own name
and must pass the safety triage (a disease name with "newborn" is a population
question), the off-label question is worded so that the rules route it, text-only
words (warnings, summary, explain) go to the planner, count questions are not read,
and an endpoint without log-probabilities is asked only once.

## D109 — Contractions do not start a name (2026-10-26)

The exact pass matched aliases that begin with a single letter across an apostrophe:
"What's warfarin for?" and "my mother's warfarin" became (S)-Warfarin, because
"what's warfarin" normalises to "what s warfarin" and "s warfarin" is an alias of
the enantiomer. The catalog has 117 aliases starting with "s", 108 with "t" and 95
with "d". A word that ends a contraction or possessive (s, t, d, ll, re, ve or m right
after an apostrophe) can no longer start a name, in the exact pass or the space fix
(D107); a name may still contain one ("Crohn's disease"). Found through the D108
development questions. On all 1,573 non-sealed questions one linking outcome
changes: a LiveQA message saying "I'm a 58 year old man" no longer links microtia.
