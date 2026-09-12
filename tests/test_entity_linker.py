"""实体链接的单元测试。

重点是**多标签同名**（咳嗽 / 头痛 / 腹泻 既是 disease 又是 symptom）
和**精确名优先**这两件 v1 没处理的事。
"""
from __future__ import annotations

import pytest

from app.entity_linker import EntityLinker


class TestDictionaryMatch:
    def test_exact(self, linker):
        names = {m.name for m in linker.all_matches("糖尿病有什么症状")}
        assert "糖尿病" in names

    def test_alias(self, linker):
        ms = [m for m in linker.all_matches("我头疼") if m.name == "头痛"]
        assert ms and ms[0].how == "alias"
        assert ms[0].surface == "头疼"

    def test_alias_keeps_user_wording_for_display(self, linker):
        m = next(m for m in linker.all_matches("拉肚子") if m.name == "腹泻")
        assert m.surface == "拉肚子"

    def test_single_char_names_are_ignored(self):
        """图里有 20 个单字节点名，出现在问句里全是噪声。"""
        lk = EntityLinker([("水", "food"), ("糖尿病", "disease")], {})
        assert {m.name for m in lk.all_matches("糖尿病人喝水")} == {"糖尿病"}

    def test_single_char_names_dont_leak_through_the_fallback(self):
        """`link()` 的 contains 兜底也得挡单字名 —— 否则「MATCH (n) DETACH DELETE n」
        这种一个中文都没有的输入会链接出一个叫「C」的实体。"""
        lk = EntityLinker([("C", "drug"), ("糖尿病", "disease")], {})
        assert lk.scan("MATCH (n) DETACH DELETE n") == []

    def test_overlapping_candidates_are_all_kept(self, linker):
        """同一段字面既是 disease 又是 symptom 时两个都要留，取哪个由下游按需要决定。"""
        labels = {m.label for m in linker.all_matches("咳嗽") if m.name == "咳嗽"}
        assert labels == {"disease", "symptom"}


class TestAnchorSelection:
    def test_picks_requested_label(self, linker):
        assert linker.anchor("咳嗽怎么治", "disease").name == "咳嗽"
        assert linker.anchor("咳嗽会引起什么", "symptom").name == "咳嗽"

    def test_returns_none_when_label_absent(self, linker):
        assert linker.anchor("糖尿病有什么症状", "drug") is None

    def test_longer_span_wins(self, linker):
        """「糖尿病足」在场时不该退化成「糖尿病」。"""
        assert linker.anchor("糖尿病足怎么治", "disease").name == "糖尿病足"

    def test_shorter_contained_anchor_is_dropped(self, linker):
        names = [m.name for m in linker.anchors("糖尿病足怎么治", "disease")]
        assert "糖尿病" not in names

    def test_multiple_anchors_in_document_order(self, linker):
        names = [m.name for m in linker.anchors("高血压和糖尿病共同的忌口", "disease")]
        assert names == ["高血压", "糖尿病"]

    def test_generic_words_are_deprioritised(self, linker):
        """「药物」确实是 cureWay 节点，但问句里它是疑问词不是查询目标。"""
        m = next(m for m in linker.all_matches("感冒吃什么药物") if m.name == "药物")
        assert m.score < 100


class TestExactPreference:
    def test_has_exact(self, linker):
        assert linker.has_exact("肺炎", "disease")
        assert not linker.has_exact("肺炎", "symptom")

    def test_variants_sorted_by_length(self, linker):
        v = linker.variants("肺炎", "disease", limit=5)
        assert v[0] == "肺炎"
        assert v == sorted(v, key=lambda n: (len(n), n))

    def test_ambiguous_empty_when_exact_exists(self, linker):
        assert linker.ambiguous("肺炎", "disease") == []

    def test_ambiguous_when_no_exact_and_many_hits(self, linker):
        assert linker.ambiguous("肺炎杆", "disease", threshold=0)


class TestScanAndDescribe:
    def test_scan_is_non_overlapping(self, linker):
        ms = linker.scan("糖尿病人不能吃西瓜吗")
        spans = sorted((m.start, m.end) for m in ms if m.start >= 0)
        for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
            assert e1 <= s2 or (s1, e1) == (s2, e2)

    def test_describe_mentions_canonical_name(self, linker):
        text = linker.describe(linker.scan("我头疼"))
        assert "头痛" in text and "头疼" in text

    def test_describe_empty(self, linker):
        assert "未在图谱中匹配到" in linker.describe([])

    def test_labels_in(self, linker):
        assert "disease" in linker.labels_in("糖尿病有什么症状")
        assert linker.labels_in("完全无关的一句话") == frozenset()


class TestSuggest:
    def test_suggests_only_unmatched(self, linker):
        assert "糖尿病" not in linker.suggest("糖尿病有什么症状")

    def test_empty_question(self, linker):
        assert linker.suggest("") == []


class TestAliasAudit:
    def test_flags_broken_alias(self):
        lk = EntityLinker([("腹泻", "symptom")], {"拉肚子": "不存在的词"})
        assert ("拉肚子", "不存在的词") in lk.audit_aliases()["broken"]

    def test_flags_redundant_alias(self):
        lk = EntityLinker([("腹泻", "symptom")], {"腹泻": "腹泻"})
        assert ("腹泻", "腹泻") in lk.audit_aliases()["redundant"]

    def test_broken_alias_is_not_applied(self):
        """宁可不改写，也不能把问句改成一个图谱里查不到的词。"""
        lk = EntityLinker([("腹泻", "symptom")], {"拉肚子": "不存在的词"})
        assert lk.all_matches("拉肚子") == []

    def test_shipped_alias_table_is_clean(self):
        """仓库里那份 data/aliases.json 必须 0 冗余 0 失效 —— 否则就是没体检过。"""
        from app.entity_linker import load_aliases
        from tests.conftest import NAMES

        raw = load_aliases()
        assert raw, "别名表不该是空的"
        # 这里只能验"格式正确"（测试环境没有全量图谱）：key 和 value 都非空且不相等
        for k, v in raw.items():
            assert k and v, f"空条目 {k!r} -> {v!r}"
            assert k != v, f"{k} 映射到自己，属于冗余条目"
        _ = NAMES  # conftest 的名单只用于其他用例
