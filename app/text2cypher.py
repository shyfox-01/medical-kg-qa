"""问答主链路。

    问题
     ├─ 安全闸           自伤危机 -> 直接短路，不查图谱（0 次 LLM 调用）
     ├─ 指代消解         「那它忌口什么」-> 「糖尿病忌口什么」
     ├─ 缓存             命中直接返回
     ├─ 实体链接         本地词典 + 别名，不花 token
     ├─ 模板快路径 ★     意图明确 + 锚点唯一 -> 查表生成 Cypher，0 次生成调用
     │    └─ 落空时回落到 LLM
     ├─ LLM 生成         schema 注入 + 意图分类 + 错误回灌重试
     │    └─ 判定越界 -> 直接拒答，不执行也不组织回答（省 2 次调用）
     ├─ 校验 + 只读执行  三道闸，见 graph.py / cypher_guard.py
     ├─ 0 结果兜底       近似名建议 + 全文检索，而不是一句"查不到"
     └─ 组织回答         关系语义注入 + 截断标记 + 确定性来源与免责声明

带 ★ 的是 v2 新增的主路径。v1 是"每一问都必须让大模型现写一条 Cypher"，
而这套图谱的 schema 极其规整（9 类节点、12 类关系，全部以 disease 为起点），
大多数问题本来就只是"某个疾病 + 某条关系"，交给模型是拿概率换确定性。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from . import answer as answer_mod
from . import safety as safety_mod
from .cache import TTLCache, make_key
from .config import settings
from .cypher_guard import CypherRejected
from .entity_linker import EntityLinker, Mention
from .graph import GraphStore, QueryResult
from .llm import EmptyCompletion, Usage
from .planner import Plan, plan as make_plan
from .session import Conversation, Turn, focus_from

DISCLAIMER = answer_mod.DISCLAIMER

_CYPHER_SYSTEM = """你是医疗知识图谱的 Cypher 生成器。根据用户问题生成一条**只读** Cypher 查询。

# 图谱 Schema
{schema}

# 已经对齐到图谱的实体（请优先直接使用这里的规范名，不要自己改写）
{entities}
{history}
# 硬性规则
1. 只允许 MATCH / WHERE / WITH / RETURN / ORDER BY / LIMIT。禁止 CREATE、MERGE、SET、DELETE。
   只读子查询可以写 `CALL {{ ... }}`，但不允许调用任何存储过程或 apoc / db / dbms 下的函数。
2. 关系方向必须严格照 Schema，不能反写。所有关系都以 (:disease) 为起点。
3. 只能使用 Schema 里列出的节点类型、关系类型和属性名，不要发明新的。
4. 一定要 RETURN 具体属性（如 d.name、s.name），不要 RETURN 整个节点。
5. 结尾带 LIMIT，一般 LIMIT 25 足够，最大不超过 {max_limit}。
6. 上面给了规范名就用 `{{name: "规范名"}}` 精确匹配；没给或不确定时用
   `WHERE d.name CONTAINS "关键词"` 做模糊匹配。
7. 问「哪些疾病会有某症状」这类反查时，仍然写 (:disease)-[:diseaseSymptomRelation]->(:symptom)，
   只是把约束加在 symptom 上。
8. 变长路径必须写明上界且不超过 {max_hops} 跳。

# 先判断问题类不类得上这张图谱
`intent` 字段取值：
  "kg_query"     —— 能用上面的图谱回答（疾病的症状/科室/检查/用药/治疗/饮食/人群/并发症等）
  "out_of_scope" —— 图谱回答不了（天气、编程、购物、闲聊、非医疗话题，
                    以及虽然是医疗但图谱里没有的信息，比如具体用药剂量、医院排名、报销比例）
判为 out_of_scope 时 `cypher` 留空字符串，不要硬凑一条查询。

# 输出格式
只输出 JSON，不要有别的文字：
{{"intent": "kg_query", "reasoning": "一句话说明查询思路", "cypher": "MATCH ... RETURN ... LIMIT 25"}}"""

_FEWSHOT = [
    (
        "肺炎有什么症状？",
        '{"intent": "kg_query", "reasoning": "从疾病出发沿症状关系取 symptom.name", '
        '"cypher": "MATCH (d:disease)-[:diseaseSymptomRelation]->(s:symptom) '
        'WHERE d.name = \\"肺炎\\" RETURN d.name AS 疾病, collect(s.name) AS 症状 LIMIT 25"}',
    ),
    (
        "咳嗽和发热可能是什么病？该挂哪个科？",
        '{"intent": "kg_query", "reasoning": "由症状反查疾病并带出科室", '
        '"cypher": "MATCH (d:disease)-[:diseaseSymptomRelation]->(s:symptom) '
        'WHERE s.name IN [\\"咳嗽\\", \\"发烧\\"] '
        'WITH d, count(DISTINCT s) AS 命中 ORDER BY 命中 DESC LIMIT 10 '
        'MATCH (d)-[:diseaseDepartmentRelations]->(dep:department) '
        'RETURN d.name AS 疾病, 命中, collect(dep.name) AS 科室 LIMIT 25"}',
    ),
    (
        "今天上海天气怎么样？",
        '{"intent": "out_of_scope", "reasoning": "天气不在医疗知识图谱范围内", "cypher": ""}',
    ),
]

_OUT_OF_SCOPE_ANSWER = (
    "这个问题超出了本系统的范围。我只能回答医疗知识图谱里有的内容：\n"
    "8808 种疾病的症状、就诊科室、检查项目、用药、治疗方式、忌口与宜吃、"
    "易感人群、并发症，以及病因、预防、治愈率、大概费用这些属性。"
)


@dataclass
class Step:
    name: str
    detail: str
    ok: bool = True
    seconds: float = 0.0


@dataclass
class QAResult:
    question: str
    answer: str
    resolved_question: str = ""
    cypher: str | None = None
    params: dict = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    attempts: int = 0
    total_seconds: float = 0.0
    route: str = ""                       # template / llm / cache / safety / out_of_scope / no_result
    intent: str | None = None
    truncated: bool = False
    safety_level: str = "none"
    safety_categories: tuple[str, ...] = ()

    def trace(self) -> str:
        out = []
        for s in self.steps:
            flag = "OK " if s.ok else "FAIL"
            out.append(f"  [{flag}] {s.name} ({s.seconds:.2f}s)\n        {s.detail}")
        return "\n".join(out)


class Text2CypherPipeline:
    def __init__(
        self,
        graph: GraphStore,
        llm: Any,
        linker: EntityLinker,
        conversation: Conversation | None = None,
        cache: TTLCache | None = None,
    ) -> None:
        self.graph = graph
        self.llm = llm
        self.linker = linker
        self.conversation = conversation or Conversation(max_turns=settings.history_turns)
        self.cache = cache

    # ================================================================== 主流程

    def answer(self, question: str) -> QAResult:
        t_start = time.perf_counter()
        usage_base = self.llm.usage.snapshot()
        res = QAResult(question=question, answer="", resolved_question=question)
        if not question.strip():
            res.answer = "问题为空。"
            return res

        # ---- 0. 安全闸（本地规则，0 次 LLM 调用）
        t0 = time.perf_counter()
        assessment = safety_mod.assess(question, self.linker.labels_in(question))
        res.safety_level = assessment.level
        res.safety_categories = assessment.categories
        if settings.safety and assessment.categories:
            detail = f"level={assessment.level} 类别={list(assessment.categories)}"
            if assessment.injection:
                # 真防线是校验闸 + 只读事务，这里只是让"有人在试"这件事看得见
                detail += f" | 检出注入痕迹 {list(assessment.injection)}"
            res.steps.append(Step("安全闸", detail, seconds=time.perf_counter() - t0))
        if settings.safety and assessment.blocked:
            res.answer = assessment.short_circuit
            res.route = "safety"
            res.total_seconds = time.perf_counter() - t_start
            return res

        # ---- 1. 指代消解
        resolution = self.conversation.resolve(question, self.linker)
        res.resolved_question = resolution.question
        if resolution.note:
            res.steps.append(
                Step("指代消解", f"{resolution.original} -> {resolution.note}", seconds=0.0)
            )
        q = resolution.question

        # ---- 2. 缓存
        key = self._cache_key(q)
        if self.cache is not None and (cached := self.cache.get(key)) is not None:
            cached = _clone_for_cache_hit(cached, question, q)
            cached.route = "cache"
            cached.total_seconds = time.perf_counter() - t_start
            self._remember(cached)
            return cached

        # ---- 3. 实体链接
        t0 = time.perf_counter()
        res.mentions = self.linker.scan(q)
        res.steps.append(
            Step(
                "实体链接",
                self.linker.describe(res.mentions).replace("\n", " | ") or "无",
                seconds=time.perf_counter() - t0,
            )
        )

        # ---- 4. 模板快路径
        result: QueryResult | None = None
        used_plan: Plan | None = None
        if settings.fast_path:
            result, used_plan = self._try_template(q, res, resolution.carried_intent)

        # ---- 5. LLM 兜底
        if result is None or not result.rows:
            llm_result = self._try_llm(q, res)
            if llm_result is _OUT_OF_SCOPE:
                res.route = "out_of_scope"
                res.intent = "out_of_scope"
                res.answer = _OUT_OF_SCOPE_ANSWER
                return self._finish(res, assessment, usage_base, t_start)
            if llm_result is not None and llm_result.rows:
                result, used_plan = llm_result, None
                res.route = "llm"

        # ---- 6. 出结果 or 兜底检索
        if result is not None:
            res.cypher = result.stmt
            res.params = used_plan.params if used_plan else {}
            res.rows = result.rows
            res.truncated = result.truncated

        if not res.rows:
            return self._finish(
                self._no_result(q, res, used_plan), assessment, usage_base, t_start
            )

        # ---- 7. 组织回答
        rels = used_plan.rels if used_plan else _rels_in(res.cypher or "", self.graph)
        t0 = time.perf_counter()
        text = self.llm.chat(
            answer_mod.build_messages(
                q,
                res.cypher or "",
                res.rows,
                truncated=res.truncated,
                rels=rels,
                safety_instruction=assessment.instruction if settings.safety else "",
            ),
            temperature=0.3,
            max_tokens=1200,
            thinking=False,  # 组织回答不需要推理，纯浪费 token 和延迟
        )
        res.steps.append(Step("组织回答", f"{len(text)} 字", seconds=time.perf_counter() - t0))
        evidence = answer_mod.Evidence(
            path=used_plan.describe if used_plan else (res.cypher or "")[:80],
            row_count=len(res.rows),
            truncated=res.truncated,
            entities=tuple(m.name for m in res.mentions[:4]),
        )
        res.answer = answer_mod.finalize(text, evidence)
        return self._finish(res, assessment, usage_base, t_start)

    # ================================================================ 各分支

    def _try_template(
        self, q: str, res: QAResult, intent_hint: str | None = None
    ) -> tuple[QueryResult | None, Plan | None]:
        t0 = time.perf_counter()
        try:
            p = make_plan(q, self.linker, intent_hint)
        except Exception as e:  # noqa: BLE001 - 快路径任何意外都不该拖垮问答
            res.steps.append(Step("模板快路径", f"规划异常，回落 LLM：{e!r}", ok=False,
                                  seconds=time.perf_counter() - t0))
            return None, None
        if p is None:
            res.steps.append(
                Step("模板快路径", "未命中（意图不明确或缺锚点实体），交给 LLM",
                     seconds=time.perf_counter() - t0)
            )
            return None, None
        try:
            # 模板生成的语句一样要过校验闸 —— 不留"可跳过校验"的口子
            result = self.graph.run_generated(p.cypher, p.params)
        except (CypherRejected, Exception) as e:
            res.steps.append(Step("模板快路径", f"{p.intent} 执行失败，回落 LLM：{str(e)[:120]}",
                                  ok=False, seconds=time.perf_counter() - t0))
            return None, None
        res.intent = p.intent
        res.steps.append(
            Step(
                "模板快路径",
                f"intent={p.intent} | {p.describe} | {len(result.rows)} 行"
                + ("（0 行，回落 LLM）" if not result.rows else "，未调用 LLM 生成"),
                ok=bool(result.rows),
                seconds=time.perf_counter() - t0,
            )
        )
        if result.rows:
            res.route = "template"
        return result, p

    def _try_llm(self, q: str, res: QAResult) -> QueryResult | None | object:
        system = _CYPHER_SYSTEM.format(
            schema=self.graph.schema().to_prompt(),
            entities=self.linker.describe(res.mentions),
            history=("\n" + h + "\n" if (h := self.conversation.prompt_context()) else ""),
            max_limit=settings.max_limit,
            max_hops=settings.max_path_hops,
        )
        messages: list[dict] = [{"role": "system", "content": system}]
        for user_q, assistant_a in _FEWSHOT:
            messages += [
                {"role": "user", "content": user_q},
                {"role": "assistant", "content": assistant_a},
            ]
        messages.append({"role": "user", "content": q})

        for attempt in range(1, settings.max_cypher_retries + 1):
            res.attempts = attempt
            t0 = time.perf_counter()
            try:
                payload = self.llm.chat_json(messages, thinking=settings.thinking)
            except (ValueError, EmptyCompletion) as e:
                res.steps.append(Step(f"生成 #{attempt}", str(e), ok=False,
                                      seconds=time.perf_counter() - t0))
                messages.append({"role": "user", "content": "上一条不是合法 JSON，请只输出 JSON。"})
                continue

            intent = str(payload.get("intent") or "kg_query").strip()
            candidate = (payload.get("cypher") or "").strip()
            res.steps.append(
                Step(f"生成 #{attempt}", f"[{intent}] {candidate or '(空)'}",
                     seconds=time.perf_counter() - t0)
            )
            # 模型自己判定图谱管不了 —— 直接拒答，省掉执行和组织回答两步
            if intent == "out_of_scope" and not candidate:
                res.intent = "out_of_scope"
                return _OUT_OF_SCOPE
            if not candidate:
                messages.append({"role": "user", "content": "cypher 字段为空，请重新生成。"})
                continue

            t0 = time.perf_counter()
            try:
                result = self.graph.run_generated(candidate)
            except CypherRejected as e:
                res.steps.append(Step(f"校验 #{attempt}", str(e), ok=False,
                                      seconds=time.perf_counter() - t0))
                messages += [
                    {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
                    {"role": "user", "content": f"上面的查询被校验器拒绝：{e}\n请修正后重新输出 JSON。"},
                ]
                continue
            except Exception as e:  # 执行期错误（超时、类型不匹配等）
                res.steps.append(Step(f"执行 #{attempt}", repr(e), ok=False,
                                      seconds=time.perf_counter() - t0))
                messages += [
                    {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
                    {"role": "user", "content": f"执行报错：{e}\n请修正后重新输出 JSON。"},
                ]
                continue

            res.intent = intent
            res.cypher = result.stmt
            note = f"{len(result.rows)} 行 / {result.seconds * 1000:.0f}ms"
            if result.truncated:
                note += f" | 顶到 LIMIT {result.limit}，结果不完整"
            if result.rewrites:
                note += " | 校验器改写：" + "；".join(result.rewrites)
            if result.warnings:
                # EXPLAIN 报的性能警告（笛卡尔积、缺索引…）。不拦，但要看得见。
                note += " | 数据库警告：" + "；".join(w[:60] for w in result.warnings)
            res.steps.append(Step(f"执行 #{attempt}", note, seconds=result.seconds))
            if result.rows:
                return result
            if attempt < settings.max_cypher_retries:
                messages += [
                    {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
                    {
                        "role": "user",
                        "content": (
                            "查询语法没问题但返回 0 行。多半是实体名对不上或关系选错了。"
                            "请放宽条件重试：把精确匹配 `{name: \"X\"}` 换成 "
                            "`WHERE n.name CONTAINS \"关键词\"`，关键词取更短的核心词。"
                        ),
                    },
                ]
        return None

    def _no_result(self, q: str, res: QAResult, used_plan: Plan | None) -> QAResult:
        """0 结果兜底：把系统知道的东西摆出来，而不是甩一句"查不到"。"""
        res.route = res.route or "no_result"
        suggestions: list[str] = []
        fulltext: list[dict] = []
        if settings.fallback_search:
            t0 = time.perf_counter()
            if used_plan is not None and used_plan.ambiguous:
                suggestions = used_plan.ambiguous[:6]
            if not suggestions:
                suggestions = self.linker.suggest(q, k=5)
            fulltext = self.graph.fulltext_disease(q, limit=5)
            res.steps.append(
                Step(
                    "兜底检索",
                    f"近似名 {len(suggestions)} 个 / 全文命中 {len(fulltext)} 个",
                    seconds=time.perf_counter() - t0,
                )
            )
        res.answer = answer_mod.no_result_message(
            suggestions, fulltext, [m.name for m in res.mentions[:4]]
        )
        return res

    # ================================================================== 辅助

    def _cache_key(self, q: str) -> str:
        return make_key(
            q,
            self.graph.schema().fingerprint(),
            getattr(self.llm, "model", "?"),
            settings.fast_path,
            settings.safety,
            settings.default_limit,
        )

    def _finish(
        self, res: QAResult, assessment: safety_mod.SafetyAssessment,
        usage_base: Usage, t_start: float,
    ) -> QAResult:
        if settings.safety:
            res.answer = safety_mod.apply(assessment, res.answer)
        res.usage = self.llm.usage.since(usage_base)
        res.total_seconds = time.perf_counter() - t_start
        if self.cache is not None and res.route in ("template", "llm"):
            self.cache.put(self._cache_key(res.resolved_question), res)
        self._remember(res)
        return res

    def _remember(self, res: QAResult) -> None:
        self.conversation.record(
            Turn(
                question=res.question,
                resolved=res.resolved_question,
                intent=res.intent,
                focus=focus_from(res.mentions),
                cypher=res.cypher,
                row_count=len(res.rows),
                route=res.route,
            )
        )


# 用一个哨兵对象表示"模型判定越界"，避免和"没查到"(None) 混淆
_OUT_OF_SCOPE = object()


def _clone_for_cache_hit(cached: QAResult, question: str, resolved: str) -> QAResult:
    import copy

    out = copy.copy(cached)
    out.question = question
    out.resolved_question = resolved
    out.steps = list(cached.steps) + [Step("缓存", "命中，跳过全部查询与生成")]
    out.usage = Usage()
    return out


def _rels_in(cypher: str, graph: GraphStore) -> list[str]:
    """从语句里挑出用到的关系类型，供回答环节注入语义说明。"""
    return [r for r in graph.schema().rel_types if r in cypher]
