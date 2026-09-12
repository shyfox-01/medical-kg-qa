"""从 medical.json 重建知识图谱。

相对初版（legacy/medical data loading.py）修了四个问题：

1. **MERGE 键错了**：初版写 `MERGE (n:disease {name:..., desc:..., cause:...})`，
   MERGE 会拿花括号里**全部**属性做唯一键，同一个疾病只要有一个字段有差异就会
   多建一个节点。正确写法是 `MERGE (n:disease {name:$name}) SET n += $props`。
2. **字符串拼 Cypher**：初版用 `value.replace("'", "")` 当转义，既篡改了数据
   （病名里的引号被吃掉），又留着注入面。改成参数化查询。
3. **逐条提交**：8808 条疾病 × 9 类关系 ≈ 23 万次单独的 `graph.run`，
   跑一次要几十分钟。改成 UNWIND 批量，一批 1000 条。
4. **`except: pass` 吞异常**：初版任何一条写失败都静默跳过，
   最后根本不知道图谱缺了多少数据。改成计数 + 抽样打印。

顺带把初版丢掉的字段补进来：category（疾病分类）、drug_detail（具体药品）、
do_eat（推荐食谱）、yibao_status（医保）。

用法：
    python -m scripts.load_kg --dry-run          # 只解析统计，不写库
    python -m scripts.load_kg --limit 200        # 先拿 200 条试跑
    python -m scripts.load_kg                    # 全量
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from neo4j.exceptions import Neo4jError
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.graph import GraphStore  # noqa: E402

# v2 是原项目的子目录，47MB 的 medical.json 没必要复制一份 ——
# settings 会先看本目录、再看上一级。
DATA = Path(settings.medical_json)
BATCH = 1000

DISEASE_PROPS = [
    "desc", "prevent", "cause", "get_prob", "get_way",
    "cure_lasttime", "cured_prob", "cost_money", "yibao_status",
]

# 原始字段 -> (目标节点 label, 关系类型)。保持和已建好的图谱同名，避免 schema 分叉。
RELATIONS = {
    "cure_department": ("department", "diseaseDepartmentRelations"),
    "symptom": ("symptom", "diseaseSymptomRelation"),
    "cure_way": ("cureWay", "diseaseCureWayRelation"),
    "check": ("check", "diseaseCheckRelation"),
    "common_drug": ("drug", "diseaseDrugRelation"),
    "easy_get": ("crowd", "diseaseCrowdRelation"),
    "recommand_eat": ("food", "diseaseSuitableFoodRelation"),
    "not_eat": ("food", "diseaseTabooFoodRelation"),
    "acompany": ("disease", "diseaseDiseaseRelation"),
    # ↓ 初版没用上的字段
    "category": ("category", "diseaseCategoryRelation"),
    "recommand_drug": ("drug", "diseaseRecommendDrugRelation"),
    "do_eat": ("food", "diseaseRecommendRecipeRelation"),
}


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def parse(path: Path, limit: int | None) -> tuple[list[dict], dict[str, set], dict[str, list]]:
    diseases: list[dict] = []
    entities: dict[str, set] = defaultdict(set)
    relations: dict[str, list] = defaultdict(list)
    bad = 0

    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(tqdm(f, desc="解析", ncols=80)):
            if limit and i >= limit:
                break
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            name = str(row.get("name", "")).strip()
            if not name:
                bad += 1
                continue

            diseases.append(
                {
                    "name": name,
                    "props": {k: str(row.get(k, "")).strip() for k in DISEASE_PROPS},
                }
            )
            for field, (label, rel) in RELATIONS.items():
                for value in as_list(row.get(field)):
                    if label != "disease":
                        entities[label].add(value)
                    relations[rel].append({"s": name, "e": value, "_label": label})

    if bad:
        print(f"警告：{bad} 行解析失败或缺 name，已跳过（初版这里是静默 pass）")
    return diseases, entities, relations


def find_duplicates(graph: GraphStore, label: str, limit: int = 10) -> list[tuple[str, int]]:
    rows = graph._read_internal(
        f"MATCH (n:`{label}`) WITH n.name AS nm, count(*) AS c WHERE c > 1 "
        f"RETURN nm, c ORDER BY c DESC LIMIT {limit}"
    )
    return [(r["nm"], r["c"]) for r in rows]


def ensure_keys(graph: GraphStore, labels: set[str]) -> None:
    """给每个 label 的 name 建唯一约束，建不上就退回普通索引。

    两种建不上的情况都真实遇到过：
      * 该 (label, name) 上已有普通索引 —— 撤掉重建成约束；
      * 库里已经存在同名重复节点 —— 说明历史数据脏了，这里只报告不擅自删点，
        清理交给 `scripts/dedupe.py`，因为合并节点是不可逆操作。
    """
    for label in sorted(labels):
        constraint = (
            f"CREATE CONSTRAINT c_{label}_name IF NOT EXISTS "
            f"FOR (n:`{label}`) REQUIRE n.name IS UNIQUE"
        )
        try:
            graph._write(constraint)
            continue
        except Neo4jError as e:
            msg = str(e)
            if "IndexAlreadyExists" in msg:
                print(f"  {label}: 已有普通索引，替换为唯一约束")
                graph._write(f"DROP INDEX idx_{label}_name IF EXISTS")
                graph._write(constraint)
                continue
            if "ConstraintCreationFailed" not in msg and "ConstraintViolation" not in msg:
                raise

        dups = find_duplicates(graph, label)
        print(f"  ! {label}: 存在同名重复节点，无法建唯一约束，退回普通索引")
        for name, count in dups:
            print(f"      「{name}」x{count}")
        print(f"      清理请跑：python -m scripts.dedupe --label {label}")
        graph._write(
            f"CREATE INDEX idx_{label}_name IF NOT EXISTS FOR (n:`{label}`) ON (n.name)"
        )


def load(graph: GraphStore, diseases, entities, relations) -> None:
    # 唯一约束顺带把 name 索引也建了，MERGE 才不会退化成全表扫描
    ensure_keys(graph, {"disease"} | set(entities))

    print(f"\n写入 disease: {len(diseases)}")
    for i in tqdm(range(0, len(diseases), BATCH), ncols=80):
        graph._write(
            "UNWIND $rows AS row "
            "MERGE (n:disease {name: row.name}) "
            "SET n += row.props",
            {"rows": diseases[i : i + BATCH]},
        )

    for label, names in entities.items():
        rows = [{"name": n} for n in sorted(names)]
        print(f"写入 {label}: {len(rows)}")
        for i in tqdm(range(0, len(rows), BATCH), ncols=80):
            graph._write(
                f"UNWIND $rows AS row MERGE (n:`{label}` {{name: row.name}})",
                {"rows": rows[i : i + BATCH]},
            )

    for rel, items in relations.items():
        label = items[0]["_label"]
        print(f"写入关系 {rel}: {len(items)}")
        for i in tqdm(range(0, len(items), BATCH), ncols=80):
            graph._write(
                f"UNWIND $rows AS row "
                f"MATCH (s:disease {{name: row.s}}), (e:`{label}` {{name: row.e}}) "
                f"MERGE (s)-[:`{rel}`]->(e)",
                {"rows": items[i : i + BATCH]},
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA))
    ap.add_argument("--limit", type=int, help="只处理前 N 条，用于试跑")
    ap.add_argument("--dry-run", action="store_true", help="只解析统计，不连数据库")
    args = ap.parse_args()

    path = Path(args.data)
    if not path.exists():
        print(
            f"数据集不存在：{path}\n\n"
            "medical.json 不随本仓库分发（45MB，且上游声明请勿商用）。下载：\n"
            "  curl -L -o medical.json https://raw.githubusercontent.com/"
            "liuhuanyong/QASystemOnMedicalKG/master/data/medical.json\n"
            "放到仓库根目录即可，或用 --data <路径> 指定。详见 NOTICE.md。",
            file=sys.stderr,
        )
        return 2

    diseases, entities, relations = parse(path, args.limit)
    print(f"\n疾病 {len(diseases)}")
    for label, names in sorted(entities.items()):
        print(f"  {label:<10} {len(names)}")
    print("关系：")
    for rel, items in sorted(relations.items()):
        print(f"  {rel:<32} {len(items)}")

    if args.dry_run:
        print("\n--dry-run：没有写入数据库。")
        return 0

    with GraphStore() as graph:
        graph.verify()
        load(graph, diseases, entities, relations)
        graph.schema(refresh=True)
        graph.ensure_indexes()
    print("\n完成。schema 缓存已刷新。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
