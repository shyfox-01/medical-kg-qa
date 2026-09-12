"""意图识别 + Cypher 模板快路径。

v1 的每一次提问都要走 LLM 生成 Cypher。但这套图谱的 schema 是**极其规整**的：
9 类节点、12 类关系，**全部**以 (:disease) 为起点。绝大多数问题实际上只是
「某个疾病 + 某一条关系」，把它交给大模型现写查询，是拿概率去换一件确定的事。

所以 v2 加了一条快路径：本地识别意图 -> 挑锚点实体 -> 套白名单模板。
命中就**一次 LLM 都不用调**（只有最后组织回答那次），带来三个好处：

  * **快**：省掉 1-3 次生成往返
  * **省**：一道题的 token 直接砍掉大半
  * **准**：关系是查表选的，不是模型猜的，不存在 diseaseDrugRelation 和
    diseaseRecommendDrugRelation 选错的问题

关键是**知道自己什么时候不该出手**。以下情况一律放弃、交回 LLM：
  * 命中两个及以上一级意图（「…可能是什么病，分别挂什么科」是两跳）
  * 找不到所需 label 的锚点实体
  * 聚合、排序、比较这类没法用固定模板表达的问题

模板生成的语句**仍然要过 cypher_guard + EXPLAIN**。不是不信任自己的模板，
而是不想让"某条路径可以跳过校验"这件事存在 —— 那种口子迟早会被后来的改动撑大。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .entity_linker import EntityLinker, Mention

# ---------------------------------------------------------------- 意图词表
#
# 用**最长匹配**而不是先后顺序来决胜负：「胃炎的治疗方式是什么」里
# 「治疗方式」(4 字) 要赢过「是什么」(3 字)。靠规则表的排列顺序去调这种优先级
# 很脆弱，改一条就可能撞坏另一条。

# 意图规则写成**候选列表**而不是一整条 `a|b|c` 正则，编译时按长度降序排。
#
# 原因：Python 正则的 alternation 是"最左优先"，不是"最长优先"。
# 「胃炎不治会引起什么病」里，`不治会` 在下标 2 就能匹配上，扫描指针直接跳过 5，
# 后面那个真正想要的 `会引起什么病` 永远轮不到 —— 于是这句被判成了两个意图而放弃快路径。
# 手工把长的排前面能修好，但每加一条规则都要重新想一遍顺序，太脆。
# 排序交给代码做，规则表就只管写规则。
_TIER1: list[tuple[str, list[str]]] = [
    ("taboo_food", ["忌口", "忌食", "不能吃", "不宜吃", "不该吃", "别吃什么", "禁食",
                    "饮食禁忌", r"饮食上?[要需]?注意", "哪些不能吃"]),
    # 「能吃什么」前面必须不是否定词。否则「糖尿病人**不能吃**什么」里的
    # 「能吃什么」(4 字) 会靠最长匹配赢过「不能吃」(3 字)，把忌口问成宜吃 —— 意思正好反了。
    ("suitable_food", ["适合吃", "宜吃", "吃什么好", "吃什么水果", r"多吃点?什么", "食疗",
                       r"(?<![不别忌禁])能吃什么"]),
    ("recipe", ["食谱", "吃什么菜", "推荐菜", "做什么吃", "菜谱"]),
    ("drug", ["吃什么药", "用什么药", "什么药", "常用药", "哪些药", "药物有哪些",
              "开什么药", "用药", "服什么药"]),
    ("cure_way", ["怎么治", "如何治", "怎样治", "怎么医", "治疗方式", "治疗方法",
                  "治疗手段", "方式有哪些", r"能治好吗?"]),
    ("check", ["做什么检查", "哪些检查", "检查项目", "需要检查", "要检查", "化验什么",
               "化验", "查什么", "做什么化验"]),
    ("department", ["挂什么科", "挂哪个科", "挂哪科", "哪个科室", "什么科室", "看什么科",
                    "看哪个科", "挂号", r"挂[^，。？?]{0,4}科", "科室", "科负责",
                    r"负责[^，。？?]{0,4}疾病", "看哪些病", "管哪些病", "都看什么病"]),
    ("crowd", ["什么人容易", "哪些人容易", "谁容易", "易感人群", "高危人群",
               "什么人会得", "哪些人会得", "好发人群"]),
    ("complication", ["并发症", "合并症", "会引起什么病", "引发什么病", "会导致什么病",
                      "引起什么病", "继发"]),
    ("symptom", ["什么症状", "哪些症状", "症状", "表现", "征兆", "前兆", "什么感觉",
                 "临床表现", "有哪些不适"]),
    ("category", ["属于什么类", "疾病分类", r"属于哪一?类", "哪个科目"]),
    ("attr_cured_prob", ["治愈率", "治愈概率", r"治好的?概率", "能不能治愈"]),
    ("attr_cost", ["多少钱", "花多少", r"治疗费用?", "费用", "要花费"]),
    ("attr_cause", ["怎么引起", "如何引起", "什么原因", "病因", "为什么会得",
                    "由什么引起", "怎么得的", "怎么造成"]),
    ("attr_prevent", ["怎么预防", "如何预防", "预防措施", "怎样预防"]),
    ("attr_infect", ["传染吗", "会传染", "传染性", "传播途径", "会不会传染", "传不传染"]),
    ("attr_duration", ["治多久", "多长时间能好", "治疗周期", "要治多久", "多久能好"]),
    ("attr_prob", ["发病率", "患病率", "多少人得"]),
    ("attr_yibao", ["医保", "报销"]),
]

# 二级意图：问法本身很泛，只有在没有一级意图时才用它
_TIER2: list[tuple[str, list[str]]] = [
    ("disease_by_symptom", ["可能是什么病", "是什么病", "什么病", "怎么回事",
                            "得了什么", "是什么毛病", "什么原因造成"]),
    ("attr_desc", ["是什么", "什么是", "介绍一下", "简介", "了解一下"]),
]


def _compile(table: list[tuple[str, list[str]]]) -> list[tuple[str, re.Pattern]]:
    return [
        (name, re.compile("|".join(sorted(alts, key=len, reverse=True))))
        for name, alts in table
    ]


_COMPILED = _compile(_TIER1)
_COMPILED2 = _compile(_TIER2)

# 求交集信号：「高血压和糖尿病**共同**的忌口」「**既**能治高血压**又**能治糖尿病」
_INTERSECT = re.compile(r"共同|都能|都可以|同时[能可]|既.{0,8}又|共有|两种病|都要|都需要")
# 计数信号：「一共负责**多少种**疾病」
_COUNT = re.compile(r"多少种|多少个|几种|几个|数量|一共有多少|总共")

# 意图 -> (关系, 目标 label, 中文列名)
_REL_INTENTS: dict[str, tuple[list[str], str, str]] = {
    "symptom":       (["diseaseSymptomRelation"], "symptom", "症状"),
    "department":    (["diseaseDepartmentRelations"], "department", "就诊科室"),
    "check":         (["diseaseCheckRelation"], "check", "检查项目"),
    "cure_way":      (["diseaseCureWayRelation"], "cureWay", "治疗方式"),
    "taboo_food":    (["diseaseTabooFoodRelation"], "food", "忌吃"),
    "suitable_food": (["diseaseSuitableFoodRelation"], "food", "宜吃"),
    "recipe":        (["diseaseRecommendRecipeRelation"], "food", "推荐食谱"),
    "crowd":         (["diseaseCrowdRelation"], "crowd", "易感人群"),
    "complication":  (["diseaseDiseaseRelation"], "disease", "并发症"),
    "category":      (["diseaseCategoryRelation"], "category", "所属分类"),
    # 常用药和推荐药是两条不同的关系，语义有重叠但粒度不同（1-2 个 vs 平均 8 个）。
    # 问「常用药」只取前者，问「吃什么药」两条都给，让回答环节自己分层讲。
    "drug":          (["diseaseDrugRelation", "diseaseRecommendDrugRelation"], "drug", "药物"),
}

# 意图 -> (属性名, 中文列名)。属性名是白名单，不接受任何外部输入
_ATTR_INTENTS: dict[str, tuple[str, str]] = {
    "attr_cured_prob": ("cured_prob", "治愈率"),
    "attr_cost":       ("cost_money", "治疗费用"),
    "attr_cause":      ("cause", "病因"),
    "attr_prevent":    ("prevent", "预防措施"),
    "attr_infect":     ("get_way", "传染性"),
    "attr_duration":   ("cure_lasttime", "治疗周期"),
    "attr_prob":       ("get_prob", "发病率"),
    "attr_yibao":      ("yibao_status", "医保状态"),
    "attr_desc":       ("desc", "疾病简介"),
}


@dataclass
class Plan:
    intent: str
    cypher: str
    params: dict
    describe: str
    anchors: list[Mention] = field(default_factory=list)
    rels: list[str] = field(default_factory=list)
    prop: str | None = None
    ambiguous: list[str] = field(default_factory=list)  # 非空 = 需要用户消歧


def detect_intent(question: str) -> tuple[str | None, list[str]]:
    """返回 (选中的意图, 命中的一级意图列表)。

    命中两个及以上一级意图说明这是个多跳/复合问题，模板表达不了，
    调用方应该据此放弃快路径 —— 所以第二个返回值要一并给出来。
    """
    q = question or ""
    best: tuple[int, str] | None = None
    hits: list[str] = []
    spans: list[tuple[int, int]] = []
    for name, pat in _COMPILED:
        found = list(pat.finditer(q))
        if not found:
            continue
        hits.append(name)
        longest = max(found, key=lambda m: m.end() - m.start())
        spans.append((longest.start(), longest.end()))
        size = longest.end() - longest.start()
        if best is None or size > best[0]:
            best = (size, name)

    # 「症状 -> 疾病」是一跳，它再叠一个一级意图就是两跳。
    #   「咳嗽发热**可能是什么病**，分别**挂什么科**」= symptom -> disease -> department
    # 模板表达不了，必须交回 LLM。
    # 但「胃炎不治会**引起什么病**」里的「什么病」只是 complication 那条规则的一部分，
    # 不是独立意图 —— 所以要看区间是不是被一级意图的区间**包住**了。
    by_symptom = _COMPILED2[0][1]
    for m in by_symptom.finditer(q):
        if not any(s <= m.start() and m.end() <= e for s, e in spans):
            if hits:
                hits.append("disease_by_symptom")
            break

    if best:
        return best[1], hits
    for name, pat in _COMPILED2:
        if pat.search(q):
            return name, hits
    return None, hits


def plan(
    question: str, linker: EntityLinker, intent_hint: str | None = None
) -> Plan | None:
    """尝试用模板生成查询。做不到就返回 None，让 LLM 接手。

    `intent_hint` 来自多轮会话：「糖尿病有什么症状」→「高血压呢」，
    第二问自己识别不出意图，但上文的意图是可以接着用的。
    只在本句**完全没有**意图信号时才采用，不会覆盖用户明确表达的意图。
    """
    intent, tier1_hits = detect_intent(question)
    if intent is None and intent_hint:
        intent, tier1_hits = intent_hint, [intent_hint]
    # 没识别出意图，但问句里有科室实体又在问数量/清单 ——「呼吸内科一共负责多少种疾病」
    if intent is None:
        dep = linker.anchor(question, "department")
        if dep and (_COUNT.search(question) or "疾病" in question or "病" in question):
            return _plan_department_reverse(question, dep)
        return None
    # 复合意图：「咳嗽发热可能是什么病，分别挂什么科」= 症状->疾病->科室，模板表达不了
    if len(set(tier1_hits)) > 1:
        return None

    if intent in _REL_INTENTS:
        return _plan_relation(question, linker, intent)
    if intent in _ATTR_INTENTS:
        return _plan_attribute(question, linker, intent)
    if intent == "disease_by_symptom":
        return _plan_by_symptom(question, linker)
    return None


# ---------------------------------------------------------------- 各类模板

def _plan_relation(question: str, linker: EntityLinker, intent: str) -> Plan | None:
    rels, target, column = _REL_INTENTS[intent]
    if intent == "drug" and "常用" in question:
        rels = ["diseaseDrugRelation"]
        column = "常用药"

    diseases = linker.anchors(question, "disease", limit=4)

    # 反查：锚点是科室而不是疾病 ——「呼吸内科一共负责多少种疾病」
    if not diseases and intent == "department":
        if dep := linker.anchor(question, "department"):
            return _plan_department_reverse(question, dep)

    if not diseases:
        # 词典里没有对应疾病；如果关键词模糊命中一大片，与其硬猜不如让用户选
        return None

    # Neo4j 5 起，多关系写法必须是 [r:A|B]，老的 [r:A|:B] 会直接语法报错
    rel_pattern = ":" + "|".join(rels)

    # 多个疾病 + 求交集信号 ->「共同的忌口食物」「既能治 A 又能治 B 的方式」
    if len(diseases) >= 2 and _INTERSECT.search(question):
        names = [m.name for m in diseases]
        # 不用 `WHERE 命中数 = 全部` 硬筛交集。实测「高血压和糖尿病共同的忌口食物」
        # 在这份数据里交集**真的是空的**（两边各 4 个忌口，完全不重叠），
        # 硬筛的话就只能回一句"没有"，虽然正确但对用户没用。
        # 改成把并集连同命中数一起返回，真正的共同项自然排在最前面，
        # 同时用户也能看到各自的清单和"为什么没有交集"。
        cypher = (
            f"MATCH (d:disease)-[{rel_pattern}]->(x:`{target}`) "
            f"WHERE d.name IN $names "
            f"WITH x, collect(DISTINCT d.name) AS 涉及疾病, count(DISTINCT d) AS 命中数 "
            f"RETURN x.name AS {column}, 涉及疾病, 命中数 "
            f"ORDER BY 命中数 DESC, x.name LIMIT 40"
        )
        return Plan(
            intent=f"{intent}:intersect",
            cypher=cypher,
            params={"names": names},
            describe=f"比较 {'、'.join(names)} 在 {rels[0]} 上的重合情况",
            anchors=diseases,
            rels=rels,
        )

    anchor = diseases[0]

    if _COUNT.search(question):
        cypher = (
            f"MATCH (d:disease)-[{rel_pattern}]->(x:`{target}`) "
            f"WHERE d.name = $name "
            f"RETURN d.name AS 疾病, count(DISTINCT x) AS {column}数量 LIMIT 5"
        )
    elif len(rels) > 1:
        # 两条关系一起查时把关系类型带出来，回答环节才分得清"常用药"和"推荐药"
        cypher = (
            f"MATCH (d:disease)-[r{rel_pattern}]->(x:`{target}`) "
            f"WHERE d.name = $name "
            f"RETURN d.name AS 疾病, type(r) AS 关系, collect(DISTINCT x.name) AS {column} "
            f"LIMIT 5"
        )
    else:
        cypher = (
            f"MATCH (d:disease)-[{rel_pattern}]->(x:`{target}`) "
            f"WHERE d.name = $name "
            f"RETURN d.name AS 疾病, collect(DISTINCT x.name) AS {column} LIMIT 5"
        )

    return Plan(
        intent=intent,
        cypher=cypher,
        params={"name": anchor.name},
        describe=f"{anchor.name} --{'/'.join(rels)}--> {target}",
        anchors=[anchor],
        rels=rels,
        ambiguous=linker.ambiguous(anchor.name, "disease"),
    )


def _plan_department_reverse(question: str, dep: Mention) -> Plan:
    """科室 -> 疾病。「呼吸内科一共负责多少种疾病」「消化内科都看哪些病」"""
    if _COUNT.search(question):
        cypher = (
            "MATCH (d:disease)-[:diseaseDepartmentRelations]->(dep:department) "
            "WHERE dep.name = $name "
            "RETURN dep.name AS 科室, count(DISTINCT d) AS 疾病数量 LIMIT 5"
        )
    else:
        cypher = (
            "MATCH (d:disease)-[:diseaseDepartmentRelations]->(dep:department) "
            "WHERE dep.name = $name "
            "RETURN dep.name AS 科室, collect(DISTINCT d.name)[0..40] AS 疾病 LIMIT 5"
        )
    return Plan(
        intent="department_reverse",
        cypher=cypher,
        params={"name": dep.name},
        describe=f"{dep.name} 科室下的疾病",
        anchors=[dep],
        rels=["diseaseDepartmentRelations"],
    )


def _plan_attribute(question: str, linker: EntityLinker, intent: str) -> Plan | None:
    prop, column = _ATTR_INTENTS[intent]
    anchor = linker.anchor(question, "disease")
    if anchor is None:
        return None
    cypher = (
        f"MATCH (d:disease) WHERE d.name = $name "
        f"RETURN d.name AS 疾病, d.{prop} AS {column} LIMIT 5"
    )
    return Plan(
        intent=intent,
        cypher=cypher,
        params={"name": anchor.name},
        describe=f"读取 {anchor.name} 的 {prop} 属性",
        anchors=[anchor],
        prop=prop,
        ambiguous=linker.ambiguous(anchor.name, "disease"),
    )


def _plan_by_symptom(question: str, linker: EntityLinker) -> Plan | None:
    """症状 -> 疾病。命中的症状越多排越前，这比"随便返回 25 个"有用得多。"""
    symptoms = linker.anchors(question, "symptom", limit=6)
    if not symptoms:
        return None
    names = [m.name for m in symptoms]
    cypher = (
        "MATCH (d:disease)-[:diseaseSymptomRelation]->(s:symptom) "
        "WHERE s.name IN $names "
        "WITH d, count(DISTINCT s) AS 命中症状数 "
        "ORDER BY 命中症状数 DESC, d.name "
        "RETURN d.name AS 疾病, 命中症状数 LIMIT 15"
    )
    return Plan(
        intent="disease_by_symptom",
        cypher=cypher,
        params={"names": names},
        describe=f"由症状 {'、'.join(names)} 反查疾病，按命中数排序",
        anchors=symptoms,
        rels=["diseaseSymptomRelation"],
    )
