"""离线假 LLM：用规则代替模型，只为在没有 API key 的情况下验证链路是否通。

不参与正式问答，也不参与评测打分。留着是因为它能把「链路问题」和「模型问题」分开定位——
真实排查时先跑 --mock，通了就说明图谱、校验、执行、组织回答这一圈没毛病。

v2 里它还多了一个用途：**验证模板快路径确实省掉了生成调用**。
跑 `--mock` 时如果 usage.calls 只有 1（组织回答那次），就说明生成那步真的没走。
"""
from __future__ import annotations

import json
import re
import time

from .llm import Usage

_RULES = [
    (("忌", "不能吃", "禁"), "diseaseTabooFoodRelation", "food", "忌吃"),
    (("吃", "食物", "饮食", "宜"), "diseaseSuitableFoodRelation", "food", "宜吃"),
    (("症状", "表现", "征兆"), "diseaseSymptomRelation", "symptom", "症状"),
    (("科", "挂号"), "diseaseDepartmentRelations", "department", "科室"),
    (("检查", "化验"), "diseaseCheckRelation", "check", "检查"),
    (("药", "用药"), "diseaseDrugRelation", "drug", "药物"),
    (("治疗", "怎么治", "疗法"), "diseaseCureWayRelation", "cureWay", "治疗方式"),
    (("并发", "合并"), "diseaseDiseaseRelation", "disease", "并发症"),
    (("人群", "谁容易", "易感"), "diseaseCrowdRelation", "crowd", "易感人群"),
]
_OUT_OF_SCOPE = ("天气", "代码", "python", "编程", "股票", "游戏", "值得买", "电影")
_RESULT_BLOCK = re.compile(r"<查询结果>\s*(.*?)\s*</查询结果>", re.DOTALL)


class FakeLLM:
    model = "fake-rule-based"

    def __init__(self) -> None:
        self.usage = Usage()

    def _tick(self) -> None:
        self.usage.add(Usage(calls=1, prompt_tokens=0, completion_tokens=0, seconds=0.001))
        time.sleep(0.001)

    def chat_json(self, messages: list[dict], temperature: float = 0.0, thinking=None) -> dict:
        self._tick()
        question = messages[-1]["content"]
        if any(k in question.lower() for k in _OUT_OF_SCOPE):
            return {"intent": "out_of_scope", "reasoning": "规则判定越界", "cypher": ""}

        # 从 system prompt 里回捞实体链接的结果
        system = messages[0]["content"]
        keyword = ""
        for line in system.splitlines():
            if '-> (:disease {name: "' in line:
                keyword = line.split('name: "', 1)[1].split('"', 1)[0]
                break
        if not keyword:
            keyword = question[:4]

        rel, target, alias = "diseaseSymptomRelation", "symptom", "症状"
        for keys, r, t, a in _RULES:
            if any(k in question for k in keys):
                rel, target, alias = r, t, a
                break
        cypher = (
            f"MATCH (d:disease)-[:{rel}]->(x:{target}) "
            f'WHERE d.name CONTAINS "{keyword}" '
            f"RETURN d.name AS 疾病, collect(x.name) AS {alias} LIMIT 25"
        )
        return {"intent": "kg_query", "reasoning": f"规则命中 {rel}", "cypher": cypher}

    def chat(
        self, messages: list[dict], temperature: float = 0.0, max_tokens=None, thinking=None
    ) -> str:
        self._tick()
        payload = messages[-1]["content"]
        m = _RESULT_BLOCK.search(payload)
        if not m:
            return "（假 LLM）没有拿到查询结果块。"
        try:
            rows = json.loads(m.group(1).split("\n（共")[0])
        except json.JSONDecodeError:
            return "（假 LLM）拿到结果但没法解析。"
        return "（假 LLM 直出）" + json.dumps(rows[:3], ensure_ascii=False)
