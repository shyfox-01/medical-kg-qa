English | [简体中文](NOTICE.zh-CN.md)

# Notice: data provenance, licensing, and limits of use

Three things: **where the data came from**, **what licence applies to what**, and
**what this system must not be used for**. Please read before using or forking.

---

## 1. Medical disclaimer

**This is a technical demonstration, not a medical product. It does not provide
medical advice and it does not diagnose.**

* Every answer comes from a **publicly scraped medical encyclopedia**. That data has
  not been clinically reviewed and contains noise (see "Known data quality issues"
  below).
* The system **does not diagnose**. All it does is look up which symptoms, departments,
  medications or foods a disease is linked to in the graph, and restate what it found.
  Symptom overlap is extremely common in medicine: "diseases associated with these
  symptoms include X" and "you have X" are entirely different statements.
* The system **will not give medication dosages**. A safety layer (`app/safety.py`)
  detects requests for dosing and refuses them, because individual dosing depends on
  body weight, liver and kidney function, concurrent medications and current condition —
  information a knowledge graph does not and cannot contain.
* **If you or someone near you has a health problem, see a doctor.** For chest pain
  with sweating, sudden slurred speech or limb weakness, loss of consciousness, heavy
  bleeding, or difficulty breathing, call emergency services immediately (**120** in
  mainland China) or go to an emergency department. Do not rely on any software.
* If you are having thoughts of harming yourself, please reach out to a person. In
  mainland China: psychological assistance hotline **12356** (nationwide, 24h) or
  **400-161-9995**. Elsewhere: [findahelpline.com](https://findahelpline.com).
  The system short-circuits its entire pipeline when it detects this kind of message
  and returns these resources instead of querying the graph — but please do not treat
  software as the thing you reach out to.

---

## 2. Data provenance

The disease data in `medical.json` **was not collected by this project and is not
redistributed with it**.

| Item | Detail |
|---|---|
| Upstream project | [liuhuanyong/QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG) |
| File | `data/medical.json` in that repository |
| Original source | The upstream author states the data was scraped from a medical vertical portal (widely understood to be xywy.com) |
| Size | 8,808 disease records, MongoDB export format (one JSON object per line, with `_id.$oid`) |
| Fields | `name` `desc` `category` `prevent` `cause` `symptom` `yibao_status` `get_prob` `get_way` `acompany` `cure_department` `cure_way` `cure_lasttime` `cured_prob` `cost_money` `check` `common_drug` `recommand_drug` `drug_detail` `do_eat` `not_eat` `recommand_eat` |

### The upstream author's terms

The upstream README states (original Chinese):

> 本项目的数据，如侵犯相关单位权益，请联系我删除。本数据请勿商用。
>
> *"If this data infringes any party's rights, contact me and I will remove it.
> Do not use this data commercially."*

Accordingly:

* **Non-commercial use only** (study, research, technical demonstration).
* The upstream repository carries **no explicit open-source licence**, so the rights
  status of the data is not clear.
* This repository therefore **does not redistribute `medical.json`**. It provides the
  download location and the loading script only. That respects the upstream author's
  terms and avoids propagating data whose rights status is unclear.
* If the original site or any rights holder considers the use made here inappropriate,
  please open an issue and I will cooperate.

### Getting the data

```bash
# Just the one file
curl -L -o medical.json \
  https://raw.githubusercontent.com/liuhuanyong/QASystemOnMedicalKG/master/data/medical.json

# Or clone upstream and copy
git clone https://github.com/liuhuanyong/QASystemOnMedicalKG.git
cp QASystemOnMedicalKG/data/medical.json ./medical.json
```

Put `medical.json` in the repository root; the loader finds it automatically. It can
live elsewhere — pass `--data <path>` or set the `MEDICAL_JSON` environment variable.

### Note on language

The dataset is in Chinese, so node names, relationship values and the answers the
system produces are Chinese. The code, tests and documentation are structured so that
this does not require reading Chinese: relationship type names are ASCII
(`diseaseSymptomRelation` and so on), and the schema is described in English in the
README. Example questions and answers throughout the documentation are given with
enough context to follow without translation.

### Known data quality issues

The data was scraped and has not been cleaned. Before relying on it:

* **Duplicate records under the same name.** 胎膜早破 (premature rupture of membranes)
  appears twice with different `_id`s, producing duplicate nodes and preventing a
  uniqueness constraint on `disease.name`. `python -m app.cli --doctor` reports this;
  `python -m scripts.dedupe` merges them (dry run by default).
* **Non-symptoms in the symptom field.** The symptom list for 感冒 (common cold)
  contains 情绪性感冒, which is actually a disease name.
* **Inconsistent attribute formats.** `cured_prob` (cure rate) is a percentage string
  for most diseases but free text for others — for diabetes it reads
  "manageable with medication, difficult to cure outright". A benchmark case in this
  project once failed because it assumed the field was always a percentage.
* **Overlapping relationship semantics.** `diseaseDrugRelation` (common medications,
  1–2 per disease) and `diseaseRecommendDrugRelation` (recommended list, ~8 per disease)
  are indistinguishable by name alone. `data/schema_notes.json` supplies a curated
  semantic description that is injected into the prompt.

---

## 3. Third-party components

| Component | Purpose | Licence | Bundled? |
|---|---|---|---|
| [Neo4j Community Edition](https://neo4j.com/deployment-center/) 5.26 | Graph database | GPLv3 | **No**, download separately |
| [neo4j Python Driver](https://github.com/neo4j/neo4j-python-driver) | Database driver | Apache-2.0 | No (pip) |
| [openai-python](https://github.com/openai/openai-python) | OpenAI-compatible client | Apache-2.0 | No (pip) |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | Fuzzy matching | MIT | No (pip) |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | Reads .env | BSD-3-Clause | No (pip) |

The LLM endpoint defaults to Zhipu GLM's OpenAI-compatible API, but the project is not
tied to any provider — three lines in `.env` switch it to SiliconFlow, DeepSeek, or a
local Ollama. **This repository contains no API keys.**

---

## 4. Development tooling

AI coding assistants were used during development, including Anthropic's Claude and
OpenAI's ChatGPT / Codex.

Every performance figure in the README was measured against a real Neo4j instance and a
real LLM rather than estimated; per-question raw results are archived in `eval/runs/`
for verification.
