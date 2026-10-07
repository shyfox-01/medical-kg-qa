# English Medical GraphRAG

An English research demo combining a bounded medical graph, public health
summaries and drug-label evidence. CLI, FastAPI, verified-answer SSE, independent
evaluation and OpenTelemetry are included. **Not medical advice or a clinically
validated system.** The Chinese implementation is preserved by the local `zh-v2` tag.

```mermaid
flowchart LR
  CSV[PrimeKG + MONDO/HPO] --> KG[(Neo4j)]
  Text[MedlinePlus + openFDA] --> Chunks[Sections + bge-small vectors]
  Chunks --> KG
  Q[Question + history] --> Safety[Safety + entity linking]
  Safety --> Plan[Templates or bounded JSON plan]
  Plan --> Tools[Guarded Cypher / vector / fulltext / expansion]
  KG --> Tools
  Tools --> Answer[Evidence-only generation + entity verification]
  Answer --> Output[Code citations + conflicts + CLI / HTTP / SSE]
  Plan --> Trace[OpenTelemetry: JSONL or OTLP]
  Answer --> Trace
```

See [architecture](docs/architecture.md), [decisions](docs/decisions.md) and
[measured results](docs/reports/summary.md).

## Quick start

Requires Python 3.12 and Neo4j Community 5.26 with JDK 21. Use a project environment.
The existing checkout is `E:\medical project\medical-kg-qa`; keep data and caches
inside it. Normal use of the delivered checkout does not require another import.

```powershell
cd 'E:\medical project\medical-kg-qa'
# Create only if .venv is absent:
py -3.12 -m venv .venv
$env:TEMP = Join-Path (Get-Location) '.cache\temp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path (Get-Location) '.cache\pip'
$env:HF_HOME = Join-Path (Get-Location) '.cache\huggingface'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
```

Configure the variables in `.env.example` in an ignored `.env`. Settings check the
repository, then its parent `.env`, without overriding environment variables.
Reuse your OpenAI-compatible endpoint/model; thinking stays disabled. `JUDGE_MODEL`
defaults to `LLM_MODEL`. Never commit credentials.

Start the existing Windows Neo4j installation in another terminal:

```powershell
# Specify another JDK 21 path if needed; no global PATH change:
.\scripts\start_neo4j.ps1 -JavaHome 'D:\PyCharm 2025.2\jbr'
```

For a **fresh, dedicated database**, import in this order. Downloaders cache raw
snapshots. CSV processing and CPU embeddings can take tens of minutes or longer;
check available disk space first. Do not run the importer against unrelated data.

```powershell
.\.venv\Scripts\python.exe -m scripts.download_structured
.\.venv\Scripts\python.exe -m scripts.load_primekg
.\.venv\Scripts\python.exe -m scripts.embed_entities
.\.venv\Scripts\python.exe -m scripts.download_text
.\.venv\Scripts\python.exe -m scripts.load_text --openfda-limit 500
.\.venv\Scripts\python.exe -m eval.biored --limit 12
.\.venv\Scripts\python.exe -m scripts.extract_openfda --limit 80
.\.venv\Scripts\python.exe -m scripts.embed_entities
.\.venv\Scripts\python.exe -m scripts.build_vector_corpus --threads 2
```

The openFDA request ledger caps the whole task at 500, including failed requests.
A cached import does not authorize another 500. Extraction links existing entities
only and creates a review queue. Recorded snapshots/hashes define the reported run;
new upstream versions may change counts.

```powershell
.\.venv\Scripts\python.exe -m medkg.cli 'Which genes are associated with asthma?' --json
.\.venv\Scripts\python.exe -m uvicorn medkg.api.app:app --host 127.0.0.1 --port 8000
```

POST `/ask` accepts `{"question":"Which genes are associated with asthma?","history":[]}`.
POST `/ask/stream` accepts the same body and emits `status`, verified final `answer`
chunks, then `result` events. GET `/health` checks liveness; GET `/ready` checks graph
connectivity and LLM configuration without a provider call. Readiness does not
establish provider availability. History is limited to four turns.

Compose defines `neo4j:5.26-community` and app, with health checks and loopback
published ports. `docker compose up --build` requires Docker and pulls images;
no image was pulled in this task. Its new Neo4j volume needs an explicit import.
Linux bind mounts must permit container uid 10001 to write caches and logs.

## Evaluation and checks

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pytest -m 'not integration'
$env:MEDKG_INTEGRATION='1'
$env:MEDKG_REAL_COUNTS='1'
.\.venv\Scripts\python.exe -m pytest -m integration
# Generate local CSV gold only if absent; preserve the frozen MANIFEST:
.\.venv\Scripts\python.exe -m eval.generate --paraphrase-limit 24
# Use dev while changing rules/prompts:
.\.venv\Scripts\python.exe -m eval.run --split dev --phase 3 --max-per-category 3
# Three-round fixed-sample gate after development:
.\.venv\Scripts\python.exe -m eval.run --split test --rounds 3 --phase 3 --max-per-category 3 --output eval/runs/recheck_summary.json --baseline eval/runs/v1_summary.json --fail-on-redline-regression
```

Evaluation calls the public process boundary; `eval/` does not import QA internals.
Gold comes from CSV. Raw/derived datasets, per-question records and human queues
are ignored. Public text drafts, MANIFEST and aggregates are committed. CI uses a
fictional fixture graph and FakeLLM with no real LLM or embedding-model download.
The default synthetic loader requires an empty/fixture-only database.

## Measured outcomes

The latest frozen capability comparison uses repaired cached data, the same
provider/model and cache off. Each system answered all 240 structured test cases
once, plus three rounds on 70 fixed cases. The saved answers are scored offline
with the corrected `deterministic-3.4` evaluator (D047; zero new model calls).

| System | 240 cases, one round | 70 cases, three-round mean | Round std |
|---|---:|---:|---:|
| Exact pre-capability phase-3 hybrid | 60.00% | 73.33% | 1.35 pp |
| Improved phase-3 hybrid | **87.50%** | **92.38%** | 1.35 pp |
| Improved-code pure vector | 56.67% | 75.24% | 1.78 pp |

| Category (240-case round) | Questions | Before | Improved hybrid | Pure vector |
|---|---:|---:|---:|---:|
| single_hop | 42 | 78.57% | 90.48% | 69.05% |
| reverse | 27 | 40.74% | 85.19% | 59.26% |
| multi_constraint | 27 | 7.41% | 85.19% | 18.52% |
| multi_hop | 36 | 19.44% | 66.67% | 13.89% |
| aggregation | 21 | 85.71% | 100.00% | 71.43% |
| lexical_variation | 27 | 59.26% | 88.89% | 48.15% |
| multi_turn | 12 | 75.00% | 83.33% | 83.33% |
| out_of_scope | 18 | 100.00% | 100.00% | 88.89% |
| adversarial | 15 | 100.00% | 93.33% | 80.00% |
| safety | 15 | 100.00% | 100.00% | 100.00% |

Only aggregation differs from the originally reported `deterministic-3.3` scores
(58.75% / 85.83% / 52.92%; 71.90% / 90.95% / 73.81%): that parser rejected correct
"Count: N" answers whenever another number appeared. These answers predate the
D047 code fixes, which need a new real-provider run to measure. The benchmark only
samples entities with at most 15 neighbors and ontology synonyms, so these rates
do not cover common drugs, brand names or lay wording (see D047). Rescored
summaries are `eval/runs/improvement_{full,repeat,balanced}_*_rescored_v34_summary.json`.

The repeated subset is safety-heavy (30/70 redline cases). These rates do not
establish clinical efficacy. The measured capability snapshot has one hybrid
timeout regression and three vector refusal regressions. Later scope/mutex
maintenance receives separate final-code checks: 213 unit tests, 15 native
integration tests, FakeLLM 13 cases in three rounds, and 30 safety/adversarial
cases in three fresh hybrid rounds with no regression. Some refusals still depend
on the provider. Final vector revalidation retains one refusal regression.
See the [implementation report](docs/reports/improvement-2026-10-06.md) for exact
source fingerprints, failed historical gates, recovery and interpretation limits.

The following tables archive the original staged implementation.

These are sampled results, not full-test estimates. All models use the same 54/240
structured test questions, three rounds and cache off. The sample overweights
safety/adversarial cases: all 30 such cases, three per other category.

| Archived stage/model | Mean pass | Population std | Redline regressions |
|---|---:|---:|---:|
| Phase 2: v0 structured | 74.07% | 1.51 pp | Baseline |
| Phase 3: v1 hybrid | 70.37% | 0.00 pp | 0 |
| Phase 3: pure vector | 38.89% | 0.00 pp | 13; gate exit 1 |
| Phase 4: hybrid delivery | 70.99% | 0.87 pp | 0 against v1 |

**Archived v1 did not improve the overall sampled structured score over v0.** The vector
control fails the redline gate and is not an approved fallback. The baseline already
has one failing adversarial case; a no-regression gate does not mean every attack
passes. Engineering changes are measured separately in [phase 4](docs/reports/phase-4.md).

Text measurements use the same 8/48 draft test questions, three rounds: hybrid
12.50% (std 0.00 pp), vector 45.83% (std 5.89 pp). Strict quote coverage can reject
correct paraphrases. These unreviewed, small-sample scores are exploratory.
BioRED uses 12 sampled test abstracts: pair F1 0.3467, native typed F1 0.1067.
FDA extraction produced 45 assertions from 80/592 eligible chunks, with 75.56%
PrimeKG agreement; agreement is not medical truth.

The [corrective review report](docs/reports/fix-2026-10-05.md) records subsequent
repairs and validation. Historical scores above remain archived measurements.
Versioned `*_rescored_v2_summary.json` files rejudge saved answers using corrected
scoring/catalog data; they are not new runs of the repaired QA system. Legacy
multi-turn costs remain incomplete. The cached repair retains 27 extracted
assertions and quarantines 18 for human review, without new model calls or downloads.

The [ordered follow-up report](docs/reports/followup-2026-10-06.md) records the next
eight correctness fixes, 143 passing unit tests, 13 passing native integration
tests and a new real-provider pilot (38 fixed test IDs, three rounds per system).
Composite quality means are 92.98% for current-code phase-1 control, 94.74% for
hybrid and 80.70% for vector. Hybrid has no redline regression; vector has four.
The pilot is safety-heavy, uses a newer evaluator and does not establish overall
improvement over historical v0. Human review remains pending.

The [capability implementation report](docs/reports/improvement-2026-10-06.md)
records the subsequent planning, routing, lexical and conversation improvements,
213 passing unit tests, 15 passing native integration tests and the frozen
before/after/vector experiment (240 cases once; 70 common cases in three rounds).
Human blind decisions now have a validated import
command; labels and medical validation still require independent human review.

## Data licensing

| Source | Rights/use boundary |
|---|---|
| PrimeKG | Source-specific licenses, including DrugBank commercial restrictions; no descriptions or derived data distributed |
| MONDO | CC BY 4.0; attribution required |
| HPO | HPO attribution/integrity terms; version-specific conditions in NOTICE |
| MedlinePlus | NLM-authored summaries are public domain; linked third-party material excluded |
| openFDA | Government/CC0 terms include private-party copyright exceptions; labels stay local |
| MeSH (NLM) | Free with attribution; drug brand/synonym and lay disease aliases, not distributed |
| DrugBank Vocabulary | Optional CC0 synonyms, manual download only |
| BioRED | Research benchmark; original abstract rights remain; local diagnostic only |
| bge-small-en-v1.5 | MIT model license; weights not distributed |

See [NOTICE](NOTICE.md) for official links and conditions. The software license
does not grant rights to upstream medical data.

## Limits and human review

The corpus has 400 structured questions (160 dev / 240 test), but only 24 were
LLM-paraphrased; others use declared template/authored wording. Text drafts are
40 text-only and 40 mixed. Only 19 passed the bounded LLM drafting/grounding step;
fallbacks are disclosed. All 80 remain `draft`.

Review 100 sentence claims in `eval/human_labels/judge_calibration_todo.jsonl`,
30 assertions in `eval/human_labels/extraction_review_todo.jsonl`, and all 80 text
drafts. The [review guide](eval/human_labels/README.md) explains annotation and
agreement calculation. Judge labels remain **uncalibrated** until human comparison.
Also review the 18 quarantined legacy assertions in
`eval/human_labels/extraction_repair_review_todo.jsonl`; these are absent from the
current graph. Original queues remain historical review artifacts.

Known-entity verification does not prove sentence truth. Language and output-safety
gates are conservative regex rules, not complete classifiers. ANN filtering,
two-hop/row/evidence bounds and the 512-token embedding window limit recall. The
pure-vector corpus includes all 42,975 entity paragraphs and 4,693 chunks; long
paragraphs are embedded by their prefix. No result establishes clinical usefulness
or production security. Docker build, remote CI and Phoenix were not exercised locally.

Default SDK spans write metadata-only `runs/traces/*.jsonl`. Optional OTLP HTTP
and Phoenix viewing are documented in [architecture](docs/architecture.md).
Question/evidence content and credentials are excluded from telemetry.

**Do not use this demo to diagnose, prescribe, choose doses or make treatment
decisions. Seek a qualified clinician for individual medical care.**
