"""Neo4j 访问层。

三条防线（顺序不能反）：
  1. `cypher_guard.check()` 静态校验 —— 词法扫描后跑黑名单 / schema / 资源护栏；
  2. `EXPLAIN` 预编译 —— 交给数据库判语法与语义，顺带抓"属性名不存在"这类只报 warning 的坑；
  3. **只读事务** —— 数据库层兜底。已实测：在 READ 事务里执行 CREATE，
     服务端直接返回 `Neo.ClientError.Statement.AccessMode: Writing in read access mode
     not allowed`。所以前两道就算被绕过，也写不进去。

v2 相对 v1 的改动：
  * `QUERY_TIMEOUT_S` **真正生效**了。v1 里这个配置项从头到尾没有被任何代码读过，
    README 却写着有超时保护 —— 一条笛卡尔积查询能把会话挂死。现在走
    `session.begin_transaction(timeout=...)`，超时由服务端强制执行。
  * 明确区分**受信内部查询**和**LLM 生成的查询**。前者（schema 自省、全文检索）
    是本项目自己写死的语句，走 `_read_internal`；后者必须过 `run_generated`。
    v1 里两者共用一个 `_read`，容易在后续改动中把口子开大。
  * 返回结果带 `truncated` 标记：命中 LIMIT 说明结果不完整，这个事实必须传给
    回答环节，否则模型会把截断后的 25 条当成"全部"讲出去 —— 在医疗场景这是硬伤。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from neo4j import READ_ACCESS, GraphDatabase
from neo4j.exceptions import CypherSyntaxError, Neo4jError

from .config import DATA_DIR, settings
from .cypher_guard import CypherRejected, check
from .schema import GraphSchema

_CACHE = DATA_DIR / "schema_cache.json"

# 受信内部查询（schema 自省、全文检索）给宽松一点的超时，它们本来就要扫全库
_INTERNAL_TIMEOUT = 60.0


@dataclass
class QueryResult:
    rows: list[dict]
    stmt: str
    seconds: float
    limit: int | None = None
    truncated: bool = False          # 行数刚好顶到 LIMIT，结果很可能不完整
    warnings: list[str] = field(default_factory=list)
    rewrites: list[str] = field(default_factory=list)


def _notifications(summary: Any) -> list[tuple[str, str]]:
    """返回 [(分类, 描述)]。driver 5.x 给 dict，6.x 换成了 gql_status_objects，这里都兜住。"""
    out: list[tuple[str, str]] = []
    for obj in getattr(summary, "gql_status_objects", None) or []:
        cls = str(getattr(obj, "classification", "") or "")
        desc = str(getattr(obj, "status_description", "") or "")
        if desc:
            out.append((cls, desc))
    if out:
        return out
    for note in getattr(summary, "notifications", None) or []:
        if isinstance(note, dict):
            out.append((note.get("title") or "", note.get("description") or ""))
        else:
            out.append(
                (str(getattr(note, "category", "") or ""), str(getattr(note, "title", "") or ""))
            )
    return out


class GraphStore:
    def __init__(self) -> None:
        settings.require_neo4j()
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
        self._db = settings.neo4j_database
        self._schema: GraphSchema | None = None
        self._fulltext_ok: bool | None = None

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def verify(self) -> None:
        self._driver.verify_connectivity()

    # ------------------------------------------------------------------ 执行

    def _read(self, cypher: str, params: dict | None = None, timeout: float | None = None) -> list[dict]:
        """只读事务 + 服务端强制超时。写操作在这里会被数据库直接拒绝。"""
        with self._driver.session(database=self._db, default_access_mode=READ_ACCESS) as session:
            with session.begin_transaction(timeout=timeout or settings.query_timeout_s) as tx:
                rows = [r.data() for r in tx.run(cypher, params or {})]
                tx.commit()
                return rows

    def _read_internal(self, cypher: str, params: dict | None = None) -> list[dict]:
        """本项目自己写死的受信语句（schema 自省 / 全文检索）。仍然走只读事务。"""
        return self._read(cypher, params, timeout=_INTERNAL_TIMEOUT)

    def _write(self, cypher: str, params: dict | None = None) -> list[dict]:
        """仅供导入脚本 / 建索引使用。问答链路永远不会走到这里。"""
        with self._driver.session(database=self._db) as session:
            return session.execute_write(
                lambda tx: [r.data() for r in tx.run(cypher, params or {})]
            )

    # ------------------------------------------------------------- schema 自省

    def schema(self, refresh: bool = False) -> GraphSchema:
        if self._schema is not None and not refresh:
            return self._schema
        if not refresh and (cached := GraphSchema.from_cache(_CACHE)) is not None:
            self._schema = cached
            return self._schema

        labels = [
            r["label"] for r in self._read_internal("CALL db.labels() YIELD label RETURN label")
        ]
        rel_types = [
            r["relationshipType"]
            for r in self._read_internal(
                "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
            )
        ]
        triples = [
            (r["s"], r["rel"], r["e"])
            for r in self._read_internal(
                "MATCH (a)-[r]->(b) "
                "RETURN DISTINCT labels(a)[0] AS s, type(r) AS rel, labels(b)[0] AS e "
                "ORDER BY s, rel, e"
            )
        ]
        properties, counts = {}, {}
        for label in labels:
            rows = self._read_internal(
                f"MATCH (n:`{label}`) WITH n LIMIT 200 "
                "UNWIND keys(n) AS k RETURN DISTINCT k ORDER BY k"
            )
            properties[label] = [r["k"] for r in rows]
            counts[label] = self._read_internal(
                f"MATCH (n:`{label}`) RETURN count(n) AS c"
            )[0]["c"]

        self._schema = GraphSchema(labels, rel_types, triples, properties, counts)
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(
            json.dumps(self._schema.to_json(), ensure_ascii=False, indent=2), "utf-8"
        )
        return self._schema

    # ---------------------------------------------------------------- 三道闸

    def validate(self, cypher: str, params: dict | None = None):
        """静态校验 + 预编译。通过返回 Verdict（含改写后的语句），否则抛 CypherRejected。"""
        verdict = check(
            cypher,
            self.schema(),
            max_limit=settings.max_limit,
            default_limit=settings.default_limit,
            max_path_hops=settings.max_path_hops,
        )
        try:
            with self._driver.session(
                database=self._db, default_access_mode=READ_ACCESS
            ) as session:
                summary = session.run(f"EXPLAIN {verdict.stmt}", params or {}).consume()
        except CypherSyntaxError as e:
            raise CypherRejected(f"Cypher 语法错误：{e.message}") from e
        except Neo4jError as e:
            raise CypherRejected(f"Cypher 无法编译：{e.message}") from e

        # 属性名 / label 拼错时 Neo4j 只给 warning，不报错，但查出来一定是空的 —— 提前拦掉
        for classification, desc in _notifications(summary):
            upper = classification.upper()
            if "UNRECOGNIZED" in upper:
                raise CypherRejected(f"图谱中不存在该属性或标签：{desc}")
            if "PERFORMANCE" in upper:
                verdict.warnings.append(desc)
        return verdict

    def run_generated(self, cypher: str, params: dict | None = None) -> QueryResult:
        """校验后执行一条**不可信**的语句（LLM 生成的，或 CLI 里人手敲的）。"""
        verdict = self.validate(cypher, params)
        t0 = time.perf_counter()
        rows = self._read(verdict.stmt, params)
        elapsed = time.perf_counter() - t0
        return QueryResult(
            rows=rows,
            stmt=verdict.stmt,
            seconds=elapsed,
            limit=verdict.limit,
            # 行数刚好等于 LIMIT，说明后面很可能还有 —— 这个事实要一路传到回答环节
            truncated=bool(verdict.limit and len(rows) >= verdict.limit),
            warnings=verdict.warnings,
            rewrites=verdict.rewrites,
        )

    # ------------------------------------------------------------ 兜底检索

    def fulltext_disease(self, keywords: str, limit: int = 8) -> list[dict]:
        """全文检索疾病名 / 简介。

        v1 建了 `ft_disease` 这个全文索引，然后**从来没有用过**——
        索引白建，0 结果时也就只能回一句"没查到"。这里把它接上，
        作为实体链接和 Cypher 都落空之后的最后一层召回。

        注意这条语句用了 `CALL db.index.fulltext.*`，是被校验闸禁掉的写法。
        它能跑是因为**它不是 LLM 生成的**，而是本项目写死的受信语句 ——
        受信路径和不可信路径分开，正是为了这种场景。
        """
        if self._fulltext_ok is False:
            return []  # 上一次调用就失败了（索引缺失 / FAILED），不必每题都再撞一次
        query = lucene_query(keywords)
        if not query:
            return []
        try:
            rows = self._read_internal(
                "CALL db.index.fulltext.queryNodes('ft_disease', $q) YIELD node, score "
                "RETURN node.name AS name, score, "
                "  left(coalesce(node.desc, ''), 80) AS brief "
                "ORDER BY score DESC LIMIT $limit",
                {"q": query, "limit": limit * 3},
            )
        except Neo4jError:
            # 全文索引可能没建、也可能处于 FAILED 状态（这套库里就出现过）。
            # 兜底路径挂了不该让整次问答失败，记下来降级即可，--doctor 会报出来。
            self._fulltext_ok = False
            return []
        self._fulltext_ok = True
        return _drop_unrelated(keywords, rows)[:limit]

    @property
    def fulltext_available(self) -> bool | None:
        """None = 还没用过；True/False = 上次调用的结果。给 --doctor 用。"""
        return self._fulltext_ok

    # ------------------------------------------------------------ 索引 / 工具

    def index_report(self) -> list[dict]:
        return self._read_internal(
            "SHOW INDEXES YIELD name, type, state, labelsOrTypes, properties "
            "RETURN name, type, state, labelsOrTypes, properties ORDER BY name"
        )

    def indexed_labels(self) -> set[str]:
        """已经有 name 索引的 label（含唯一约束自带的那个索引）。"""
        out = set()
        for row in self.index_report():
            if row["properties"] == ["name"] and row["labelsOrTypes"]:
                out.update(row["labelsOrTypes"])
        return out

    def ensure_indexes(self) -> list[str]:
        """按 name 查是这套图谱里最热的访问模式，没索引就是 8808 次全表扫描。

        注意不能无脑 `CREATE INDEX ... IF NOT EXISTS`：唯一约束会自带一个同样的索引，
        这时再建普通索引会撞 IndexAlreadyExists。所以先查 SHOW INDEXES 再决定。
        """
        existing = self.indexed_labels()
        created = []
        for label in self.schema().labels:
            if label in existing:
                continue
            self._write(f"CREATE INDEX idx_{label}_name FOR (n:`{label}`) ON (n.name)")
            created.append(f"idx_{label}_name")
        self._write(
            "CREATE FULLTEXT INDEX ft_disease IF NOT EXISTS "
            "FOR (n:disease) ON EACH [n.name, n.desc]"
        )
        created.append("ft_disease")
        return created

    def all_names(self) -> list[tuple[str, str]]:
        """(name, label) 全量，用于实体链接建索引。"""
        rows = self._read_internal(
            "MATCH (n) WHERE n.name IS NOT NULL "
            "RETURN n.name AS name, labels(n)[0] AS label"
        )
        return [(r["name"], r["label"]) for r in rows]

    def fingerprint(self) -> tuple[int, int]:
        """(节点数, 关系数)。评测前后各取一次，确认问答链路没改动图谱。"""
        n = self._read_internal("MATCH (n) RETURN count(n) AS c")[0]["c"]
        r = self._read_internal("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
        return n, r


_CJK = r"[一-鿿]"
# 高频功能词。留在查询里只会把打分搅浑（"最近老是…"里的"老是"能匹配上一堆病名）
_STOP = set(
    "我 你 他 她 它 的 了 吗 呢 吧 是 和 与 或 会 能 要 有 在 想 就 都 也 还 又 很 太 老是 总是 "
    "一直 最近 什么 怎么 怎样 如何 可能 哪些 哪个 一个 有点 感觉 医院 医生 请问 帮我 需要 应该 "
    "大概 多少 为什么 引起 出现 导致 注意 这个 那个 这种 那种".split()
)
# Lucene 保留字符，不转义的话一个括号就让整条查询语法错
_LUCENE_SPECIAL = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')


def _cjk_windows(text: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for chunk in re.findall(rf"{_CJK}+|[A-Za-z0-9]{{2,}}", text):
        if not re.match(_CJK, chunk):
            out.append((chunk, 2))
            continue
        for size in (5, 4, 3, 2):
            for i in range(len(chunk) - size + 1):
                window = chunk[i : i + size]
                if window not in _STOP:
                    out.append((window, size))
    return out


def lucene_query(text: str, max_terms: int = 16) -> str:
    """把中文问句拼成 Lucene **短语**查询，长词权重更高。

    第一版用的是 n-gram 的 OR 检索，效果很差：Neo4j 全文索引对中文按**单字**切词，
    所以 `老是拉肚` / `是拉肚子` / `拉肚` 这些 n-gram 最后都塌缩成同一批单字，
    只是把词频灌了水 —— 一个「拉」字就能让「马拉色菌病」拿到 50 分排到第一。
    改成带引号的短语查询后要求单字相邻，精度立刻上来了，
    而且「今天北京天气怎么样」这种越界问题会干净地返回 0 条。
    """
    seen: set[str] = set()
    terms: list[str] = []
    for window, boost in sorted(_cjk_windows(text), key=lambda x: -x[1]):
        if window in seen:
            continue
        seen.add(window)
        terms.append(f'"{_LUCENE_SPECIAL.sub(r"\\\1", window)}"^{boost}')
        if len(terms) >= max_terms:
            break
    return " OR ".join(terms)


def _drop_unrelated(question: str, rows: list[dict]) -> list[dict]:
    """候选疾病名必须和问句共享一个二字片段，否则丢掉。

    Lucene 的分数是绝对值、跨查询不可比（「肺炎」的满分匹配 6.5 分，
    「老是拉肚子」的噪声匹配反而 46 分），所以没法用阈值筛。
    但"名字里得有问句出现过的两个连续汉字"这条约束又便宜又准：
    「咳嗽发烧」→「咳嗽」留下，「老是拉肚子」→「热伤风」被丢掉。
    """
    grams = {w for w, _ in _cjk_windows(question) if len(w) == 2}
    if not grams:
        return rows
    return [r for r in rows if any(g in (r.get("name") or "") for g in grams)]
