"""命令行入口。

  python -m app.cli                     # 交互问答（多轮，支持指代追问）
  python -m app.cli -q "肺炎有什么症状"   # 单次提问
  python -m app.cli --selftest          # 不需要 API key，只测图谱层 / 校验闸 / 安全闸
  python -m app.cli --mock -q "..."     # 不需要 API key，用假 LLM 跑通整条链路
  python -m app.cli --doctor            # 环境体检：连通性、索引、别名表、配置
  python -m app.cli --no-fast-path -q ..# 关掉模板快路径，用于做 A/B 对照

交互模式里：
  :trace   切换过程显示        :reset   清空对话记忆（换话题）
  :cypher  直接查图谱          :config  打印当前配置（密钥已脱敏）
  :cache   缓存统计            q        退出
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from .cache import TTLCache
from .config import reload_settings, settings
from .cypher_guard import CypherRejected
from .entity_linker import EntityLinker
from .graph import GraphStore
from .session import Conversation

# driver 会把 Neo4j 的 warning 通知打到 stderr，问答时太吵
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)


def _banner(graph: GraphStore) -> None:
    s = graph.schema()
    total = sum(s.counts.values())
    flags = []
    if settings.fast_path:
        flags.append("模板快路径")
    if settings.safety:
        flags.append("安全闸")
    if settings.history_turns:
        flags.append(f"多轮记忆x{settings.history_turns}")
    print(
        f"医疗知识图谱问答 v2  |  {total} 节点 / {len(s.rel_types)} 类关系 / "
        f"模型 {settings.llm_model}  |  {' · '.join(flags) or '全部关闭'}"
    )
    print("输入问题回车提问。`:trace` 过程显示，`:reset` 换话题，`:cypher <语句>` 直接查图谱，`q` 退出。\n")


def _print_result(res, show_trace: bool) -> None:
    if show_trace:
        print("\n--- 过程 ---")
        print(res.trace())
    print("\n--- 回答 ---")
    print(res.answer)
    tags = [f"路由={res.route}"]
    if res.intent:
        tags.append(f"意图={res.intent}")
    if res.safety_categories:
        tags.append(f"安全={res.safety_level}:{'/'.join(res.safety_categories)}")
    if res.truncated:
        tags.append("结果已截断")
    print(
        f"\n[{' · '.join(tags)} | {res.attempts} 次生成尝试 | "
        f"总耗时 {res.total_seconds:.2f}s | {res.usage}]"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="医疗知识图谱问答系统 v2")
    ap.add_argument("-q", "--question", help="单次提问后退出")
    ap.add_argument("--trace", action="store_true", help="显示中间过程")
    ap.add_argument("--selftest", action="store_true", help="只检查本地各层，不调用 LLM")
    ap.add_argument("--doctor", action="store_true", help="环境体检")
    ap.add_argument("--mock", action="store_true", help="用假 LLM 跑通链路，不需要 API key")
    ap.add_argument("--refresh-schema", action="store_true", help="重新自省 schema 缓存")
    ap.add_argument("--ensure-indexes", action="store_true", help="补建缺失的索引")
    ap.add_argument("--no-fast-path", action="store_true", help="关掉模板快路径（A/B 对照用）")
    ap.add_argument("--no-safety", action="store_true", help="关掉医疗安全闸（A/B 对照用）")
    ap.add_argument("--no-cache", action="store_true", help="关掉结果缓存")
    args = ap.parse_args(argv)

    # 命令行开关覆盖 .env，方便一条命令跑对照实验
    if args.no_fast_path:
        os.environ["FAST_PATH"] = "false"
    if args.no_safety:
        os.environ["SAFETY"] = "false"
    if args.no_cache:
        os.environ["CACHE"] = "false"
    reload_settings()

    try:
        graph = GraphStore()
        graph.verify()
    except Exception as e:
        print(f"连不上 Neo4j：{e}\n请先启动数据库（见 README 的「启动」一节）。", file=sys.stderr)
        return 2

    with graph:
        if args.refresh_schema:
            graph.schema(refresh=True)
            print("schema 缓存已刷新。")
        if args.ensure_indexes:
            print("已确保索引：", graph.ensure_indexes())
        if args.doctor:
            return _doctor(graph)
        if args.selftest:
            return _selftest(graph)

        print("加载实体索引…", end="", flush=True)
        linker = EntityLinker(graph.all_names())
        print(" 完成。")

        if args.mock:
            from ._fake_llm import FakeLLM

            llm = FakeLLM()
        else:
            from .llm import LLMClient

            try:
                llm = LLMClient()
            except RuntimeError as e:
                print(f"\n{e}", file=sys.stderr)
                return 2

        from .text2cypher import Text2CypherPipeline

        cache = TTLCache(ttl=settings.cache_ttl_s) if settings.cache_enabled else None
        conversation = Conversation(max_turns=settings.history_turns)
        pipe = Text2CypherPipeline(graph, llm, linker, conversation, cache)

        if args.question:
            _print_result(pipe.answer(args.question), args.trace or settings.trace)
            return 0

        _banner(graph)
        show_trace = args.trace or settings.trace
        while True:
            try:
                q = input("问> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if q in ("q", "quit", "exit"):
                break
            if not q:
                continue
            if q == ":trace":
                show_trace = not show_trace
                print(f"过程显示：{'开' if show_trace else '关'}")
                continue
            if q == ":reset":
                conversation.reset()
                print("对话记忆已清空。")
                continue
            if q == ":config":
                for k, v in settings.redacted().items():
                    print(f"  {k:18} {v}")
                continue
            if q == ":cache":
                print(f"  {cache.stats() if cache else '缓存已关闭'}")
                continue
            if q.startswith(":cypher "):
                try:
                    r = graph.run_generated(q[8:])
                    print(f"{r.stmt}\n-> {len(r.rows)} 行 / {r.seconds * 1000:.0f}ms"
                          + (f" | 改写：{'；'.join(r.rewrites)}" if r.rewrites else ""))
                    for row in r.rows[:10]:
                        print("  ", row)
                except CypherRejected as e:
                    print(f"被校验器拒绝：{e}")
                continue
            try:
                _print_result(pipe.answer(q), show_trace)
            except Exception as e:  # noqa: BLE001 - REPL 不应因单次失败退出
                print(f"出错：{e!r}")
            print()
    return 0


# ---------------------------------------------------------------- 自检

_GUARD_CASES = [
    ("正常查询", "MATCH (d:disease)-[:diseaseSymptomRelation]->(s:symptom) "
                 "WHERE d.name CONTAINS '肺炎' RETURN d.name, s.name", True),
    ("字面量里的分号", 'MATCH (d:disease) WHERE d.name CONTAINS ";" RETURN d.name', True),
    ("字面量里的 SET", 'MATCH (f:food) WHERE f.name CONTAINS "SET" RETURN f.name', True),
    ("字面量里的 //", 'MATCH (d:disease) WHERE d.desc CONTAINS "http://x" RETURN d.name', True),
    ("只读子查询", 'MATCH (d:disease) WHERE d.name = "感冒" '
                   'CALL { MATCH (x:drug) RETURN x.name AS n LIMIT 3 } RETURN d.name, n', True),
    ("删库注入", "MATCH (n) DETACH DELETE n RETURN 1", False),
    ("多语句注入", "MATCH (d:disease) RETURN d.name LIMIT 1; DROP INDEX idx_disease_name", False),
    ("编造关系", "MATCH (d:disease)-[:hasSymptom]->(s:symptom) RETURN s.name", False),
    ("属性拼错", "MATCH (d:disease) RETURN d.disease_name LIMIT 5", False),
    ("语法错误", "MATCH (d:disease RETURN d.name", False),
    ("存储过程", "CALL dbms.components() YIELD name RETURN name", False),
    ("apoc 函数", "MATCH (d:disease) RETURN apoc.convert.toJson(d) LIMIT 5", False),
    ("SHOW 管理语句", "SHOW INDEXES YIELD name RETURN name", False),
    ("无界变长路径", "MATCH (d:disease)-[*]->(x) RETURN x.name", False),
    ("超跳数", "MATCH (d:disease)-[:diseaseDiseaseRelation*1..9]->(x:disease) RETURN x.name", False),
    ("裸扫无 LIMIT", "MATCH (d:disease) RETURN d.name", True),
]

_SAFETY_CASES = [
    ("感冒有什么症状？", ()),
    ("糖尿病人不能吃什么？", ()),
    ("小儿肺炎有什么症状", ()),
    ("二甲双胍一次吃几片", ("dosage",)),
    ("胸口剧烈疼痛还冒冷汗", ("emergency",)),
    ("孕妇感冒能吃什么药", ("special_population",)),
    ("我不想活了", ("self_harm",)),
]


def _selftest(graph: GraphStore) -> int:
    from . import safety as safety_mod
    from .planner import plan as make_plan

    print("== schema 自省 ==")
    print(graph.schema().to_prompt())

    print("\n== 校验闸门 ==")
    passed = 0
    for tag, q, should_pass in _GUARD_CASES:
        try:
            graph.validate(q)
            ok = should_pass
            print(f"  {'v' if ok else 'x'} {tag}: 放行")
        except CypherRejected as e:
            ok = not should_pass
            print(f"  {'v' if ok else 'x'} {tag}: 拦截（{str(e)[:56]}…）")
        passed += ok

    print("\n== 医疗安全闸 ==")
    safety_ok = 0
    for q, want in _SAFETY_CASES:
        got = safety_mod.assess(q).categories
        ok = set(got) == set(want)
        safety_ok += ok
        print(f"  {'v' if ok else 'x'} {q[:22]:<24} -> {list(got) or '正常'}")

    print("\n== 实体链接 ==")
    linker = EntityLinker(graph.all_names())
    for q in ["糖尿病人能吃西瓜吗", "最近老是头疼还发烧", "拉肚子还胃里烧得慌", "肺炎支原体感染"]:
        ms = linker.scan(q)
        print(f"  {q}")
        print("   ", linker.describe(ms).strip().replace("\n", "\n    "))

    print("\n== 模板快路径 ==")
    fast = 0
    probes = ["感冒有什么症状", "高血压挂什么科", "糖尿病人不能吃什么", "胃炎不治会引起什么病",
              "呼吸内科一共负责多少种疾病", "今天天气怎么样"]
    for q in probes:
        p = make_plan(q, linker)
        fast += p is not None
        print(f"  {q:<24} -> {p.intent if p else '交给 LLM'}")

    print("\n== 别名表体检 ==")
    audit = linker.audit_aliases()
    print(f"  生效 {len(audit['valid'])} 条")
    for tag, label in (("redundant", "冗余，key 本身就是图谱节点"), ("broken", "失效，目标不在图谱")):
        if audit[tag]:
            print(f"  ! {len(audit[tag])} 条{label}：")
            for k, v in audit[tag]:
                print(f"      {k} -> {v}")
    alias_ok = not audit["redundant"] and not audit["broken"]

    print(
        f"\n校验闸门 {passed}/{len(_GUARD_CASES)}｜安全闸 {safety_ok}/{len(_SAFETY_CASES)}"
        f"｜快路径命中 {fast}/{len(probes)}｜别名表{'干净' if alias_ok else '需要清理'}"
    )
    good = passed == len(_GUARD_CASES) and safety_ok == len(_SAFETY_CASES) and alias_ok
    return 0 if good else 1


def _doctor(graph: GraphStore) -> int:
    print("== 配置 ==")
    for k, v in settings.redacted().items():
        print(f"  {k:18} {v}")

    print("\n== 图谱 ==")
    n, r = graph.fingerprint()
    s = graph.schema()
    print(f"  {n} 节点 / {r} 关系 / {len(s.labels)} 类节点 / {len(s.rel_types)} 类关系")
    print(f"  schema 指纹 {s.fingerprint()}")

    print("\n== 索引 ==")
    bad = 0
    for row in graph.index_report():
        state = row["state"]
        flag = "v" if state == "ONLINE" else "x"
        bad += state != "ONLINE"
        print(f"  {flag} {row['name']:<22} {row['type']:<9} {state:<9} "
              f"{row['labelsOrTypes'] or ''} {row['properties'] or ''}")
    missing = set(s.labels) - graph.indexed_labels()
    if missing:
        bad += 1
        print(f"  ! 这些 label 的 name 没有索引（按名查会全表扫描）：{sorted(missing)}")
        print("    修复：python -m app.cli --ensure-indexes")

    print("\n== 全文兜底 ==")
    hits = graph.fulltext_disease("咳嗽发烧", 3)
    if graph.fulltext_available:
        print(f"  v ft_disease -> {[h['name'] for h in hits]}")
    else:
        bad += 1
        print("  x ft_disease 不可用（索引缺失或处于 FAILED 状态）")
        print("    修复：python -m app.cli --ensure-indexes")

    print("\n== 数据质量 ==")
    warn = 0
    dups = graph._read_internal(
        "MATCH (n:disease) WITH n.name AS nm, count(*) AS c WHERE c > 1 "
        "RETURN nm, c ORDER BY c DESC LIMIT 5"
    )
    if dups:
        warn += 1
        print(f"  ! {len(dups)} 个同名重复的 disease 节点：{[(d['nm'], d['c']) for d in dups]}")
        print("    源数据本身就有同名记录，属于已知问题，不影响问答。")
        print("    清理：python -m scripts.dedupe --label disease （默认只读预演）")
    else:
        print("  v disease 无同名重复")

    print("\n== 关系语义说明 ==")
    # schema 自省能拿到结构，拿不到语义。图谱里加了新关系却忘了写说明，
    # 表现出来是"模型偶尔选错关系"，很难定位到根因是 prompt 里少了一句话。
    from .planner import _REL_INTENTS
    from .schema import load_schema_notes

    notes = load_schema_notes().get("relations", {})
    missing_notes = [r for r in s.rel_types if r not in notes]
    if missing_notes:
        bad += 1
        print(f"  ! {len(missing_notes)} 条关系没有语义说明，模型只能靠名字猜：{missing_notes}")
        print("    补充：data/schema_notes.json")
    else:
        print(f"  v {len(s.rel_types)} 条关系全部有说明")
    covered = {r for rels, _, _ in _REL_INTENTS.values() for r in rels}
    uncovered = sorted(set(s.rel_types) - covered)
    print(f"  模板快路径覆盖 {len(covered)}/{len(s.rel_types)} 条关系"
          + (f"，未覆盖（走 LLM）：{uncovered}" if uncovered else ""))

    print("\n== 别名表 ==")
    audit = EntityLinker(graph.all_names()).audit_aliases()
    print(f"  生效 {len(audit['valid'])} / 冗余 {len(audit['redundant'])} / 失效 {len(audit['broken'])}")
    bad += bool(audit["redundant"] or audit["broken"])

    verdict = "体检通过。" if not bad else f"发现 {bad} 处需要修的问题，见上。"
    if warn:
        verdict += f"另有 {warn} 处警告（不影响运行）。"
    print("\n" + verdict)
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
