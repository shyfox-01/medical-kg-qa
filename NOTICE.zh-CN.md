[English](NOTICE.md) | 简体中文

# 声明：数据来源、许可与使用限制

这份文件说明三件事：**数据是哪来的**、**代码和数据分别按什么许可**、
以及**这个系统不能拿来做什么**。请在使用或 fork 之前读完。

---

## 一、医疗免责声明

**本项目是一个技术演示，不是医疗产品，不构成任何诊疗建议。**

* 系统的全部回答都来自一份**公开爬取的医疗百科数据**，这份数据没有经过
  临床审核，本身就含有噪声（详见下面「数据质量」一节）。
* 系统**不做诊断**。它能做的只是"在图谱里查到某个疾病关联了哪些症状 / 科室 /
  药物 / 食物"，并把查到的结果复述出来。症状重叠在医学上极其常见，
  "有这些症状的疾病包括 X" 和 "你得了 X" 是两件完全不同的事。
* 系统**不会给出用药剂量**。代码里有一层安全闸（`app/safety.py`）会识别
  索取剂量的提问并硬性拒答 —— 因为个体化剂量取决于体重、肝肾功能、
  合并用药和当前病情，知识图谱里没有、也不可能有这些信息。
* **如果你或你身边的人正在经历健康问题，请就医。** 出现胸痛伴大汗、
  突发言语不清或肢体无力、意识丧失、大出血、呼吸困难等情况，
  请立即拨打 **120** 或前往急诊，不要依赖任何软件。
* 如果你有伤害自己的念头，请联系 **心理援助热线 12356**（全国，24 小时）或
  **希望 24 热线 400-161-9995**。系统识别到这类表达时会直接短路整条问答链路、
  给出求助渠道，而不是去查知识图谱 —— 但请不要把软件当成求助对象。

---

## 二、数据来源

本项目使用的疾病知识数据 `medical.json` **不是本项目采集的，也不随本仓库分发**。

| 项 | 内容 |
|---|---|
| 上游项目 | [liuhuanyong/QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG) |
| 文件位置 | 该仓库的 `data/medical.json` |
| 原始来源 | 上游项目自述数据采集自**医疗垂直网站**（社区普遍认为是寻医问药网 xywy.com） |
| 规模 | 8,808 条疾病记录，MongoDB 导出格式（每行一个 JSON 对象，含 `_id.$oid`） |
| 字段 | `name` `desc` `category` `prevent` `cause` `symptom` `yibao_status` `get_prob` `get_way` `acompany` `cure_department` `cure_way` `cure_lasttime` `cured_prob` `cost_money` `check` `common_drug` `recommand_drug` `drug_detail` `do_eat` `not_eat` `recommand_eat` |

### 上游的使用声明

上游仓库在 README 中明确写明（原文）：

> 本项目的数据，如侵犯相关单位权益，请联系我删除。本数据请勿商用。

因此：

* **本数据仅限非商业用途**（学习、研究、技术演示）。
* 上游仓库**没有附加明确的开源许可证**，数据的权利状态并不清晰。
* 本仓库据此**不转载 `medical.json`**，只提供获取方式和加载脚本。
  这既是尊重上游的声明，也避免把一份权利状态不明的数据再扩散一层。
* 如果原始网站或相关权利方认为本项目的使用方式不当，请提 issue，我会配合处理。

### 怎么拿到数据

```bash
# 方式一：只下这一个文件
curl -L -o medical.json \
  https://raw.githubusercontent.com/liuhuanyong/QASystemOnMedicalKG/master/data/medical.json

# 方式二：克隆上游仓库后复制
git clone https://github.com/liuhuanyong/QASystemOnMedicalKG.git
cp QASystemOnMedicalKG/data/medical.json ./medical.json
```

把 `medical.json` 放在本仓库根目录即可，加载脚本会自动找到它
（也可以放别处，用 `--data <路径>` 或环境变量 `MEDICAL_JSON` 指定）。

### 关于语言

数据集是中文的，所以节点名、关系值和系统给出的回答都是中文。代码、测试和文档的组织
方式尽量不依赖读中文：关系类型名是 ASCII（`diseaseSymptomRelation` 之类），
schema 在英文 README 里有对应说明。

### 数据质量：已知的问题

这份数据是爬来的，没有经过清洗，用之前应当知道：

* **同名重复记录。** `胎膜早破` 在源数据里有两条 `_id` 不同的记录，
  导致图谱里出现重复节点、`disease.name` 建不了唯一约束。
  `python -m app.cli --doctor` 会把这类问题报出来，
  `python -m scripts.dedupe` 可以清理（默认只读预演）。
* **症状字段混入非症状词。** 例如「感冒」的症状列表里出现过「情绪性感冒」
  这种实为疾病名的条目。
* **属性字段格式不统一。** `cured_prob`（治愈率）在多数疾病上是百分比字符串，
  但在另一些疾病上是自由文本（糖尿病那条是「药物可控制，不易根治」）。
  本项目的评测集里曾因为假设它一定是百分比而误判过一道题，
  这件事记在 README 的实测结果一节里。
* **关系语义有重叠。** `diseaseDrugRelation`（常用药，每病 1–2 个）和
  `diseaseRecommendDrugRelation`（推荐药，每病平均 8 个）光看名字分不出区别。
  本项目用 `data/schema_notes.json` 人工补了一层语义说明注入 prompt。

---

## 三、第三方组件

| 组件 | 用途 | 许可 | 是否随仓库分发 |
|---|---|---|---|
| [Neo4j Community Edition](https://neo4j.com/deployment-center/) 5.26 | 图数据库 | GPLv3 | **否**，请自行下载 |
| [neo4j Python Driver](https://github.com/neo4j/neo4j-python-driver) | 数据库驱动 | Apache-2.0 | 否（pip 安装） |
| [openai-python](https://github.com/openai/openai-python) | OpenAI 兼容协议客户端 | Apache-2.0 | 否（pip 安装） |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | 模糊匹配 | MIT | 否（pip 安装） |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 读 .env | BSD-3-Clause | 否（pip 安装） |

LLM 服务默认指向智谱 GLM 的 OpenAI 兼容端点，但项目不绑定任何供应商 ——
改 `.env` 里三行就能换成硅基流动 / DeepSeek / 本地 Ollama。
**本仓库不包含任何 API 密钥。**

---

## 四、开发工具

开发过程中使用了 AI 编程助手，包括 Anthropic 的 Claude 和 OpenAI 的 ChatGPT / Codex。

README 里的性能数字都是在真实 Neo4j 实例和真实 LLM 上实测的，不是估算，
逐题原始结果存档在 `eval/runs/` 可供复核。
