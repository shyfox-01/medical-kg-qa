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
