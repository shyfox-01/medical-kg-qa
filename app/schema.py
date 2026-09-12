"""图谱 schema 的数据结构与 prompt 渲染。

从 graph.py 里拆出来，是为了让校验器和模板生成器**不依赖数据库连接**——
这样 tests/ 里可以拿一份假 schema 把所有静态规则跑完，不用起 Neo4j。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import DATA_DIR

_NOTES = DATA_DIR / "schema_notes.json"


def load_schema_notes() -> dict:
    """人工维护的关系/属性语义说明。缺失也能跑，只是模型选关系时更容易猜错。"""
    if not _NOTES.exists():
        return {}
    try:
        return json.loads(_NOTES.read_text("utf-8"))
    except json.JSONDecodeError:
        return {}


@dataclass
class GraphSchema:
    labels: list[str] = field(default_factory=list)
    rel_types: list[str] = field(default_factory=list)
    # (起点 label, 关系, 终点 label)
    triples: list[tuple[str, str, str]] = field(default_factory=list)
    properties: dict[str, list[str]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    # -------------------------------------------------------------- 查询辅助

    def all_properties(self) -> set[str]:
        out: set[str] = set()
        for props in self.properties.values():
            out.update(props)
        return out

    def targets_of(self, rel: str) -> list[str]:
        return sorted({e for _, r, e in self.triples if r == rel})

    def rel_between(self, start: str, end: str) -> list[str]:
        return sorted({r for s, r, e in self.triples if s == start and e == end})

    def fingerprint(self) -> str:
        """schema 变了缓存就该失效。用它做缓存 key 的一部分。"""
        import hashlib

        blob = json.dumps(self.to_json(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    # -------------------------------------------------------------- 渲染

    def to_prompt(self) -> str:
        """渲染成给 LLM 看的 schema 描述。

        自省只能给出结构，给不出语义。`diseaseDrugRelation` 和
        `diseaseRecommendDrugRelation` 光看名字模型分不出区别，实测就选错过。
        所以叠一层人工维护的关系说明（data/schema_notes.json）补上这半边信息。
        """
        notes = load_schema_notes()
        rel_notes = notes.get("relations", {})
        prop_notes = notes.get("properties", {})

        lines = ["【节点类型】"]
        for label in self.labels:
            props = []
            for p in self.properties.get(label, []):
                desc = prop_notes.get(f"{label}.{p}")
                props.append(f"{p}({desc})" if desc else p)
            lines.append(
                f"  ({label})  属性: {', '.join(props)}  数量: {self.counts.get(label, '?')}"
            )
        lines.append("【关系（方向严格按下表，不要反向书写）】")
        for s, r, e in self.triples:
            note = rel_notes.get(r)
            lines.append(f"  (:{s})-[:{r}]->(:{e})" + (f"\n      # {note}" if note else ""))
        return "\n".join(lines)

    # -------------------------------------------------------------- 序列化

    def to_json(self) -> dict:
        return {
            "labels": self.labels,
            "rel_types": self.rel_types,
            "triples": [list(t) for t in self.triples],
            "properties": self.properties,
            "counts": self.counts,
        }

    @classmethod
    def from_json(cls, d: dict) -> "GraphSchema":
        return cls(
            labels=list(d["labels"]),
            rel_types=list(d["rel_types"]),
            triples=[tuple(t) for t in d["triples"]],
            properties={k: list(v) for k, v in d["properties"].items()},
            counts=dict(d["counts"]),
        )

    @classmethod
    def from_cache(cls, path: Path) -> "GraphSchema | None":
        if not path.exists():
            return None
        try:
            return cls.from_json(json.loads(path.read_text("utf-8")))
        except (json.JSONDecodeError, KeyError):
            return None
