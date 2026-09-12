English | [简体中文](README.zh-CN.md)

# Medical Knowledge Graph QA

Query disease-related knowledge in Chinese using natural language. The system stores diseases, symptoms, medications, tests, and clinical departments in Neo4j, generates Cypher through parameterised templates or an LLM, and composes an answer from the retrieved results.

The project explores how natural-language answers can have inspectable supporting data. The graph supplies entities, relationships, and properties; the language model interprets questions and presents results. Queries, returned records, and execution traces are available for inspection. This follows the Text2Cypher approach to graph-based retrieval and question answering (GraphRAG).

The dataset contains 8,808 disease records. The graph used for the archived evaluation has 9 node types and 12 relationship types, with 28,832 nodes and 337,239 relationships. Counts depend on the imported data and deduplication.

> ### ⚠ Read before use
>
> * **This project is for learning, research, and technical demonstration. It does not provide diagnoses, prescriptions, or personalised treatment advice.** Consult a clinician about health concerns. In an emergency, contact local emergency services (**120** in mainland China).
> * **Do not use its output to choose medication or dosage.** Dosage-request detection and safety notices are included, but both rules and models can miss risks or produce errors. They cannot replace professional assessment.
> * **The medical data has not undergone clinical review by this project and may contain errors, omissions, and outdated information.** It comes from [QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG), whose author asks that it not be used commercially. The raw dataset is not distributed here.
> * If you are thinking about harming yourself, contact someone you trust or professional support. In mainland China, the national mental-health assistance number is [12356](https://www.nhc.gov.cn/yzygj/c100068/202412/49a1a65386cd4be582d4702fd0926ee8.shtml). For immediate danger, contact emergency services.
> * See [NOTICE.md](NOTICE.md) for provenance, restrictions, and privacy information.

## Features

| Query subject | Example |
|---|---|
| Disease–symptom associations | Symptoms of pneumonia; diseases associated with cough and fever |
| Departments and tests | Departments linked to hypertension; tests recorded for pneumonia |
| Medication and treatment records | Common medications recorded for diabetes; treatment approaches for gastritis |
| Diet, susceptible groups, complications | Foods-to-avoid records for diabetes; groups associated with hypertension |
| Disease properties | Cause, prevention, contagiousness, treatment duration, cost, and other fields |
| Comparisons, counts, multi-hop queries | Shared associations between diseases; disease counts for a department |

Multi-turn questions can carry forward the disease or query intent. This example shows question interpretation, not medical answers:

```text
Q: 糖尿病有什么症状？  (What are the symptoms of diabetes?)
Interpretation: look up symptoms of diabetes.

Q: 那忌口什么？        (What foods should be avoided?)
Interpretation: look up foods-to-avoid records for diabetes.

Q: 高血压呢？          (What about hypertension?)
Interpretation: look up foods-to-avoid records for hypertension,
                carrying forward the preceding intent.
```

Empty results can trigger approximate entity suggestions and full-text candidates. These indicate retrieval relevance, not diagnostic probability. The pipeline also has a refusal path for questions outside the graph's scope.

## How it works

```text
Chinese question
  → local medical-safety rules
  → multi-turn reference resolution and result cache
  → entity linking: dictionary, aliases, fuzzy candidates
  → query generation: intent template / LLM + graph schema
  → static validation → EXPLAIN → read-only transaction
  → candidate search for empty results
  → answer composition with retrieval source and safety notices
```

### Data model and entity linking

The loader stores scalar fields such as disease descriptions, causes, and prevention as properties. List fields for symptoms, medications, tests, and departments become nodes and relationships. Entities are merged by name, using parameterised queries and batch loading.

Entity linking maps colloquial expressions such as 拉肚子 to graph names. Exact names take priority; candidates with multiple labels are retained for query planning. Relationship and property descriptions are maintained in [data/schema_notes.json](data/schema_notes.json).

### Query planning

Requests recognised by local intent rules use whitelisted Cypher templates. These cover common relationship queries, some counts, and disease comparisons. Other requests go to the LLM with the graph schema and entity candidates. An empty template result may also lead to the LLM path.

Templates save the model call used to generate a query; answer composition still uses a model when records are retrieved. The client uses an OpenAI-compatible API, with the endpoint, model, and key configured in `.env`.

### Query and answer constraints

Generated Cypher passes lexical scanning, operation restrictions, and schema checks before Neo4j `EXPLAIN` pre-compilation. Execution uses read-only transactions with configurable timeouts, row limits, and variable-length path bounds.

The answering prompt requires grounding in retrieved records. Code appends retrieval provenance, row counts, and a disclaimer. When the returned row count reaches the limit, results are marked as potentially incomplete. These details help inspect an answer's basis; they are not sentence-level fact verification and cannot guarantee the absence of hallucinations.

Medical-safety rules detect self-harm expressions, emergency descriptions, dosage requests, medication questions involving special populations, and requests for diagnosis. Detected self-harm expressions return support resources directly. Other categories use generation constraints or fixed notices. This rule layer is not a clinical triage tool.

## Getting started

You need Python, Neo4j, and a model service with an OpenAI-compatible API. Development and tests use Python 3.12. The commands below target Windows PowerShell.

### 1. Install Python dependencies

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

### 2. Obtain the data

Read the [data-use notice](NOTICE.md), then obtain `medical.json` from upstream (about 45 MB):

```powershell
curl.exe -L -o medical.json https://raw.githubusercontent.com/liuhuanyong/QASystemOnMedicalKG/master/data/medical.json
```

Place it in the repository root, or set `MEDICAL_JSON` or the loader's `--data` argument to another location.

### 3. Start Neo4j

Download Community Edition 5.26 from the [Neo4j Deployment Center](https://neo4j.com/deployment-center/) and extract it to `neo4j/neo4j-community-5.26.0/`. This series supports [Java 17 or 21](https://neo4j.com/docs/operations-manual/current/installation/requirements/). Set `JAVA_HOME` before using the startup script.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_neo4j.ps1
```

The Neo4j browser is at `http://localhost:7474`; the app connects through Bolt on port `7687`. Set the database password in Neo4j on first startup.

### 4. Configure and load the graph

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in `NEO4J_PASSWORD`, `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY`. Model calls may incur charges under your provider's terms.

```powershell
.venv\Scripts\python -m scripts.load_kg --dry-run
.venv\Scripts\python -m scripts.load_kg
```

`--dry-run` parses the data only. The second command writes to the configured database.

### 5. Ask a question

```powershell
.venv\Scripts\python -m app.cli
.venv\Scripts\python -m app.cli -q "肺炎有哪些症状"
.venv\Scripts\python -m app.cli --doctor
```

Interactive commands: `:trace` shows execution steps, `:reset` clears the conversation, `:cypher <statement>` queries the graph directly, `:config` shows redacted configuration, `:cache` shows cache statistics, and `q` exits.

The repository does not distribute `.env`, the raw dataset, Neo4j, or a virtual environment. External model calls may send questions and retrieved content to the provider. Do not enter identifiable patient records.

## Tests and evaluation

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m app.cli --selftest
.venv\Scripts\python -m scripts.demo
.venv\Scripts\python -m eval.run_eval --offline
.venv\Scripts\python -m eval.run_eval
.venv\Scripts\python -m eval.run_eval --repeat 3
```

- `pytest`: 253 unit tests, with no database or model service required.
- `--selftest`, `scripts.demo`, and `--offline`: require Neo4j but make no real LLM calls.
- Full evaluation: requires Neo4j and a model service. The 69 Chinese questions cover 11 categories, including retrieval, multi-turn questions, scope handling, injection attempts, and medical safety.

The [archived evaluation](eval/runs/v2_final.json) uses GLM-4.5-Flash, `LLM_THINKING=off`, and a disabled cache:

| Metric | Archived result |
|---|---|
| Passed under the evaluation rules | 69 / 69 |
| LLM calls | 81 |
| Total input and output tokens | 71,312 |
| Final answer routes | Template 47, LLM 4, out of scope 16, no result 1, safety response 1 |

This is one internal run on a fixed question set. It does not establish medical accuracy, clinical effectiveness, or safety for arbitrary inputs. Scoring primarily checks query execution, relationship selection, keywords, and expected safety responses; it does not replace expert review of complete answers. Generated output and latency vary with the model and service.

Use `--no-fast-path` for template-switch experiments, `--save` to record results, and `--baseline` to compare a selected archive. Comparisons require matching question sets, scoring rules, and model settings. Before-and-after node and relationship counts measure count changes only; they do not prove that all property values are unchanged.

## Layout

```text
app/       Entity linking, planning, database access, safety rules, answers, CLI
data/      Aliases and relationship descriptions
scripts/   Data loading, Neo4j startup, duplicate handling, demonstration
tests/     Unit tests
eval/      Question set, evaluation runner, result archives
```

## Limitations

- The data and local rules primarily target Chinese. English documentation does not imply validated English-language question answering.
- Aliases, fuzzy matching, and intent rules have limited coverage. Entity ambiguity and abbreviated follow-ups can be misinterpreted.
- Source data includes duplicate names, inconsistent formats, and questionable medical associations. Cost and medication information may be outdated.
- Finding no shared association describes this dataset's retrieval result; it does not establish the absence of a medical association.
- Row limits do not check completeness of every returned value. Aggregated lists or text may also be incomplete.
- Medical-safety rules and query validation have coverage limits. Passing tests does not establish suitability for clinical or unsupervised use.

## Sources, licence, and tools

Disease data comes from [liuhuanyong/QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG). Code is released under the [MIT License](LICENSE), which does not cover third-party medical data. See [NOTICE.md](NOTICE.md) for provenance and restrictions.

Claude, ChatGPT, and Codex were used during development.
