[English](README.md) | 简体中文

# 医疗知识图谱问答系统

用中文自然语言查询疾病相关知识。系统将疾病、症状、药物、检查和科室等信息存入 Neo4j，通过参数化查询模板或大语言模型生成 Cypher，再依据检索结果组织回答。

项目关注的是如何让自然语言问答有可检查的数据依据。知识图谱提供实体、关系和属性，语言模型负责理解问题与组织表达；查询语句、返回结果和执行过程可供查看。这套流程采用 Text2Cypher，也属于基于图谱检索的问答（GraphRAG）。

数据集包含 8,808 条疾病记录。评测所用图谱包含 9 类节点、12 类关系，共 28,832 个节点和 337,239 条关系。实际建库规模取决于导入的数据和去重情况。

> ### ⚠ 使用前请阅读
>
> * **本项目仅供学习、研究和技术演示，不提供诊断、处方或个体化治疗建议。** 有健康问题请就医；紧急情况请联系当地急救服务，中国大陆拨打 **120**。
> * **不要依据系统输出决定用药或剂量。** 系统包含剂量请求识别和安全提示，但规则与模型都可能漏判或出错，不能替代专业评估。
> * **医疗数据未经本项目临床审核，可能包含错误、遗漏和过时信息。** 数据来自 [QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG)，上游声明请勿商用，本仓库不分发原始数据集。
> * 如有伤害自己的念头，请及时联系可信任的人或专业支持。中国大陆可拨打全国统一心理援助热线 [12356](https://www.nhc.gov.cn/yzygj/c100068/202412/49a1a65386cd4be582d4702fd0926ee8.shtml)；身处即时危险时请联系急救服务。
> * 数据来源、使用限制与隐私说明见 [NOTICE.zh-CN.md](NOTICE.zh-CN.md)。

## 功能

| 查询内容 | 示例问题 |
|---|---|
| 症状与疾病关联 | 肺炎有哪些症状？咳嗽发热关联哪些疾病？ |
| 就诊科室、检查 | 高血压挂什么科？肺炎要做什么检查？ |
| 药物和治疗方式记录 | 糖尿病常用药有哪些？胃炎有哪些治疗方式？ |
| 饮食、人群、并发症 | 糖尿病有哪些忌口记录？哪些人容易得高血压？ |
| 疾病属性 | 病因、预防、传染性、治疗周期、费用等字段 |
| 比较、统计、多跳查询 | 两种疾病有哪些共同关联？某科室关联多少种疾病？ |

支持多轮追问。以下示例展示问题的理解方式，不作为医疗回答：

```text
问：糖尿病有什么症状？ → 查询糖尿病的症状。
问：那忌口什么？       → 查询糖尿病的忌口记录。
问：高血压呢？         → 查询高血压的忌口记录，沿用上一问的意图。
```

查不到结果时，系统可提供近似实体名和全文检索候选；候选仅表示检索相关性，不表示诊断概率。超出知识图谱范围的问题有拒答路径。

## 工作原理

```text
中文问题
  → 本地医疗安全规则
  → 多轮指代补全、结果缓存
  → 实体链接：词典匹配、别名归一、模糊候选
  → 查询生成：意图模板 / LLM + 图谱 schema
  → 静态校验 → EXPLAIN → 只读事务执行
  → 空结果候选检索
  → 根据查询结果组织回答，附来源和安全提示
```

### 数据建模与实体链接

导入脚本将疾病简介、病因、预防等标量字段保存为疾病属性，将症状、药物、检查和科室等列表字段转换为节点及关系。实体按名称合并，写入使用参数化查询和批量导入。

实体链接将“拉肚子”等口语对齐到图谱名称。精确同名实体优先；同名多标签候选保留给查询规划使用。关系和属性的语义说明维护在 [data/schema_notes.json](data/schema_notes.json)。

### 查询规划

本地意图规则可识别的请求使用白名单模板生成参数化 Cypher，包括常见关系查询、部分统计和疾病比较。其余请求交给 LLM，提示中包含图谱结构与实体候选。模板查询无结果时也可能进入 LLM 路径。

模板路径省去的是生成查询的模型调用；有检索结果时，回答组织仍会调用模型。LLM 通过 OpenAI 兼容接口接入，端点、模型和密钥由 `.env` 配置。

### 查询与回答约束

生成的 Cypher 经过词法扫描、操作限制和 schema 检查，再通过 Neo4j `EXPLAIN` 预编译。查询使用只读事务，配置包括超时、返回行数上限和变长路径跳数上限。

回答提示要求依据检索结果作答。代码附加查询来源、返回行数和免责声明；返回行数达到限制时，会标记结果可能不完整。这些信息用于检查回答依据，不等于逐句事实核验，也不能保证消除模型幻觉。

医疗安全规则识别自伤危机、急症描述、剂量请求、特殊人群用药和诊断请求。识别到自伤危机时直接返回求助资源；其他类别通过生成约束或固定提示处理。该规则层不是临床分诊工具。

## 运行

需要 Python 环境、Neo4j 和支持 OpenAI 兼容接口的模型服务。开发与测试使用 Python 3.12；以下命令面向 Windows PowerShell。

### 1. 安装 Python 依赖

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

### 2. 获取数据

先阅读 [数据使用说明](NOTICE.zh-CN.md)，再从上游获取 `medical.json`（约 45 MB）：

```powershell
curl.exe -L -o medical.json https://raw.githubusercontent.com/liuhuanyong/QASystemOnMedicalKG/master/data/medical.json
```

默认放在仓库根目录；也可以通过 `MEDICAL_JSON` 环境变量或加载脚本的 `--data` 参数指定位置。

### 3. 启动 Neo4j

从 [Neo4j 下载页面](https://neo4j.com/deployment-center/) 获取 Community Edition 5.26，解压到 `neo4j/neo4j-community-5.26.0/`。该系列支持 [Java 17 或 21](https://neo4j.com/docs/operations-manual/current/installation/requirements/)；使用启动脚本时，建议先设置 `JAVA_HOME`。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_neo4j.ps1
```

Neo4j 浏览器地址为 `http://localhost:7474`，应用通过 Bolt 端口 `7687` 连接。首次启动时，在 Neo4j 中设置数据库密码。

### 4. 配置并导入图谱

```powershell
Copy-Item .env.example .env
notepad .env
```

填写 `NEO4J_PASSWORD`、`LLM_BASE_URL`、`LLM_MODEL` 和 `LLM_API_KEY`。模型调用可能产生费用，具体以服务商为准。

```powershell
.venv\Scripts\python -m scripts.load_kg --dry-run
.venv\Scripts\python -m scripts.load_kg
```

`--dry-run` 只解析数据；第二条命令会写入配置指定的数据库。

### 5. 提问

```powershell
.venv\Scripts\python -m app.cli
.venv\Scripts\python -m app.cli -q "肺炎有哪些症状"
.venv\Scripts\python -m app.cli --doctor
```

交互命令：`:trace` 显示执行过程，`:reset` 清空对话，`:cypher <语句>` 直接查询图谱，`:config` 查看脱敏配置，`:cache` 查看缓存统计，`q` 退出。

`.env`、原始数据集、Neo4j 发行版和虚拟环境不随仓库分发。调用外部模型时，问题和检索内容可能发送给服务商，请勿输入可识别个人身份的病历信息。

## 测试与评测

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m app.cli --selftest
.venv\Scripts\python -m scripts.demo
.venv\Scripts\python -m eval.run_eval --offline
.venv\Scripts\python -m eval.run_eval
.venv\Scripts\python -m eval.run_eval --repeat 3
```

- `pytest`：253 个单元测试，不需要数据库或模型服务。
- `--selftest`、`scripts.demo` 和 `--offline`：需要 Neo4j，不调用真实 LLM。
- 完整评测：需要 Neo4j 和模型服务。69 道中文题覆盖检索、多轮、越界、注入攻击和医疗安全等 11 类场景。

仓库中的 [评测存档](eval/runs/v2_final.json) 使用 GLM-4.5-Flash、`LLM_THINKING=off`，关闭缓存：

| 指标 | 存档结果 |
|---|---|
| 按评测规则通过 | 69 / 69 |
| LLM 调用 | 81 次 |
| 输入与输出 token 合计 | 71,312 |
| 最终回答路径 | 模板 47、LLM 4、越界拒答 16、空结果 1、安全响应 1 |

这是固定题集的一次内部评测，不代表医学准确率、临床有效性或对任意输入的安全保证。评分主要检查查询执行、关系选择、关键词和预期安全响应，不能代替完整答案的专业审核。生成结果和延迟会随模型及服务状态变化。

`--no-fast-path` 可用于模板开关实验，`--save` 保存结果，`--baseline` 比较指定存档。比较时需保持题集、评分规则和模型配置一致。图谱节点数与关系数的前后核对只反映数量变化，不能证明所有属性内容均未改变。

## 目录

```text
app/       实体链接、查询规划、数据库访问、安全规则、回答组织与命令行入口
data/      别名表和关系语义说明
scripts/   数据导入、Neo4j 启动、重复节点处理和演示
tests/     单元测试
eval/      评测题集、运行脚本和结果存档
```

## 使用限制

- 数据与本地规则主要面向中文，英文文档不表示系统已通过英文问答评测。
- 别名、模糊匹配和意图规则覆盖有限，实体歧义与多轮省略可能被错误理解。
- 原始数据包含重复名称、格式不一致和可疑医疗关联；费用、用药等内容可能过时。
- “没有查到共同关联”仅描述这份数据的检索结果，不代表医学上不存在共同项。
- 行数限制不等于对所有结果内容的完整性检查，聚合列表或文本也可能不完整。
- 医疗安全规则与查询校验均有覆盖边界，测试通过不代表适合临床或无人监督使用。

## 来源、许可与工具

疾病数据来自 [liuhuanyong/QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG)。代码按 [MIT](LICENSE) 许可发布；该许可不覆盖第三方医疗数据。来源与使用限制见 [NOTICE.zh-CN.md](NOTICE.zh-CN.md)。

开发过程中使用了 Claude、ChatGPT 和 Codex。
