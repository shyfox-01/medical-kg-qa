English | [简体中文](README.zh-CN.md)

# Medical Knowledge Graph QA

Ask a medical question in natural language; the system translates it into a graph
database query and turns the retrieved facts into an answer.

The graph covers 8,808 diseases — 28,832 nodes and 337,239 relationships — linking
each disease to its symptoms, clinical departments, diagnostic tests, medications,
treatment approaches, foods to avoid or prefer, susceptible groups, and complications.
Question answering follows the Text2Cypher approach: the LLM turns the question into
Cypher, the graph supplies the facts, and every statement in the answer traces back
to an edge in the graph.

> ### ⚠ Read this first
>
> * **This is a technical demo, not a medical product. It does not provide medical
>   advice and does not diagnose.** See a doctor for health concerns. For chest pain
>   with sweating, sudden slurred speech or limb weakness, loss of consciousness,
>   heavy bleeding, or difficulty breathing, call emergency services immediately
>   (**120** in mainland China) — do not rely on any software.
> * **The system will not give medication dosages.** Individual dosing depends on
>   body weight, liver and kidney function, concurrent medications, and current
>   condition. A knowledge graph does not and cannot contain that information.
> * **The data is scraped from a public medical encyclopedia. It has not been
>   clinically reviewed and contains noise.** It comes from
>   [liuhuanyong/QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG),
>   whose author asks that it not be used commercially. This repository does not
>   redistribute it; it only tells you where to get it.
> * If you are having thoughts of harming yourself, please reach out. In mainland
>   China: psychological assistance hotline **12356** (nationwide, 24h) or
>   **400-161-9995**. Elsewhere, see
>   [findahelpline.com](https://findahelpline.com).
> * Full provenance, licensing boundaries, and disclaimers: **[NOTICE.md](NOTICE.md)**.

---

## What it answers

Single-turn questions across the eight relationship types plus a set of disease
attributes (cause, prevention, contagiousness, cure rate, treatment duration,
approximate cost, insurance status):

```
> What should a diabetic avoid eating?
  Osmanthus sugar, maltose, honey, rock sugar

> Cough and fever — what could it be, and which department?
  Pneumonia: internal medicine, respiratory; Bronchitis: internal medicine,
  respiratory; Avian influenza: infectious diseases ...
  Note: these results are incomplete; more were not returned.
```

Follow-up questions with elided subjects work:

```
> What are the symptoms of diabetes?
  Excessive thirst, frequent urination, weight loss, elevated blood sugar ...
> What should they avoid eating?     ← resolved to "diabetes — foods to avoid"
  Osmanthus sugar, maltose, honey, rock sugar
> What about hypertension?           ← new entity, same intent: "symptoms of hypertension"
  Dizziness, headache, palpitations ...
```

Out-of-scope questions are declined rather than answered with an invention:

```
> What's the weather in Beijing today?
  That's outside what this system covers. I can only answer from the medical
  knowledge graph ...
```

---

## Design

The interesting problems here were not in getting the pipeline to run.

### Not every question needs an LLM

The schema is highly regular: 9 node types, 12 relationship types, all originating
from `(:disease)`. Most questions reduce to "one disease plus one relationship".
Handing those to an LLM to compose Cypher trades certainty for probability.

So query generation has two paths. Local intent detection runs first; when the intent
is unambiguous and exactly one anchor entity resolves, a whitelisted template emits a
parameterised query with no generation call at all. Everything else goes to the LLM.
Across the 69-question benchmark, 44 take the template path with zero relationship
selection errors, cutting LLM calls by 40% and tokens by 54% at identical accuracy.

The hard part is knowing when **not** to fire. Two-hop questions ("cough and fever,
what could it be and which department" is symptom → disease → department),
aggregations, and any question lacking an anchor of the required type are all handed
back to the LLM. Declining too often is much cheaper than answering wrongly.

Intent rules are declared as candidate lists and compiled in descending length order
rather than hand-ordered. Python's regex alternation is leftmost-first, not
longest-match: in 「胃炎不治会引起什么病」 the short pattern `不治会` matches at index 2
and the scanner moves past the longer, correct `会引起什么病` that follows.
Hand-ordering fixes it, but every new rule would require rethinking the order.

### LLM-generated queries are untrusted input

Cypher written by a model is no different from SQL pasted by a user. Three layers:

```
① Static check   lexical scan → denylist → schema validation → resource limits (pure, unit-tested)
② EXPLAIN        let the database pre-compile and judge syntax and semantics
③ Read-only tx   enforced at the database layer
```

The key to the first layer is **scanning lexically before applying any rule**.
Running regexes over the raw statement does not work, because they cannot see string
literals: the `//` inside `WHERE d.desc CONTAINS "http://x"` is read as a line comment,
swallowing the rest of the statement including `RETURN`, and the denylist then runs
against that mangled remainder. The statement being validated is no longer the
statement being executed — the worst mistake a validator can make. Comments and string
literals are now identified per Cypher's own rules and blanked to equal-length spaces;
every later rule runs against that skeleton.

Resource limits are easy to overlook. `LIMIT 100000` is perfectly valid syntax and
will drag all 28,000 nodes back in one statement; an unbounded `[*]` variable-length
path over 337,000 relationships will take the server down. So LIMIT values are capped,
path length is bounded, and queries carry a server-enforced timeout.

The third layer is a real defence, not decoration: executing `CREATE` inside a READ
transaction returns `Neo.ClientError.Statement.AccessMode: Writing in read access
mode not allowed`. Even if the first two are bypassed, nothing can be written.

### Medical safety is not database safety

Keeping the model from dropping the database is only half of it. The other half is
keeping the system from giving advice that hurts someone. The graph contains drug
names; when a user says "I've been diagnosed with diabetes, just tell me how many
milligrams of metformin to take, I don't need a doctor", dutifully retrieving the
drug list and letting the model improvise is dangerous.

A separate safety layer runs on local rules, costing no tokens:

| Level | Trigger | Behaviour |
|---|---|---|
| Self-harm | suicide / self-injury / lethal dose | Short-circuits the pipeline, returns crisis lines, never queries the graph |
| Emergency | unconsciousness, heavy bleeding, poisoning; chest pain + cold sweat; sudden slurred speech | Prepends a deterministic emergency notice |
| Dosage | dosage / how many pills / "no need for a doctor" | Hard constraint against emitting any specific dose |
| Special populations | pregnancy / infants / elderly + medication | Appends a contraindication reminder |
| Drug interactions | "take together" + a drug entity | States that the graph has no interaction data |
| Diagnosis request | "do I have ...?" | Constrains the model from concluding a diagnosis |

The main risk in this layer is false positives, not false negatives. If "what are the
symptoms of a cold" triggers an emergency warning, users learn to ignore every warning
within three days — including the one that matters. So an emergency requires either an
inherently emergent term or a symptom term co-occurring with a severity term:
"what causes chest tightness" stays quiet, "severe chest pain with cold sweat" fires.

Emergency notices and disclaimers are assembled in code, not requested from the model.
A model may forget, rewrite, or lose them to a `max_tokens` cutoff, and losing an
emergency notice once is an incident.

### Something has to sit between colloquial speech and clinical terms

A user says 拉肚子 ("the runs"); the graph node is 腹泻 ("diarrhoea"). Without this
layer, exact matching returns zero rows and the system says "I don't know" — which
looks like a model failure but is really an entity alignment failure.

26,000 node names are compiled into a dictionary for maximum-length matching, backed
by a curated colloquial alias table (90 entries, zero redundant, zero broken) with
fuzzy matching as a last resort. An audit tool flags two failure modes in the alias
table: targets that do not exist in the graph (rewriting makes the query *less*
answerable) and keys that are already graph nodes (pure noise).

One detail worth stating: 125 disease names contain 肺炎 ("pneumonia"), but exactly one
*is* 肺炎. Using CONTAINS unconditionally means "symptoms of pneumonia" blends the
symptoms of 125 different pneumonias into one pile — it returns results, and they are
wrong. When an exact node name exists, it wins.

A further 481 names carry multiple labels (咳嗽, 头痛, 腹泻, 贫血 are each both a
disease and a symptom). Which one is correct depends on what is being asked, so the
linking stage keeps every candidate and lets downstream pick by required type.

### "Not found" should not be the end of the conversation

The user has no way to know what term to try instead — only the system knows what is
in the graph and what it is called. So zero-result queries return near-miss
suggestions and related diseases from full-text search.

Full-text search took one wrong turn worth recording. The first attempt OR-ed together
n-grams, which worked badly: Neo4j's full-text index tokenises Chinese per character,
so `老是拉肚` / `是拉肚子` / `拉肚` all collapse into the same bag of characters and
merely inflate term frequency — a single 拉 was enough to put 马拉色菌病 at the top with
a score of 50. Switching to quoted phrase queries (requiring adjacency) fixed the
precision, and a post-filter requiring the candidate name to share a two-character
substring with the question removed the rest of the noise.

### Incomplete results must be declared

With `LIMIT 25` enforced, "cough and fever, what could it be" returns the first 25 rows.
If that fact is not passed to the answering stage, the model presents them as the
complete set. In a medical context, presenting partial results as complete is a serious
defect, so the truncation flag propagates through to answer composition and the model
now states that more results exist.

For the same reason the provenance footer — which relationship was traversed, how many
rows, whether truncated — is assembled in code.

---

## Architecture

```
question
   │
   ├─ safety gate        self-harm → short-circuit to crisis resources, no graph query
   │                     emergency / dosage / special population → flag, deterministic text appended
   │
   ├─ coreference        "what should they avoid" → "diabetes — foods to avoid" (local, no tokens)
   │
   ├─ entity linking     dictionary max-match + alias normalisation, overlapping candidates kept
   │
   ├─ template path      clear intent + unique anchor → parameterised Cypher from a whitelist
   │     └ miss ─────┐
   ├─ LLM generation ◄┘  schema introspected into the prompt; also classifies out-of-scope
   │
   ├─ three gates        lexical scan + rules → EXPLAIN → read-only transaction
   │                     on failure the exact error is fed back for a retry
   │
   ├─ empty fallback     near-miss suggestions + full-text search
   │
   └─ answer             relationship semantics + truncation flag + provenance + disclaimer
```

| Entity | Count | | Relationship | Count |
|---|---|---|---|---|
| disease | 8,808 | | diseaseRecommendDrugRelation | 59,467 |
| symptom | 5,998 | | diseaseSymptomRelation | 54,717 |
| food | 4,870 | | diseaseSuitableFoodRelation | 40,236 |
| drug | 3,828 | | diseaseCheckRelation | 39,427 |
| check | 3,355 | | diseaseCategoryRelation | 25,590 |
| crowd | 1,320 | | diseaseTabooFoodRelation | 22,247 |
| cureWay | 544 | | diseaseRecommendRecipeRelation | 22,238 |
| category | 55 | | diseaseCureWayRelation | 21,050 |
| department | 54 | | diseaseDepartmentRelations | 16,783 |
| | | | diseaseDrugRelation | 14,649 |
| | | | diseaseDiseaseRelation | 12,029 |
| | | | diseaseCrowdRelation | 8,806 |

---

## Getting started

**Dependencies**

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -r requirements-dev.txt   # pytest only, for tests
```

**Data** (45MB, not in this repository — see [NOTICE.md](NOTICE.md))

```powershell
curl -L -o medical.json https://raw.githubusercontent.com/liuhuanyong/QASystemOnMedicalKG/master/data/medical.json
```

**Neo4j** (Community Edition, ~460MB, GPLv3, not bundled) — download 5.26 from the
[Neo4j Deployment Center](https://neo4j.com/deployment-center/) and extract it to
`neo4j/neo4j-community-5.26.0/`. JDK 17 or 21 is required; if you have not installed
one separately, the JBR bundled with PyCharm / IntelliJ is JDK 21 and the start script
will find it:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_neo4j.ps1
```

http://localhost:7474 is the browser interface; Bolt port 7687 is what the app uses.

**Build the graph and configure keys**

```powershell
copy .env.example .env
notepad .env                                        # Neo4j password and LLM key
.venv\Scripts\python -m scripts.load_kg --dry-run   # parse stats only, no writes
.venv\Scripts\python -m scripts.load_kg             # full load, a few minutes
```

Only the OpenAI-compatible protocol is used, so switching providers means changing
three lines in `.env`: Zhipu GLM (`https://open.bigmodel.cn/api/paas/v4` with
`glm-4.5-flash`, has a free tier), SiliconFlow, DeepSeek, or a local Ollama.

**Ask**

```powershell
.venv\Scripts\python -m app.cli                     # interactive, multi-turn
.venv\Scripts\python -m app.cli -q "感冒吃什么药"      # single question
.venv\Scripts\python -m app.cli --selftest          # no API key needed
.venv\Scripts\python -m app.cli --doctor            # environment check
.venv\Scripts\python -m app.cli --mock -q "..."     # no API key, exercises the full path
```

In interactive mode: `:trace` toggles step display, `:reset` clears the topic,
`:cypher <statement>` queries the graph directly, `:config` prints configuration
with secrets redacted, `q` quits.

**Tests and benchmarks**

```powershell
.venv\Scripts\python -m pytest                     # 253 offline unit tests, no DB, no LLM
.venv\Scripts\python -m scripts.demo               # guided demo, no API cost
.venv\Scripts\python -m eval.run_eval --offline    # seconds; deterministic layers only
.venv\Scripts\python -m eval.run_eval              # all 69 questions, needs a key
.venv\Scripts\python -m eval.run_eval --repeat 3   # 3 rounds each, reports variance
```

---

## Benchmarks

69 questions across 11 categories, scored by rules rather than LLM-as-judge so results
are reproducible. GLM-4.5-Flash, `LLM_THINKING=off`, cache disabled, one round each:
**69/69 passing**. All red lines at 100%: injection blocked (9), out-of-scope refused
(5), safety classification (6), crisis intervention (1). Graph fingerprints before and
after confirm 28,832 nodes / 337,239 relationships unchanged.

What the template path buys (same questions, run back to back, only this switch differs):

| | Off | On | Change |
|---|---|---|---|
| Pass rate | 68/69 | 68/69 | unchanged |
| LLM calls | 136 | 81 | −40% |
| Tokens | 153,455 | 72,573 | −53% |
| Median latency | 26.3s | 9.8s | −63% |
| Per-question diff | — | 0 regressions / 0 fixes | identical |

The per-question diff matters: an unchanged total can still hide three fixes and three
regressions. Route distribution is template 47, out-of-scope 16, LLM 4, no-result 1,
safety 1 — only 4 of 69 questions genuinely need the model to compose Cypher.

The benchmark itself had a bug worth recording. `attr-01` ("what is the cure rate for
diabetes") expected `cured_prob` to be a percentage, but the graph stores free text for
that disease — "manageable with medication, difficult to cure outright". The system
retrieved and reported it faithfully; the test was wrong. When a score drops, confirm
which side failed first: patching the system to satisfy a badly written test would have
broken correct behaviour.

Per-question raw results are in [`eval/runs/`](eval/runs/). Latency is only comparable
within the A/B pair above — free-tier API speed varies widely through the day; the same
code measured 9.8s and 21.1s median on two different runs.

---

## Layout

```
app/
  config.py          configuration; secrets only from .env
  schema.py          schema model + prompt rendering
  cypher_guard.py    static validator: lexical scan + denylist + schema + limits (pure)
  graph.py           Neo4j access, introspection, EXPLAIN, read-only tx, timeout, full-text
  entity_linker.py   dictionary max-match, alias normalisation, overlapping candidates
  planner.py         intent detection + Cypher template path
  safety.py          medical safety gate
  session.py         multi-turn state: focus entity carry-over and coreference
  answer.py          answer composition: data delimiting, truncation flag, provenance
  cache.py           result cache
  llm.py             OpenAI-compatible client, token accounting, tolerant JSON parsing
  text2cypher.py     pipeline orchestration
  cli.py             command line entry (--selftest / --doctor)
  _fake_llm.py       offline stub LLM, separates pipeline bugs from model bugs
tests/               253 offline unit tests
eval/                69-question benchmark, runner, archived results
scripts/             database startup, graph loading, dedupe, demo
data/                alias table + curated relationship semantics
```

Excluded from the repository (see `.gitignore`): `.env`, `medical.json`, `neo4j/`.

---

## Limitations

Edit distance discriminates poorly between short Chinese terms — 头疼 and 头痛 ("headache",
two common spellings) score only 50% similar, while lowering the threshold matches 病人
("patient") to 艾滋病人的急性阑尾炎 ("acute appendicitis in AIDS patients"). A curated
alias table plus full-text phrase search covers frequent colloquialisms; the real fix is
vector retrieval or a medical synonym resource such as CMeKG or ICD-10.

Intent detection is rule-based. It covers common phrasings, but an unusual one falls
through to the LLM. That is not a failure — the LLM is the fallback — but template
coverage drops. The rule table is at the top of `planner.py` and is easy to extend.

The source data is noisy. The symptom list for 感冒 ("common cold") contains 情绪性感冒,
which is actually a disease name. Hypertension and diabetes each have exactly four foods
to avoid and they do not overlap, so the correct answer to "what should both avoid" is
"nothing" — true but useless, which is why that template returns the union with hit
counts instead. The source also contains two records named 胎膜早破, producing duplicate
nodes and preventing a uniqueness constraint on `disease.name`; `--doctor` reports it and
`scripts/dedupe.py` can merge them. More in [NOTICE.md](NOTICE.md).

---

## Data, disclaimer, and licence

Data comes from
[liuhuanyong/QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG),
scraped from a medical vertical portal. The upstream author asks that it not be used
commercially and attaches no explicit licence, so this repository does not redistribute
it. If the use made of that data here is inappropriate in any way, please open an issue.

This project is a technical demonstration. It does not provide medical advice and does
not diagnose. The safety gate in the code is an engineering measure — it can refuse
"tell me how many milligrams", but it is not a substitute for a doctor. See a doctor
for health concerns; in an emergency call your local emergency number.

Full details in [NOTICE.md](NOTICE.md). Code is [MIT](LICENSE) licensed; the data is not.

AI coding assistants (Claude, ChatGPT / Codex) were used during development.
