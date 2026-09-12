English | [简体中文](NOTICE.zh-CN.md)

# Data provenance, licensing, and limits of use

## Medical-use restrictions

**This project is for learning, research, and technical demonstration. It does not provide diagnoses, prescriptions, or personalised treatment advice.**

Answers are produced from retrieved records and a language model. Symptom associations are not diagnoses; medication and food associations are not recommendations for an individual. The medical data has not undergone clinical review by this project and may contain errors, omissions, or outdated information.

`app/safety.py` contains rules for crisis expressions, emergency descriptions, dosage requests, and related categories. Fixed notices and generation constraints cover some expressions, but detection can miss risks or raise false alarms, and models may ignore instructions. These measures cannot replace clinicians, clinical triage, or human content review.

Consult a clinician about health concerns. In an emergency, contact local emergency services (**120** in mainland China). If you are thinking about harming yourself, contact someone you trust or professional support. Mainland China's national mental-health assistance number is [12356](https://www.nhc.gov.cn/yzygj/c100068/202412/49a1a65386cd4be582d4702fd0926ee8.shtml). Elsewhere, [Find A Helpline](https://findahelpline.com) lists local resources.

## Data provenance

`medical.json` was not collected by this project and is not distributed with this repository.

| Item | Source |
|---|---|
| Upstream repository | [liuhuanyong/QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG) |
| Data file | [data/medical.json](https://github.com/liuhuanyong/QASystemOnMedicalKG/blob/master/data/medical.json) |
| Collection script | [prepare_data/data_spider.py](https://github.com/liuhuanyong/QASystemOnMedicalKG/blob/master/prepare_data/data_spider.py), which contains disease-page URLs on `jib.xywy.com` (寻医问药网) |
| Format | One JSON object per line, including a MongoDB identifier in `_id.$oid` |
| Dataset used by this project | 8,808 disease records, about 45 MB |

The upstream collection script identifies a source website, but the data file does not preserve verifiable collection dates, permissions, or clinical-review information for each record. This project has not verified every record against its original page.

### Data-use conditions

The upstream [README](https://github.com/liuhuanyong/QASystemOnMedicalKG/blob/master/README.md) states:

> 本数据请勿商用

This asks users not to use the data commercially. The upstream repository does not list an explicit licence file. That restriction does not establish full permission from the original website or other rights holders to copy or redistribute the content. Check upstream terms and applicable permissions before use. This project's MIT licence does not apply to the dataset.

This repository provides a loader and an upstream download location, not the raw dataset. Evaluation archives contain some model output and retrieved excerpts that may reflect upstream content; their inclusion should not be read as a separate grant of rights over that content. Rights holders may contact the maintainer through a repository issue. Do not put personal health information in public issues.

### Obtaining the data

```powershell
curl.exe -L -o medical.json https://raw.githubusercontent.com/liuhuanyong/QASystemOnMedicalKG/master/data/medical.json
```

Place the file in the repository root, or select its location through `MEDICAL_JSON` or the loader's `--data <path>` argument.

### Data quality

- **Duplicate names:** 胎膜早破 has records with different `_id` values under the same name. Duplicate nodes may exist after import. `python -m app.cli --doctor` checks for duplicates; `python -m scripts.dedupe` reports them without writes by default and modifies the database only with `--apply`.
- **Noisy field semantics:** symptom lists may include disease names or other terms unsuitable as symptoms.
- **Inconsistent formats:** fields such as `cured_prob` may contain percentage strings or free text and cannot uniformly be parsed as numbers.
- **Overlapping relationships:** common-medication and recommended-medication relationships should be interpreted with the descriptions in [schema_notes.json](data/schema_notes.json). These support query planning; they do not validate a medication's effectiveness or suitability.
- **Currency:** records lack reliable individual update dates. Treatment, cost, and insurance fields should not be used as current policy or clinical guidance.

The data, aliases, and intent rules primarily target Chinese. The two documentation languages describe the same system; they do not imply validated English-language medical question answering.

## Model services and privacy

Configuration and keys are read from environment variables or a local `.env` file. `.env` is excluded from version control.

External model calls may send questions, entity names, graph schema, retrieved records, and, on some paths, conversation context to the provider. Data handling depends on the configured service's terms. This project does not provide patient-data de-identification or a healthcare privacy-compliance guarantee. Do not enter identifiable patient records.

Execution traces and evaluation archives may contain questions, generated queries, and answers. Check them for personal information before saving or sharing them. If using a local model endpoint, also review that service's logging and network settings.

## Code and third-party software

Code in this repository is released under the [MIT License](LICENSE). Third-party data, model services, and software retain their own licences or terms.

Python dependencies are listed in [requirements.txt](requirements.txt), with test dependencies in [requirements-dev.txt](requirements-dev.txt). Obtain Neo4j separately from its [official distribution page](https://neo4j.com/deployment-center/). Neither its distribution nor model weights are bundled here.

## Development tools

Claude, ChatGPT, and Codex were used during development.
