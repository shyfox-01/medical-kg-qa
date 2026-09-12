"""测试夹具。

整套测试**不连数据库、不调 LLM、不联网**。这是刻意的：
校验闸、安全闸、意图识别、实体链接、指代消解全都是纯函数或纯本地逻辑，
它们的正确性不该依赖"Neo4j 起没起来"。

图谱 schema 用一份和真库同构的假数据（label / 关系 / 属性都对得上），
实体名单取真图谱里的一小撮代表性节点 —— 包括那些同时挂多个标签的
（咳嗽、头痛、腹泻既是 disease 又是 symptom），因为它们正是最容易出 bug 的地方。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.entity_linker import EntityLinker  # noqa: E402
from app.schema import GraphSchema  # noqa: E402

LABELS = ["disease", "department", "symptom", "cureWay", "check", "drug", "crowd", "food", "category"]
RELS = [
    "diseaseDepartmentRelations", "diseaseSymptomRelation", "diseaseCureWayRelation",
    "diseaseCheckRelation", "diseaseDrugRelation", "diseaseCrowdRelation",
    "diseaseSuitableFoodRelation", "diseaseTabooFoodRelation", "diseaseDiseaseRelation",
    "diseaseCategoryRelation", "diseaseRecommendDrugRelation", "diseaseRecommendRecipeRelation",
]
DISEASE_PROPS = [
    "cause", "cost_money", "cure_lasttime", "cured_prob", "desc",
    "get_prob", "get_way", "name", "prevent", "yibao_status",
]

_TARGET = {
    "diseaseDepartmentRelations": "department",
    "diseaseSymptomRelation": "symptom",
    "diseaseCureWayRelation": "cureWay",
    "diseaseCheckRelation": "check",
    "diseaseDrugRelation": "drug",
    "diseaseRecommendDrugRelation": "drug",
    "diseaseCrowdRelation": "crowd",
    "diseaseSuitableFoodRelation": "food",
    "diseaseTabooFoodRelation": "food",
    "diseaseRecommendRecipeRelation": "food",
    "diseaseDiseaseRelation": "disease",
    "diseaseCategoryRelation": "category",
}

# (name, label)。刻意包含多标签同名的节点，它们是各种排序 bug 的高发区
NAMES: list[tuple[str, str]] = [
    ("糖尿病", "disease"), ("高血压", "disease"), ("肺炎", "disease"), ("胃炎", "disease"),
    ("感冒", "disease"), ("贫血", "disease"), ("糖尿病足", "disease"), ("小儿肺炎", "disease"),
    ("急性肺炎", "disease"), ("慢性肺炎", "disease"), ("球形肺炎", "disease"),
    ("肺炎杆菌肺炎", "disease"), ("水痘肺炎", "disease"), ("胃癌", "disease"),
    ("咳嗽", "disease"), ("咳嗽", "symptom"),
    ("头痛", "disease"), ("头痛", "symptom"),
    ("腹泻", "disease"), ("腹泻", "symptom"),
    ("发烧", "symptom"), ("烧心", "symptom"), ("多饮", "symptom"), ("消瘦", "symptom"),
    ("尿糖", "symptom"), ("糖尿", "symptom"), ("剧烈疼痛", "symptom"),
    ("内科", "department"), ("内分泌科", "department"), ("呼吸内科", "department"),
    ("呼吸内科", "category"), ("心内科", "department"), ("血液科", "department"),
    ("药物治疗", "cureWay"), ("手术治疗", "cureWay"), ("支持性治疗", "cureWay"),
    ("药物", "cureWay"), ("手术", "cureWay"),
    ("血常规", "check"), ("尿常规", "check"),
    ("二甲双胍片", "drug"), ("感冒灵颗粒", "drug"), ("布洛芬片", "drug"),
    ("肥胖人群", "crowd"), ("有家族史者", "crowd"),
    ("西瓜", "food"), ("蜂蜜", "food"), ("冰糖", "food"), ("杏仁", "food"), ("猪血", "food"),
    ("内分泌科疾病", "category"),
]

ALIASES = {
    "头疼": "头痛", "拉肚子": "腹泻", "血糖高": "糖尿病",
    "发热": "发烧", "胃里烧得慌": "烧心", "跑肚": "腹泻",
}


@pytest.fixture
def schema() -> GraphSchema:
    props = {lb: ["name"] for lb in LABELS}
    props["disease"] = DISEASE_PROPS
    counts = {lb: 100 for lb in LABELS}
    counts["disease"] = 8808
    triples = [("disease", rel, _TARGET[rel]) for rel in RELS]
    return GraphSchema(
        labels=list(LABELS), rel_types=list(RELS), triples=triples,
        properties=props, counts=counts,
    )


@pytest.fixture
def linker() -> EntityLinker:
    return EntityLinker(NAMES, ALIASES)
