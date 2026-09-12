"""合并同名重复节点。

为什么会有重复：初版导入脚本写的是
    MERGE (n:disease {name:..., desc:..., cause:..., ...})
MERGE 拿花括号里**全部**属性当唯一键，所以源数据里同名但描述不同的两条记录
（medical.json 里「胎膜早破」就有两条，_id 不同、desc 一长一短）会各建一个节点。
后果是查询按 name 匹配时会拿到两份结果，而且唯一约束根本建不上。

合并策略（不丢信息）：
  * 保留关系最多的那个节点做主节点；
  * 属性逐个比对，主节点为空就用副本的，都非空则保留更长的那个（一般是更完整的描述）；
  * 副本的所有出边入边都 MERGE 到主节点上，再 DETACH DELETE 副本。

默认只报告不动手。确认无误后加 --apply 才真正写库。

    python -m scripts.dedupe                 # 全库扫描，只报告
    python -m scripts.dedupe --label disease # 只看某一类
    python -m scripts.dedupe --apply         # 真的合并
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graph import GraphStore  # noqa: E402


def duplicates(graph: GraphStore, label: str) -> list[str]:
    rows = graph._read_internal(
        f"MATCH (n:`{label}`) WITH n.name AS nm, count(*) AS c "
        f"WHERE c > 1 RETURN nm ORDER BY c DESC"
    )
    return [r["nm"] for r in rows]


def group(graph: GraphStore, label: str, name: str) -> list[dict]:
    """同名节点，按关系数从多到少排序，第一个就是主节点。"""
    return graph._read_internal(
        f"MATCH (n:`{label}` {{name: $name}}) "
        "RETURN elementId(n) AS id, properties(n) AS props, "
        "  size([(n)-[]->() | 1]) AS out, size([(n)<-[]-() | 1]) AS incoming "
        "ORDER BY out + incoming DESC, id",
        {"name": name},
    )


def merged_props(keep: dict, dups: list[dict]) -> dict:
    """主节点缺的补上，都有的保留更长的那个。"""
    out = dict(keep)
    for d in dups:
        for k, v in d.items():
            if not isinstance(v, str):
                continue
            current = out.get(k)
            if not current or (isinstance(current, str) and len(v) > len(current)):
                out[k] = v
    return out


def merge_one(graph: GraphStore, label: str, name: str, rel_types: list[str], apply: bool) -> int:
    nodes = group(graph, label, name)
    if len(nodes) < 2:
        return 0
    keep, dups = nodes[0], nodes[1:]
    print(f"  「{name}」{len(nodes)} 个节点 -> 保留 {keep['id']}"
          f"（{keep['out']} 出边 / {keep['incoming']} 入边）")
    for d in dups:
        print(f"      合并 {d['id']}（{d['out']} 出边 / {d['incoming']} 入边）")

    if not apply:
        return len(dups)

    props = merged_props(keep["props"], [d["props"] for d in dups])
    graph._write(
        "MATCH (k) WHERE elementId(k) = $id SET k += $props",
        {"id": keep["id"], "props": props},
    )
    for d in dups:
        for rel in rel_types:
            graph._write(
                f"MATCH (k) WHERE elementId(k) = $keep "
                f"MATCH (d)-[:`{rel}`]->(x) WHERE elementId(d) = $dup "
                f"MERGE (k)-[:`{rel}`]->(x)",
                {"keep": keep["id"], "dup": d["id"]},
            )
            graph._write(
                f"MATCH (k) WHERE elementId(k) = $keep "
                f"MATCH (x)-[:`{rel}`]->(d) WHERE elementId(d) = $dup "
                f"MERGE (x)-[:`{rel}`]->(k)",
                {"keep": keep["id"], "dup": d["id"]},
            )
        graph._write("MATCH (d) WHERE elementId(d) = $id DETACH DELETE d", {"id": d["id"]})
    return len(dups)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", help="只处理某一类实体，默认全部")
    ap.add_argument("--apply", action="store_true", help="真正写库。不加只报告")
    args = ap.parse_args()

    with GraphStore() as graph:
        graph.verify()
        schema = graph.schema()
        labels = [args.label] if args.label else schema.labels
        rel_types = schema.rel_types

        before = graph._read_internal("MATCH (n) RETURN count(n) AS c")[0]["c"]
        total = 0
        for label in labels:
            names = duplicates(graph, label)
            if not names:
                continue
            print(f"{label}: {len(names)} 个名字有重复")
            for name in names:
                total += merge_one(graph, label, name, rel_types, args.apply)

        if total == 0:
            print("没有发现重复节点。")
            return 0
        if not args.apply:
            print(f"\n共 {total} 个冗余节点。这是**只读预演**，没有改动数据库。")
            print("确认无误后加 --apply 执行合并。")
            return 0

        after = graph._read_internal("MATCH (n) RETURN count(n) AS c")[0]["c"]
        print(f"\n合并完成：{before} -> {after} 节点（-{before - after}）")
        graph.schema(refresh=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
