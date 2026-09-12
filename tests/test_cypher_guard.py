"""校验闸的单元测试。

重点覆盖两类 v1 会出错的场景：
  * 假阳性 —— 危险关键字出现在**字符串字面量**里，是合法查询，不该拒；
  * 假阴性 —— 注释 / 字符串把语法结构搅乱后，v1 校验的和执行的不是同一条语句。
"""
from __future__ import annotations

import pytest

from app.cypher_guard import CypherRejected, check, lex_skeleton


def ok(stmt, schema, **kw):
    return check(stmt, schema, **kw)


def rejected(stmt, schema, **kw):
    with pytest.raises(CypherRejected) as e:
        check(stmt, schema, **kw)
    return str(e.value)


# ------------------------------------------------------------------ 词法扫描

class TestLexSkeleton:
    def test_keeps_length(self):
        src = 'MATCH (d:disease) WHERE d.name = "肺炎" RETURN d.name'
        assert len(lex_skeleton(src)) == len(src)

    def test_masks_string_contents_but_keeps_quotes(self):
        out = lex_skeleton('WHERE d.name = "DELETE"')
        assert "DELETE" not in out
        assert out.count('"') == 2

    def test_masks_line_comment(self):
        assert "secret" not in lex_skeleton("MATCH (n) // secret\nRETURN n")

    def test_masks_block_comment(self):
        assert "secret" not in lex_skeleton("MATCH (n) /* secret */ RETURN n")

    def test_slashes_inside_string_are_not_a_comment(self):
        """v1 的注释正则不认识字符串，会把 `http://x` 后面的半句连同 RETURN 一起吃掉。"""
        src = 'MATCH (d:disease) WHERE d.desc CONTAINS "http://x" RETURN d.name'
        assert "RETURN" in lex_skeleton(src)

    def test_keeps_backtick_identifier(self):
        assert "disease" in lex_skeleton("MATCH (n:`disease`) RETURN n.name")

    def test_handles_escaped_quote(self):
        src = "MATCH (d:disease) WHERE d.name = 'a\\'b' RETURN d.name"
        assert "RETURN" in lex_skeleton(src)


# ------------------------------------------------------------------ 假阳性

class TestNoFalsePositives:
    """这些都是**合法的只读查询**，v1 会误拒。"""

    @pytest.mark.parametrize("stmt", [
        'MATCH (d:disease) WHERE d.name CONTAINS ";" RETURN d.name',
        'MATCH (f:food) WHERE f.name CONTAINS "SET" RETURN f.name',
        'MATCH (f:food) WHERE f.name CONTAINS "CREATE" RETURN f.name',
        'MATCH (d:disease) WHERE d.desc CONTAINS "http://x" RETURN d.name',
        "MATCH (d:disease) WHERE d.name = 'DROP' RETURN d.name",
        'MATCH (d:disease) WHERE d.desc CONTAINS "// 注意" RETURN d.name',
    ])
    def test_dangerous_words_inside_literals_are_fine(self, stmt, schema):
        assert ok(stmt, schema).stmt

    def test_readonly_call_subquery_allowed(self, schema):
        """v1 一刀切禁 CALL，把 UNION 型只读子查询也误伤了。"""
        stmt = (
            'MATCH (d:disease) WHERE d.name = "感冒" '
            "CALL { MATCH (x:drug) RETURN x.name AS n LIMIT 3 } "
            "RETURN d.name, n"
        )
        assert ok(stmt, schema).stmt


# ------------------------------------------------------------------ 写操作

class TestWriteBlocked:
    @pytest.mark.parametrize("stmt", [
        "MATCH (n) DETACH DELETE n RETURN 1",
        "MATCH (d:disease) SET d.name = 'x' RETURN d.name",
        "CREATE (d:disease {name:'x'}) RETURN d.name",
        "MERGE (d:disease {name:'x'}) RETURN d.name",
        "MATCH (d:disease) REMOVE d.name RETURN 1",
        "DROP INDEX idx_disease_name",
        "LOAD CSV FROM 'file:///x.csv' AS row RETURN row",
        "MATCH (d:disease) FOREACH (x IN [1] | SET d.name = 'y') RETURN d.name",
    ])
    def test_blocked(self, stmt, schema):
        rejected(stmt, schema)

    def test_multi_statement_blocked(self, schema):
        msg = rejected("MATCH (d:disease) RETURN d.name LIMIT 1; DROP INDEX x", schema)
        assert "一条语句" in msg

    def test_in_transactions_blocked(self, schema):
        rejected(
            "MATCH (d:disease) CALL { WITH d RETURN d.name AS n } IN TRANSACTIONS RETURN n",
            schema,
        )


class TestProceduresBlocked:
    @pytest.mark.parametrize("stmt", [
        "CALL dbms.components() YIELD name RETURN name",
        "CALL db.labels() YIELD label RETURN label",
        "CALL dbms.security.listUsers() YIELD username RETURN username",
        "MATCH (d:disease) RETURN apoc.convert.toJson(d)",
        "MATCH (d:disease) RETURN gds.version()",
    ])
    def test_blocked(self, stmt, schema):
        rejected(stmt, schema)

    @pytest.mark.parametrize("stmt", [
        "SHOW INDEXES YIELD name RETURN name",
        "SHOW DATABASES YIELD name RETURN name",
        "USE neo4j MATCH (d:disease) RETURN d.name",
    ])
    def test_admin_blocked(self, stmt, schema):
        rejected(stmt, schema)


# ------------------------------------------------------------------ schema

class TestSchemaChecks:
    def test_unknown_relation(self, schema):
        msg = rejected("MATCH (d:disease)-[:hasSymptom]->(s:symptom) RETURN s.name", schema)
        assert "hasSymptom" in msg

    def test_unknown_label(self, schema):
        rejected("MATCH (d:doctor) RETURN d.name", schema)

    def test_unknown_property(self, schema):
        msg = rejected("MATCH (d:disease) RETURN d.disease_name", schema)
        assert "disease_name" in msg

    def test_known_property_ok(self, schema):
        assert ok("MATCH (d:disease) RETURN d.cured_prob", schema).stmt

    def test_decimal_literal_is_not_a_property(self, schema):
        """`1.5` 不能被当成属性访问 —— 属性正则的变量名必须以字母开头。"""
        assert ok("MATCH (d:disease) WHERE 1.5 > 1.0 RETURN d.name", schema).stmt

    def test_no_return_rejected(self, schema):
        rejected("MATCH (d:disease) WHERE d.name = 'x'", schema)

    def test_explain_prefix_rejected(self, schema):
        msg = rejected("EXPLAIN MATCH (d:disease) RETURN d.name", schema)
        assert "EXPLAIN" in msg


# ------------------------------------------------------------------ 资源护栏

class TestResourceGuards:
    def test_appends_limit_when_missing(self, schema):
        v = ok("MATCH (d:disease) RETURN d.name", schema, default_limit=25)
        assert v.stmt.rstrip().endswith("LIMIT 25")
        assert v.limit == 25
        assert v.rewrites

    def test_caps_oversized_limit(self, schema):
        """v1 只看"结尾有没有 LIMIT"，`LIMIT 100000` 照样放行。"""
        v = ok("MATCH (d:disease) RETURN d.name LIMIT 100000", schema, max_limit=200)
        assert "LIMIT 200" in v.stmt
        assert v.limit == 200

    def test_keeps_small_limit(self, schema):
        v = ok("MATCH (d:disease) RETURN d.name LIMIT 10", schema, max_limit=200)
        assert v.limit == 10
        assert v.stmt.count("LIMIT") == 1

    def test_caps_inner_limit_too(self, schema):
        v = ok(
            "MATCH (d:disease) WITH d LIMIT 99999 RETURN d.name LIMIT 10",
            schema, max_limit=200,
        )
        assert "LIMIT 200" in v.stmt

    def test_default_limit_never_exceeds_max(self, schema):
        v = ok("MATCH (d:disease) RETURN d.name", schema, default_limit=500, max_limit=200)
        assert v.limit == 200

    @pytest.mark.parametrize("stmt", [
        "MATCH (d:disease)-[*]->(x) RETURN x.name",
        "MATCH (d:disease)-[*..]->(x) RETURN x.name",
        "MATCH (d:disease)-[:diseaseDiseaseRelation*2..]->(x:disease) RETURN x.name",
    ])
    def test_unbounded_path_blocked(self, stmt, schema):
        assert "变长路径" in rejected(stmt, schema)

    def test_too_many_hops_blocked(self, schema):
        rejected(
            "MATCH (d:disease)-[:diseaseDiseaseRelation*1..9]->(x:disease) RETURN x.name",
            schema, max_path_hops=3,
        )

    def test_bounded_path_allowed(self, schema):
        assert ok(
            "MATCH (d:disease)-[:diseaseDiseaseRelation*1..2]->(x:disease) RETURN x.name",
            schema, max_path_hops=3,
        ).stmt

    def test_unlabeled_match_warns_not_rejects(self, schema):
        v = ok("MATCH (n) RETURN n.name", schema)
        assert v.warnings

    def test_trailing_semicolon_tolerated(self, schema):
        assert ok("MATCH (d:disease) RETURN d.name LIMIT 5;", schema).limit == 5

    def test_empty_rejected(self, schema):
        rejected("   ", schema)
