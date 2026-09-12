"""实体链接：把用户口语里的说法对齐到图谱里真实存在的节点名。

这是初版最大的功能缺陷。用户问「我头疼」，LLM 会生成
`MATCH (s:symptom {name:'头疼'})...`，但图谱里那个节点叫「头痛」，
精确匹配返回 0 行，系统就回一句「这个问题我还不知道怎么回答」——
看起来像模型不行，其实是实体没对齐。

v2 在 v1 的"词典最大匹配 + 别名归一 + 模糊兜底"之上补了三件事，
都是被后面的模板快路径逼出来的需求：

**1. 保留重叠候选，而不是只留贪心结果。**
   v1 的 `scan()` 只做一遍从左到右的最长匹配，同一个位置只可能产出一个实体。
   但图谱里有 481 个名字同时挂着多个标签（`咳嗽`、`头痛`、`腹泻`、`贫血`
   既是 disease 又是 symptom；`呼吸内科` 既是 department 又是 category），
   到底该取哪个**取决于问题问的是什么**——「咳嗽会引起什么病」要 symptom，
   「咳嗽怎么治」要 disease。所以链接阶段不做取舍，把候选都留着，
   由下游按 label 去挑（`anchor(label=...)`）。

**2. 精确名优先于 CONTAINS。**
   图里有 125 个疾病名含「肺炎」，但恰好有一个就叫「肺炎」。
   v1 一律 CONTAINS，于是「肺炎有什么症状」把 125 种肺炎的症状混成一锅端出来，
   看着有结果，其实是错的。有精确同名节点时必须优先用它。

**3. 消歧与建议。**
   没有精确名、CONTAINS 又命中一大片时，与其硬猜，不如把候选摆出来让用户选。

已知局限（v1 就写了，v2 依然成立）：中文短词的编辑距离区分度很差
（「头疼」vs「头痛」相似度只有 50%），放低阈值又会让「病人」匹配到
「艾滋病人的急性阑尾炎」。所以模糊匹配只做最后兜底，主力靠词典 + 别名表。
真正的解法是换成向量检索或医学同义词库（CMeKG / ICD-10）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz, process

from .config import DATA_DIR

MAX_NAME_LEN = 16  # 滑窗上限，超过这个长度的节点名极少，靠模糊匹配兜
MIN_NAME_LEN = 2   # 单字节点名（图里有 20 个）在问句里全是噪声，不参与词典匹配
_ALIAS_PATH = DATA_DIR / "aliases.json"

# 这些名字确实是图谱节点（都是 cureWay / check），但出现在**问句**里时
# 几乎总是疑问词而不是查询目标：「感冒吃什么药物」问的是药，不是叫"药物"的治疗方式。
# 不删除，只降权 —— 下游按 label 挑锚点时它们自然排在后面。
_GENERIC = {"药物", "手术", "治疗", "检查", "化验", "预防", "护理", "康复", "饮食"}


def load_aliases(path: Path | None = None) -> dict[str, str]:
    p = path or _ALIAS_PATH
    if not p.exists():
        return {}
    raw = json.loads(p.read_text("utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


@dataclass(frozen=True)
class Mention:
    surface: str  # 问句中出现的字面
    name: str  # 图谱中的规范名
    label: str
    score: float
    how: str  # exact / alias / contains / fuzzy
    start: int = -1
    end: int = -1

    @property
    def span(self) -> int:
        return max(self.end - self.start, len(self.surface))


class EntityLinker:
    def __init__(self, names: list[tuple[str, str]], aliases: dict[str, str] | None = None) -> None:
        self._by_name: dict[str, list[str]] = {}
        for name, label in names:
            if not name:
                continue
            self._by_name.setdefault(name, []).append(label)
        self._all = list(self._by_name.keys())
        # 别名只保留目标确实在图谱里的那些，避免把问句改成一个查不到的词。
        # 过滤前的原始表要留着 —— audit_aliases() 体检的正是"哪些条目被静默丢掉了"。
        src = aliases if aliases is not None else load_aliases()
        self._raw_aliases = dict(src)
        self._aliases = {k: v for k, v in src.items() if v in self._by_name}
        self._alias_keys = sorted(self._aliases, key=len, reverse=True)
        # label -> 该 label 下的全部名字，供 variants() 做内存 CONTAINS
        self._by_label: dict[str, list[str]] = {}
        for name, labels in self._by_name.items():
            for lb in labels:
                self._by_label.setdefault(lb, []).append(name)

    # ------------------------------------------------------------ 词典匹配

    def all_matches(self, text: str) -> list[Mention]:
        """问句里所有词典命中，**允许重叠**，包含别名归一后的命中。

        不做取舍是刻意的：同一段字面可能既是 disease 又是 symptom，
        选哪个要等下游知道"问的是什么"才能定。
        """
        text = (text or "").strip()
        out: list[Mention] = []
        n = len(text)
        for i in range(n):
            for length in range(min(MAX_NAME_LEN, n - i), MIN_NAME_LEN - 1, -1):
                piece = text[i : i + length]
                if piece in self._by_name:
                    for lb in self._by_name[piece]:
                        score = 90.0 if piece in _GENERIC else 100.0
                        out.append(Mention(piece, piece, lb, score, "exact", i, i + length))
        # 别名：口语片段 -> 图谱术语。别名的 surface 是用户原话，name 是规范名
        for key in self._alias_keys:
            start = text.find(key)
            while start >= 0:
                canon = self._aliases[key]
                for lb in self._by_name[canon]:
                    out.append(
                        Mention(key, canon, lb, 99.0, "alias", start, start + len(key))
                    )
                start = text.find(key, start + 1)
        return out

    def scan(self, question: str, per_mention: int = 3) -> list[Mention]:
        """贪心最长匹配（不重叠），用于注入 prompt 给 LLM 看。

        从 all_matches 里选：先按覆盖长度、再按分数取，选中后把区间占掉。
        全句一个都没命中时（纯口语提问）退化成整句模糊匹配。
        """
        matches = self.all_matches(question)
        if not matches:
            return self.link(question.strip(), k=per_mention)

        taken: list[tuple[int, int]] = []
        chosen: list[Mention] = []
        for m in sorted(matches, key=lambda m: (-m.span, -m.score, m.start)):
            if any(m.start < e and s < m.end for s, e in taken):
                # 区间已被更长的实体占了；但同名不同 label 的要一起留下
                if not any(c.start == m.start and c.end == m.end for c in chosen):
                    continue
            taken.append((m.start, m.end))
            chosen.append(m)
        chosen.sort(key=lambda m: (m.start, -m.score))
        return _dedup(chosen)

    def anchor(self, question: str, label: str) -> Mention | None:
        """挑一个指定 label 的锚点实体。没有就返回 None（下游据此决定要不要走快路径）。

        排序依据：覆盖字面越长越可信 -> 分数 -> 出现位置越靠前越可能是主语。
        """
        cands = [m for m in self.all_matches(question) if m.label == label]
        if not cands:
            return None
        cands.sort(key=lambda m: (-m.span, -m.score, m.start))
        return cands[0]

    def anchors(self, question: str, label: str, limit: int = 5) -> list[Mention]:
        """指定 label 的全部锚点候选，去重后按可信度排序。多疾病求交集时要用。"""
        cands = [m for m in self.all_matches(question) if m.label == label]
        cands.sort(key=lambda m: (-m.span, -m.score, m.start))
        seen: set[str] = set()
        out: list[Mention] = []
        for m in cands:
            if m.name in seen:
                continue
            # 被更长实体完全包住的短实体丢掉：「糖尿病足」在场时不要再冒出「糖尿病」
            if any(o.start <= m.start and m.end <= o.end for o in out):
                continue
            seen.add(m.name)
            out.append(m)
            if len(out) >= limit:
                break
        return sorted(out, key=lambda m: m.start)

    def has_exact(self, name: str, label: str | None = None) -> bool:
        labels = self._by_name.get(name)
        return bool(labels) and (label is None or label in labels)

    def variants(self, keyword: str, label: str, limit: int = 12) -> list[str]:
        """图谱里所有包含该关键词的同类节点名，短的排前面。

        「肺炎」-> ['肺炎', '球形肺炎', '肺炎杆菌肺炎', ...]，共 125 个。
        用来判断"要不要让用户消歧"，以及在没有精确名时给候选。
        """
        pool = self._by_label.get(label, [])
        hits = [n for n in pool if keyword in n]
        hits.sort(key=lambda n: (len(n), n))
        return hits[:limit]

    def ambiguous(self, keyword: str, label: str, threshold: int = 6) -> list[str]:
        """没有精确同名、而模糊命中又太多 —— 这种情况该让用户选，不该替他猜。"""
        if self.has_exact(keyword, label):
            return []
        hits = self.variants(keyword, label, limit=threshold + 1)
        return hits if len(hits) > threshold else []

    # ------------------------------------------------------------------ 单点

    def link(self, mention: str, k: int = 5) -> list[Mention]:
        mention = mention.strip()
        if not mention:
            return []
        if mention in self._aliases:
            canon = self._aliases[mention]
            return [Mention(mention, canon, lb, 99.0, "alias") for lb in self._by_name[canon]]
        if mention in self._by_name:
            return [Mention(mention, mention, lb, 100.0, "exact") for lb in self._by_name[mention]]

        hits: list[Mention] = []
        for name in self._all:
            # `name in mention` 这个方向噪声很大：图里有 20 个单字节点名，
            # 随便一句话都能包住它们。问「MATCH (n) DETACH DELETE n」时
            # 曾经真的链接出一个叫「C」的实体。词典匹配那边有 MIN_NAME_LEN 挡着，
            # 这条兜底路径也得挡。
            if mention in name or (len(name) >= MIN_NAME_LEN and name in mention):
                for lb in self._by_name[name]:
                    hits.append(Mention(mention, name, lb, 95.0, "contains"))
        if hits:
            hits.sort(key=lambda m: abs(len(m.name) - len(mention)))
            return hits[:k]

        return self._fuzzy(mention, k=k, cutoff=70)

    def _fuzzy(self, mention: str, k: int, cutoff: float) -> list[Mention]:
        """WRatio 里的 partial_ratio 会把「病人」和「艾滋病人的急性阑尾炎」判成满分，
        所以额外加一道长度护栏：候选名不能比查询词长太多。"""
        hits: list[Mention] = []
        for name, score, _ in process.extract(
            mention, self._all, scorer=fuzz.WRatio, limit=k * 4, score_cutoff=cutoff
        ):
            if len(name) > len(mention) * 2 + 2:
                continue
            for lb in self._by_name[name]:
                hits.append(Mention(mention, name, lb, float(score), "fuzzy"))
        return hits[:k]

    def suggest(self, question: str, k: int = 5) -> list[str]:
        """「你是不是想问……」。一无所获时给用户一个下一步，而不是一句"查不到"。"""
        found = {m.name for m in self.all_matches(question)}
        out: list[str] = []
        for m in self.link(question.strip(), k=k * 2):
            if m.name not in found and m.name not in out:
                out.append(m.name)
        return out[:k]

    # ------------------------------------------------------------------ 体检

    def audit_aliases(self) -> dict[str, list[tuple[str, str]]]:
        """体检别名表。三种坏味道，都是真踩过的：

        broken    目标词不在图谱里 —— 我最初把「气短」映射成「气促」，
                  想当然以为图谱用学术术语，结果图谱里就叫「气短」，这条纯属帮倒忙；
        redundant key 自己就是图谱节点 —— 词典最大匹配已经能命中，别名反而是噪声；
        valid     真正起作用的。

        构造函数会静默丢掉 broken 那批（宁可不改写，也不能把问句改成一个查不到的词），
        但静默丢掉意味着你不知道自己写错了，所以要有这个方法把它们摆出来。

        注意体检的是**构造这个 linker 时实际用的那份别名表**，不是磁盘上的文件。
        v1 这里写的是 `load_aliases()`，传了自定义别名进来时体检的就是另一份数据 ——
        单测正是被这一条揪出来的。
        """
        out: dict[str, list[tuple[str, str]]] = {"valid": [], "redundant": [], "broken": []}
        for k, v in self._raw_aliases.items():
            if k in self._by_name:
                out["redundant"].append((k, v))
            elif v not in self._by_name:
                out["broken"].append((k, v))
            else:
                out["valid"].append((k, v))
        return out

    def describe(self, mentions: list[Mention]) -> str:
        """渲染成注入 prompt 的一段文本，让 LLM 只用图谱里真实存在的名字。"""
        if not mentions:
            return "（未在图谱中匹配到问句里的实体，请用 CONTAINS 做模糊检索）"
        lines = []
        for m in mentions:
            note = f"  [{m.how}]" + (f" 用户原话「{m.surface}」" if m.surface != m.name else "")
            lines.append(f'  "{m.name}" -> (:{m.label} {{name: "{m.name}"}}){note}')
        return "\n".join(lines)

    def labels_in(self, question: str) -> frozenset[str]:
        """问句里出现了哪些类型的实体。安全闸拿它判断"是不是在说药"。"""
        return frozenset(m.label for m in self.all_matches(question))


def _dedup(mentions: list[Mention]) -> list[Mention]:
    seen, out = set(), []
    for m in mentions:
        key = (m.name, m.label)
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out
