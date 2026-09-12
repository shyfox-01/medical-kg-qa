"""Cypher 静态校验闸。纯函数、不碰数据库，因此可以被单测完整覆盖。

v1 的做法是直接拿正则去扫原始语句。演示里够用，但有两类真实缺陷：

**假阳性** —— 正则看不懂字符串字面量。
    只要用户问的词里带分号，或者食物名里出现 SET / CREATE 这样的字母序列，
    v1 的写操作黑名单就会把一条完全合法的只读查询拒掉。

**假阴性** —— 同样是因为看不懂词法结构。
    v1 先用注释正则把 `//...` 剥掉，而那个正则本身不认识字符串：
    一句 `WHERE d.desc CONTAINS "http://x"` 里的 `//` 会被当成行注释，
    把后面半句连同 RETURN 一起吃掉，剩下的残句再去做黑名单匹配 ——
    **校验对象和执行对象不是同一条语句，这是校验器最不该犯的错。**

所以 v2 先做一遍词法扫描：注释、字符串、反引号标识符各按 Cypher 的规则识别，
字符串内容替换成等长空格（下标一一对应，方便回写原文），注释替换成空格。
后面所有规则都跑在这份"骨架"上，检查的和执行的就是同一条语句。

在此之上补了 v1 没有的四道：
  * LIMIT 数值封顶（v1 只看结尾有没有 LIMIT，`LIMIT 100000` 照样放行）
  * 变长路径 `[*]` 上限（33 万条关系上的无界遍历 = 一句话打爆服务器）
  * 属性名白名单（离线就能拦掉 `d.disease_name`，不必等数据库的 EXPLAIN 警告）
  * 放行只读 `CALL { ... }` 子查询，但仍禁掉所有存储过程与命名空间函数
    （v1 一刀切禁 CALL，把 UNION 型子查询这种正当写法也误伤了）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schema import GraphSchema


class CypherRejected(Exception):
    """静态校验不通过。消息会原样回灌给 LLM 让它自己改，所以要写得可操作。"""


@dataclass
class Verdict:
    stmt: str                                  # 实际可执行的语句（已补 / 已封顶 LIMIT）
    limit: int | None = None                   # 生效的行数上限，供"结果是否被截断"判断
    warnings: list[str] = field(default_factory=list)
    rewrites: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 词法扫描

def lex_skeleton(text: str) -> str:
    """把注释和字符串字面量抹成等长空格，返回与原文等长的骨架。

    等长是关键：后续规则在骨架上定位到的下标，可以直接拿去改写原文。
    反引号标识符的内容要保留 —— MATCH (n:`disease`) 里的 label 还得校验。
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        # 行注释
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
            continue
        # 块注释
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            while i < n:
                closing = text[i] == "*" and i + 1 < n and text[i + 1] == "/"
                out[i] = " "
                i += 1
                if closing:
                    out[i] = " "
                    i += 1
                    break
            continue
        # 字符串字面量：内容抹掉，引号留着（保住语法结构）
        if ch in ("'", '"'):
            quote = ch
            i += 1
            while i < n:
                if text[i] == "\\" and i + 1 < n:
                    out[i] = " "
                    out[i + 1] = " "
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                out[i] = " "
                i += 1
            continue
        # 反引号标识符：内容保留（label / 关系名 / 属性名可能被反引号包起来）
        if ch == "`":
            i += 1
            while i < n and text[i] != "`":
                i += 1
            i += 1
            continue
        i += 1
    return "".join(out)


# ---------------------------------------------------------------- 规则

_WRITE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b", re.IGNORECASE
)
_ADMIN = re.compile(
    r"\b(SHOW|TERMINATE|ALTER|GRANT|DENY|REVOKE|ENABLE|RENAME|START\s+DATABASE|"
    r"STOP\s+DATABASE|USE)\b",
    re.IGNORECASE,
)
_IN_TRANSACTIONS = re.compile(r"\bIN\s+TRANSACTIONS?\b", re.IGNORECASE)
_EXPLAIN_PREFIX = re.compile(r"^\s*(EXPLAIN|PROFILE)\b", re.IGNORECASE)
_RETURN = re.compile(r"\bRETURN\b", re.IGNORECASE)
_LIMIT = re.compile(r"\bLIMIT\b\s+(\d+)", re.IGNORECASE)
_TRAILING_LIMIT = re.compile(r"\bLIMIT\b\s+(\d+)\s*$", re.IGNORECASE)
_LIMIT_NON_NUMERIC = re.compile(r"\bLIMIT\b\s*(?![\s\d])", re.IGNORECASE)
# 命名空间函数 / 过程：apoc.* db.* dbms.* gds.* —— 既有写操作也有信息泄露面
_NAMESPACE = re.compile(
    r"\b(apoc|db|dbms|gds|spatial|algo|genai|vector|internal)\s*\.\s*[A-Za-z_]", re.IGNORECASE
)
# 关系括号里的变长路径量词：[*] [*2] [*1..3] [*..5] [*2..]
_REL_BRACKET = re.compile(r"\[([^\]]*)\]")
_VAR_LEN = re.compile(r"\*\s*(\d*)\s*(\.\.)?\s*(\d*)")
# 只在 ( ) 和 [ ] 里面找 label / 关系名，避免把 RETURN {a: b} 这类 map 字面量误判
_PATTERN_BODY = re.compile(r"[(\[]([^)\]]*)")
_TYPE_TOKEN = re.compile(r"[:|]\s*`?([A-Za-z_][A-Za-z0-9_]*)`?")
# 属性访问：变量名必须以字母 / 下划线开头，才不会把 1.5 这种小数当成属性
_PROP_ACCESS = re.compile(r"(?<![\w.$])([A-Za-z_]\w*)\s*\.\s*`?([A-Za-z_]\w*)`?")
_UNLABELED_MATCH = re.compile(r"\bMATCH\s*\(\s*[A-Za-z_]\w*\s*\)", re.IGNORECASE)


def _pattern_tokens(code: str) -> set[str]:
    tokens: set[str] = set()
    for body in _PATTERN_BODY.findall(code):
        body = body.split("{", 1)[0]  # 属性 map 里没有 label
        tokens.update(_TYPE_TOKEN.findall(body))
    return tokens


def _check_var_length(code: str, max_hops: int) -> None:
    for m in _REL_BRACKET.finditer(code):
        body = m.group(1)
        if "*" not in body:
            continue
        q = _VAR_LEN.search(body)
        if not q:
            continue
        lo, dots, hi = q.group(1), q.group(2), q.group(3)
        if not hi:  # [*] / [*..] / [*2..] 都没有上界
            if dots or not lo:
                raise CypherRejected(
                    f"不允许无上界的变长路径 [{body}]。图里有 33 万条关系，"
                    f"无界遍历会把服务器拖死。请写明上界且不超过 {max_hops} 跳，"
                    f"例如 [:关系名*1..2]。"
                )
            hi = lo
        if int(hi) > max_hops:
            raise CypherRejected(f"变长路径最多 {max_hops} 跳，[{body}] 超了，请收窄跳数。")


def _check_call(code: str) -> None:
    """放行只读子查询 CALL { ... }，拒绝一切存储过程调用。

    CALL (n) { ... } 这种带作用域变量的新语法也一并拒掉：它是 5.23 之后才有的，
    这里保守处理，宁可让模型换个写法，也不为兼容性放松边界。
    """
    for m in re.finditer(r"\bCALL\b", code, re.IGNORECASE):
        rest = code[m.end():].lstrip()
        if rest.startswith("{"):
            continue
        nxt = rest[:40].strip() or "<语句结尾>"
        raise CypherRejected(
            f"不允许调用存储过程（CALL {nxt}）。只读子查询请写成 CALL {{ ... }}，"
            f"其余一律用 MATCH / WHERE 表达。"
        )


def _cap_limits(stmt: str, code: str, max_limit: int) -> tuple[str, int | None, list[str]]:
    """把所有 LIMIT 数值封到上限以内，并返回最终生效的行数上限。

    从右往左改写，保证前面匹配到的下标不失效。
    """
    rewrites: list[str] = []
    for m in reversed(list(_LIMIT.finditer(code))):
        value = int(m.group(1))
        if value > max_limit:
            stmt = stmt[: m.start(1)] + str(max_limit) + stmt[m.end(1):]
            rewrites.append(f"LIMIT {value} 超过上限，已封顶为 {max_limit}")
    effective = None
    if tail := _TRAILING_LIMIT.search(lex_skeleton(stmt)):
        effective = min(int(tail.group(1)), max_limit)
    return stmt, effective, rewrites


def check(
    cypher: str,
    schema: GraphSchema,
    *,
    max_limit: int = 200,
    default_limit: int = 25,
    max_path_hops: int = 3,
    check_properties: bool = True,
) -> Verdict:
    """静态校验。通过返回 Verdict，不通过抛 CypherRejected。"""
    stmt = (cypher or "").strip()
    # 结尾一个分号是不少模型的习惯，允许并剥掉；语句中间的分号才是多语句拼接
    while stmt.endswith(";"):
        stmt = stmt[:-1].rstrip()
    if not stmt:
        raise CypherRejected("空语句")

    code = lex_skeleton(stmt)
    warnings: list[str] = []

    # --- 闸 1：只允许单条、只读、非管理类语句 -------------------------------
    if ";" in code:
        raise CypherRejected("只允许一条语句，不要用 ; 拼接多条")
    if m := _EXPLAIN_PREFIX.search(code):
        raise CypherRejected(
            f"不要加 {m.group(1)} 前缀，它只返回执行计划、不返回数据。直接写查询本身。"
        )
    if m := _WRITE.search(code):
        raise CypherRejected(f"检测到写操作关键字 {m.group(0)}，本系统只允许只读查询")
    if m := _ADMIN.search(code):
        raise CypherRejected(f"不允许管理类语句 {m.group(0)}，本系统只对图数据做只读查询")
    if _IN_TRANSACTIONS.search(code):
        raise CypherRejected("不允许 IN TRANSACTIONS（它属于写入语法）")
    if m := _NAMESPACE.search(code):
        raise CypherRejected(
            f"不允许调用 {m.group(1)}.* 命名空间下的过程或函数。"
            f"图数据查询只需要 MATCH / WHERE / RETURN。"
        )
    _check_call(code)
    if not _RETURN.search(code):
        raise CypherRejected("语句必须包含 RETURN")
    if _LIMIT_NON_NUMERIC.search(code):
        raise CypherRejected("LIMIT 后面必须直接跟一个整数字面量，不要用参数或表达式")

    # --- 闸 2：结构必须真实存在 ---------------------------------------------
    known = set(schema.labels) | set(schema.rel_types)
    for token in sorted(_pattern_tokens(code)):
        if token not in known:
            raise CypherRejected(
                f"`{token}` 不是图谱里的节点类型或关系类型。"
                f"可用节点类型: {schema.labels}；可用关系: {schema.rel_types}"
            )
    if check_properties and (known_props := schema.all_properties()):
        for var, prop in _PROP_ACCESS.findall(code):
            if prop not in known_props:
                raise CypherRejected(
                    f"图谱里没有 `{prop}` 这个属性（你写的是 {var}.{prop}）。"
                    f"可用属性: {sorted(known_props)}"
                )

    # --- 闸 3：资源护栏 ------------------------------------------------------
    _check_var_length(code, max_path_hops)
    stmt, effective_limit, rewrites = _cap_limits(stmt, code, max_limit)
    if effective_limit is None:
        effective_limit = min(default_limit, max_limit)
        stmt = f"{stmt} LIMIT {effective_limit}"
        rewrites.append(f"结尾没有 LIMIT，已补 LIMIT {effective_limit}")
    if _UNLABELED_MATCH.search(code):
        warnings.append("存在不带 label 的 MATCH，会退化成全库扫描")

    return Verdict(stmt=stmt, limit=effective_limit, warnings=warnings, rewrites=rewrites)
