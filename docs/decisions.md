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
