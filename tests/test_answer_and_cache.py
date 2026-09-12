"""回答组织、缓存、JSON 容错解析的单元测试。"""
from __future__ import annotations

import time

import pytest

from app import answer as answer_mod
from app.cache import TTLCache, make_key
from app.llm import parse_json


class TestRenderRows:
    def test_short_rows_not_truncated(self):
        text, truncated = answer_mod.render_rows([{"a": 1}])
        assert not truncated and '"a"' in text

    def test_long_rows_truncated_with_note(self):
        rows = [{"name": "x" * 50, "i": i} for i in range(200)]
        text, truncated = answer_mod.render_rows(rows, max_chars=500)
        assert truncated
        assert "共 200 条" in text

    def test_empty(self):
        text, truncated = answer_mod.render_rows([])
        assert not truncated and text.strip() == "[]"


class TestBuildMessages:
    def test_wraps_data_in_delimited_blocks(self):
        msgs = answer_mod.build_messages("感冒有什么症状", "MATCH ...", [{"症状": "咳嗽"}])
        user = msgs[1]["content"]
        assert "<用户问题>" in user and "</用户问题>" in user
        assert "<查询结果>" in user and "</查询结果>" in user

    def test_system_forbids_executing_embedded_instructions(self):
        msgs = answer_mod.build_messages("q", "c", [])
        assert "当作**数据**" in msgs[0]["content"]

    def test_truncation_flag_reaches_the_model(self):
        """截断没告诉模型，模型就会把 25 条讲成"全部"。医疗场景里这是硬伤。"""
        msgs = answer_mod.build_messages("q", "c", [{"a": 1}], truncated=True)
        assert "这不是全部" in msgs[1]["content"]

    def test_no_truncation_flag_when_complete(self):
        msgs = answer_mod.build_messages("q", "c", [{"a": 1}], truncated=False)
        assert "结果完整性" not in msgs[1]["content"]

    def test_relation_semantics_injected(self):
        """常用药 vs 推荐药光看关系名分不出来，得把人工写的语义说明带上。"""
        msgs = answer_mod.build_messages(
            "q", "c", [], rels=["diseaseDrugRelation", "diseaseRecommendDrugRelation"]
        )
        assert "diseaseDrugRelation" in msgs[1]["content"]

    def test_safety_instruction_appended_to_system(self):
        msgs = answer_mod.build_messages("q", "c", [], safety_instruction="【硬约束】不给剂量")
        assert "不给剂量" in msgs[0]["content"]


class TestFinalize:
    def test_disclaimer_is_added_by_code_not_the_model(self):
        """v1 是在 prompt 里"请求"模型加免责声明，模型可能忘、可能被截断。"""
        assert answer_mod.DISCLAIMER in answer_mod.finalize("回答正文")

    def test_evidence_rendered(self):
        ev = answer_mod.Evidence(path="糖尿病 --rel--> food", row_count=4)
        out = answer_mod.finalize("正文", ev)
        assert "糖尿病 --rel--> food" in out and "4 条结果" in out

    def test_evidence_marks_truncation(self):
        ev = answer_mod.Evidence(path="p", row_count=25, truncated=True)
        assert "已截断" in answer_mod.finalize("正文", ev)

    def test_empty_evidence_renders_nothing(self):
        assert answer_mod.Evidence().render() == ""


class TestNoResultMessage:
    def test_offers_suggestions(self):
        msg = answer_mod.no_result_message(["肺炎", "小儿肺炎"], [], [])
        assert "肺炎" in msg and "你是不是想问" in msg

    def test_offers_fulltext_hits(self):
        msg = answer_mod.no_result_message([], [{"name": "咳嗽"}], [])
        assert "咳嗽" in msg

    def test_falls_back_to_capability_description(self):
        """什么线索都没有时也不能只说一句"查不到"——得告诉用户这系统到底能答什么。"""
        msg = answer_mod.no_result_message([], [], [])
        assert "8808" in msg

    def test_echoes_recognised_entities(self):
        assert "糖尿病" in answer_mod.no_result_message([], [], ["糖尿病"])


class TestCache:
    def test_hit_and_miss(self):
        c = TTLCache(ttl=100)
        assert c.get("k") is None
        c.put("k", 42)
        assert c.get("k") == 42
        assert c.hits == 1 and c.misses == 1

    def test_expiry(self):
        c = TTLCache(ttl=0.01)
        c.put("k", 1)
        time.sleep(0.02)
        assert c.get("k") is None

    def test_lru_eviction(self):
        c = TTLCache(maxsize=2, ttl=100)
        c.put("a", 1); c.put("b", 2); c.put("c", 3)
        assert c.get("a") is None and c.get("c") == 3

    def test_key_includes_everything_that_changes_the_answer(self):
        """少带一个维度，改完配置拿到的就是旧答案 —— 这种错极难发现。"""
        base = make_key("q", "fp1", "model", True)
        assert make_key("q", "fp2", "model", True) != base   # schema 变了
        assert make_key("q", "fp1", "other", True) != base   # 模型变了
        assert make_key("q", "fp1", "model", False) != base  # 快路径开关变了

    def test_clear(self):
        c = TTLCache()
        c.put("k", 1); c.get("k"); c.clear()
        assert c.get("k") is None and c.hits == 0


class TestParseJson:
    def test_plain(self):
        assert parse_json('{"a": 1}') == {"a": 1}

    def test_fenced(self):
        assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_fenced_without_language(self):
        assert parse_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_strips_think_block(self):
        assert parse_json('<think>想一想</think>\n{"a": 1}') == {"a": 1}

    def test_extracts_from_surrounding_prose(self):
        assert parse_json('好的，这是结果：{"a": 1} 希望有帮助') == {"a": 1}

    def test_nested_braces(self):
        assert parse_json('前言 {"a": {"b": 2}} 后语') == {"a": {"b": 2}}

    def test_raises_on_garbage(self):
        with pytest.raises(ValueError):
            parse_json("完全不是 JSON")
