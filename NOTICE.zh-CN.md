[English](NOTICE.md) | 简体中文

# 数据来源、许可与使用限制

## 医疗使用限制

**本项目仅供学习、研究和技术演示，不提供诊断、处方或个体化治疗建议。**

回答由检索记录和语言模型共同生成。图谱中的症状关联不表示诊断结论，药物和饮食关联不构成对个人的用药或饮食建议。医疗数据未经本项目临床审核，可能包含错误、遗漏和过时信息。

`app/safety.py` 包含危机表达、急症描述、剂量请求等识别规则。固定提示和生成约束可以处理部分已覆盖的表达，但可能漏判、误判或被模型忽略。它们不能替代医生、临床分诊或人工内容审核。

有健康问题请就医；紧急情况请联系当地急救服务，中国大陆拨打 **120**。如有伤害自己的念头，请联系可信任的人或专业支持。中国大陆可拨打全国统一心理援助热线 [12356](https://www.nhc.gov.cn/yzygj/c100068/202412/49a1a65386cd4be582d4702fd0926ee8.shtml)；其他地区可通过 [Find A Helpline](https://findahelpline.com) 查找当地资源。

## 数据来源

`medical.json` 不是本项目采集的，也不随本仓库分发。

| 项目 | 来源 |
|---|---|
| 上游仓库 | [liuhuanyong/QASystemOnMedicalKG](https://github.com/liuhuanyong/QASystemOnMedicalKG) |
| 数据文件 | [data/medical.json](https://github.com/liuhuanyong/QASystemOnMedicalKG/blob/master/data/medical.json) |
| 采集脚本 | [prepare_data/data_spider.py](https://github.com/liuhuanyong/QASystemOnMedicalKG/blob/master/prepare_data/data_spider.py)，包含寻医问药网 `jib.xywy.com` 的疾病页面地址 |
| 数据格式 | 每行一个 JSON 对象，包含 MongoDB 标识字段 `_id.$oid` |
| 项目使用的数据规模 | 8,808 条疾病记录，约 45 MB |

上游采集脚本提供了网站来源线索，但数据文件没有为每条记录保留可核验的采集日期、授权或临床审阅信息。本项目也未逐条核验记录与原始网页的对应关系。

### 数据使用条件

上游 [README](https://github.com/liuhuanyong/QASystemOnMedicalKG/blob/master/README.md) 声明：

> 本数据请勿商用

上游仓库未列出明确的许可证文件。上述非商用要求不等于原始网站或其他权利方对复制、再分发等用途的完整授权。使用前应核对上游声明和适用权限；本项目的 MIT 许可不适用于这份数据。

本仓库提供导入脚本和上游下载地址，不分发原始数据集。评测存档中含少量模型输出与检索内容片段，可能反映上游数据，也不应被理解为本项目另行授予这些内容的使用权。权利方如有疑问，可通过仓库 issue 联系维护者，请勿在公开 issue 中提交个人健康信息。

### 获取数据

```powershell
curl.exe -L -o medical.json https://raw.githubusercontent.com/liuhuanyong/QASystemOnMedicalKG/master/data/medical.json
```

将文件放在仓库根目录，或通过 `MEDICAL_JSON` 环境变量、导入脚本的 `--data <路径>` 参数指定位置。

### 数据质量

- **重复名称：** `胎膜早破` 有不同 `_id` 的同名记录，导入后可能存在重复节点。`python -m app.cli --doctor` 可检查重复情况；`python -m scripts.dedupe` 默认只读报告，加 `--apply` 才修改数据库。
- **字段语义噪声：** 症状列表可能混入疾病名或其他不适合当作症状的词。
- **格式不一致：** `cured_prob` 等字段既可能是百分比字符串，也可能是自由文本，不能统一当作数值解析。
- **关系含义重叠：** 常用药、推荐药等关系需要结合 [schema_notes.json](data/schema_notes.json) 中的说明理解。这些说明帮助查询规划，不构成药物疗效或适用性的审核。
- **时效性：** 数据不包含可靠的逐条更新日期，治疗方式、费用、医保等内容不能作为现行政策或临床指南使用。

数据、别名和意图规则主要面向中文。中英文文档介绍的是同一个系统，不表示已验证英文医疗问答能力。

## 模型服务与隐私

配置和密钥通过环境变量或本地 `.env` 读取。`.env` 被排除在版本控制之外。

使用外部模型服务时，问题、实体名称、图谱结构、检索内容，以及部分路径中的对话上下文可能发送给服务商。具体数据处理方式由所配置服务的条款决定。本项目不提供患者数据去标识化或医疗隐私合规保证，请勿输入可识别个人身份的病历。

执行过程显示和评测存档可能包含问题、生成查询及回答。保存或分享这些输出前，应检查其中是否有个人信息。设置本地模型端点后，也应自行核对该服务的日志与网络配置。

## 代码与第三方软件

本仓库代码按 [MIT](LICENSE) 许可发布。第三方数据、模型服务及软件遵循各自的许可或使用条款。

Python 依赖列在 [requirements.txt](requirements.txt)，测试依赖列在 [requirements-dev.txt](requirements-dev.txt)。Neo4j 需从 [官方页面](https://neo4j.com/deployment-center/) 单独获取，发行版和模型权重均不随仓库分发。

## 开发工具

开发过程中使用了 Claude、ChatGPT 和 Codex。
