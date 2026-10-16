# Phase 4 — Service, OpenTelemetry and reproducible engineering checks

Implemented FastAPI POST /ask, POST /ask/stream, GET /health and GET /ready.
The request includes at most four history turns. SSE sends processing status,
then verified final-answer chunks and the complete result. Readiness checks
Neo4j connectivity and LLM configuration only; it does not call the provider.
Questions/focus strings and concurrency are bounded. Native services bind loopback.

Replaced provisional stage JSON logging with actual OpenTelemetry SDK spans:
request root, safety, linking, routing/planning, each tool, generation,
verification, output safety, LLM calls and request totals. JSONL exports actual
trace/span/parent ids and metadata without question text, evidence or secrets.
OTLP HTTP is enabled only by an explicit endpoint; Phoenix viewing is documented.
The SDK parent relationships and actual API trace ids were verified locally.

Added a non-root Docker image and two-service Compose configuration with Neo4j
5.26 Community, health checks, runtime credentials and loopback published ports.
GitHub Actions runs lint/unit tests, a fictional graph and FakeLLM integration/
three-round evaluation/redline gate, compose configuration and image build.
No real LLM/model download occurs in the CI evaluation. It runs no real corpus.

Engineering review also completed both-source conflict rendering, evidence
prioritization, optional-null argument handling, generated-query provenance
examples, Document fulltext source/URL preservation and a conservative output
dose/personal-diagnosis guard. Every physical provider request keeps thinking off.
These are implementation corrections, not changes based on frozen test answers.
Decisions D018–D022 explain the choices and alternatives.

## Verified checks

| Check | Result |
|---|---|
| Ruff | Passed |
| Unit tests | 57 passed |
| Native Neo4j integration tests | 6 passed; CSV/PrimeKG counts, read guard, fictional traversal/indexes, both conflict sources/evidence |
| Complete pytest run | 63 passed; one upstream Starlette/httpx deprecation warning |
| Document fulltext provenance | Additional targeted native integration check passed after the metadata correction |
| Real localhost HTTP/SSE | 10/10 checks passed, including crisis/language zero LLM calls, history 422, real development retrieval and SDK trace correspondence |
| Fictional test corpus | 13/13 per round, three rounds, std 0; redline gate exit 0 |
| Final structured gate | Same 54/240 cases x three rounds; exit 0 against phase-3 v1 |
| Pure-vector negative gate | Archived phase-3 run has 13 regressions and actual exit 1; preserved |
| Private-artifact/credential audit | No raw/processed data, private gold/queues, raw results or environment secret values tracked |
| Docker Compose | YAML topology/image/loopback ports inspected locally; actual config/build unverified |
| Remote GitHub Actions | Unrun: no push performed |
| Phoenix receiver | Unavailable locally; optional OTLP implementation not receiver-tested |

The JUnit report is local in ignored eval/runs/phase4_tests.xml. API aggregate
checks are in api_summary.json; final environment/artifact audit is
delivery_summary.json. The temporary synthetic namespace is removed after local
checks. No parent application or global environment was modified.

## Final repeated structured measurement

Three rates: 70.3704%, 72.2222%, 70.3704%; mean 70.9877%, population std 0.8730
percentage points. Inconsistent id: structured-0147. No recorded pipeline failure
stages in these rounds. Redline regressions: none relative to v1. The baseline's
already-failing adversarial case still fails, so this gate is not an all-attacks
pass statement. v0's mean is 74.0741%; no overall improvement claim is supported.

These three rounds repeat every safety/adversarial test case and three questions
per other category, with cache off. They do not estimate the complete test corpus.
Per-category costs, latency, UID-set scores, execution coverage and redlines are
in phase4_summary.json. The phase number in that file is 3 because it selects the
phase-3 hybrid tool set; phase 4 is engineering, not a new tool set.

The final Document fulltext source/URL metadata correction was checked separately
after the repeated measurement; the archived measurements are not rewritten.
Phase-3 text results are retained, and no new phase-4 text-accuracy score is claimed.

## Known issues and deviations

Docker is absent on this machine, as anticipated by the task. No runtime was
installed and no Docker image was pulled. Static YAML inspection is not docker
compose config, a successful image build or a running deployment. CI contains
those checks but has not run remotely. No Phoenix installation, external receiver
or telemetry upload was added. Dependency ranges are bounded; current versions
are recorded in delivery_summary.json, but this is not a cross-platform lockfile.

All full-corpus/sampling/drafting/extraction limitations in phases 2–3 remain.
Only 24 structured paraphrases and 19 grounding-checked LLM text drafts completed;
fallback wording is declared. Frozen lexical tests are not a comprehensive test
of the later FDA brand-alias enrichment. No source, model or credential changed.
Budget and failure charges are recorded persistently below the 15-million cap.
Regular-expression safety/language checks and known-entity verification remain
incomplete; medical/factual correctness requires human review.

Human work is generated and pending: 100 sentence claims (uncalibrated judge),
30 extraction assertions, and all 80 draft text questions. Nothing is silently
approved. See eval/human_labels/README.md and the final summary.

## Final local state

Code, dependencies, models, raw snapshots and generated outputs remain in the
existing E-drive repository. The original stopped database dump remains at
E:\medical project\backups\neo4j-zh-v2.dump. The local zh-v2 tag is retained.
Only local phase commits were made; no push, tag deletion or history rewrite.
The task's temporary API and Neo4j processes are stopped before final handoff;
process identity, shutdown method and closed-port checks are recorded in the
cleanup_summary.json. Neo4j received a console CTRL_C; its native logs confirm
shutdown checkpoints for both databases and Stopped at 2026-10-05 07:41:41 UTC.
Ports 8000, 7474 and 7687 are closed. No persistent service or autostart is added.
