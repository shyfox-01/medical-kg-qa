"""多轮会话：焦点实体延续 + 指代消解。

v1 是纯单轮的，README 里把这条列在"已知没解决的"。实际用起来这是最别扭的一点：

    问> 糖尿病有什么症状
    答> 多饮、多尿、消瘦……
    问> 那忌口什么
    答> 图谱里没有查到相关信息。

第二问在人看来毫无歧义，但系统这边实体链接一个都没命中，
生成的 Cypher 自然查不到东西。

v2 的做法是**本地**补全，不额外调 LLM：
  1. 记住每轮的焦点实体（问句里链接上的疾病 / 症状）；
  2. 新问题如果自己就有实体，什么都不做 —— 话题换了就该换焦点；
  3. 没有实体、但出现指代词（它 / 这个病 / 该病）或省略式开头（那…呢），
     就把上一轮的焦点补进来，改写成一句完整的问题。

改写结果会写进 trace，用户能看见系统"以为你在问什么"。这点很重要：
指代消解一旦猜错，用户得能立刻看出来，而不是拿到一个莫名其妙的答案。

历史同时会以极简形式注入 LLM 路径的 prompt（只有问题和查了什么，不含结果正文），
既给模型上下文，又不让历史把 token 吃光。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .entity_linker import EntityLinker, Mention
from .planner import detect_intent

# 指代词。命中说明这句在指上文的某个东西
_PRONOUN = re.compile(r"这个病|那个病|这种病|这类病|该病|此病|这病|它们|它|其")
# 省略式开头：「那忌口呢」「还有并发症吗」「另外挂什么科」
_ELLIPSIS_LEAD = re.compile(r"^\s*(那么|那|还有|另外|以及|再|顺便|接着)\s*")
# 「…呢？」也是典型的承前省略
_TRAILING_NE = re.compile(r"呢\s*[？?]?\s*$")

# 焦点可以是这些类型的实体。food / drug 这些是**答案**里的东西，不该当焦点。
_FOCUS_LABELS = ("disease", "symptom", "department")


@dataclass
class Turn:
    question: str
    resolved: str
    intent: str | None = None
    focus: tuple[str, ...] = ()
    cypher: str | None = None
    row_count: int = 0
    route: str = ""


@dataclass
class Resolution:
    question: str                    # 消解后、真正拿去查的问题
    original: str
    carried: tuple[str, ...] = ()    # 从上文带过来的实体
    carried_intent: str | None = None  # 从上文带过来的意图
    note: str = ""                   # 给 trace / 用户看的说明


class Conversation:
    """一个会话的短期记忆。CLI 用一个实例；评测每题新建一个，保证单轮可复现。"""

    def __init__(self, max_turns: int = 4) -> None:
        self.max_turns = max_turns
        self.turns: list[Turn] = []

    # ------------------------------------------------------------------ 记忆

    def reset(self) -> None:
        self.turns.clear()

    def record(self, turn: Turn) -> None:
        self.turns.append(turn)
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]

    def _last_intent(self) -> str | None:
        """最近一轮真正走通了的意图。`:intersect` 这类复合意图不往下传。"""
        for turn in reversed(self.turns):
            if turn.intent and ":" not in turn.intent and turn.row_count:
                return turn.intent
        return None

    @property
    def focus(self) -> tuple[str, ...]:
        """最近一轮有焦点实体的那轮的焦点。"""
        for turn in reversed(self.turns):
            if turn.focus:
                return turn.focus
        return ()

    # -------------------------------------------------------------- 指代消解

    def resolve(self, question: str, linker: EntityLinker) -> Resolution:
        q = (question or "").strip()
        if self.max_turns <= 0 or not self.turns:
            return Resolution(question=q, original=q)

        # 这句自己就有实体 -> 主语是新的，不要拿旧焦点去污染它。
        # 但省略可能发生在**另一半**：「糖尿病有什么症状」→「高血压呢」，
        # 实体换了、要问的东西没变。这时候要接过来的是**意图**而不是实体。
        if _has_focus_entity(q, linker):
            if detect_intent(q)[0] is None and (inherited := self._last_intent()):
                if len(q) <= 12 or _TRAILING_NE.search(q) or _ELLIPSIS_LEAD.match(q):
                    return Resolution(
                        question=q,
                        original=q,
                        carried_intent=inherited,
                        note=f"承上文，仍然问「{inherited}」",
                    )
            return Resolution(question=q, original=q)

        focus = self.focus
        if not focus:
            return Resolution(question=q, original=q)

        elliptical = bool(
            _PRONOUN.search(q) or _ELLIPSIS_LEAD.match(q) or _TRAILING_NE.search(q)
        )
        # 短问句 + 识别得出医疗意图 = 承前省略（「忌口呢」「怎么治」「挂什么科」）。
        #
        # 只看长度是不够的：「今天北京天气怎么样」才 9 个字，也没有任何实体，
        # 被当成追问就会补成「糖尿病今天北京天气怎么样」，问题直接被改坏。
        # 必须再要求这句话本身**问的是医疗图谱里的东西**。
        if not elliptical and len(q) <= 12 and detect_intent(q)[0] is not None:
            elliptical = True
        if not elliptical:
            return Resolution(question=q, original=q)

        subject = focus[0]
        body = _ELLIPSIS_LEAD.sub("", q)
        if _PRONOUN.search(body):
            rewritten = _PRONOUN.sub(subject, body, count=1)
        else:
            rewritten = f"{subject}{body}"
        return Resolution(
            question=rewritten,
            original=q,
            carried=focus,
            note=f"承上文，按「{rewritten}」理解",
        )

    # ---------------------------------------------------------- prompt 注入

    def prompt_context(self) -> str:
        """给 LLM 看的极简历史。只带问题和查询意图，不带结果正文 —— 结果动辄上千 token，
        而模型需要的只是"刚才在聊什么"。"""
        if not self.turns:
            return ""
        lines = []
        for t in self.turns[-self.max_turns :]:
            hit = f"{t.row_count} 条结果" if t.cypher else "未查询"
            lines.append(f"  - 用户问「{t.resolved}」，走 {t.route or '?'}，{hit}")
        return "# 最近的对话（用于理解指代，不要直接拿来作答）\n" + "\n".join(lines)


def _has_focus_entity(question: str, linker: EntityLinker) -> bool:
    return any(m.label in _FOCUS_LABELS for m in linker.all_matches(question))


def focus_from(mentions: list[Mention], limit: int = 2) -> tuple[str, ...]:
    """从本轮链接到的实体里挑出可以当焦点的那些。"""
    out: list[str] = []
    for label in _FOCUS_LABELS:
        for m in mentions:
            if m.label == label and m.name not in out:
                out.append(m.name)
    return tuple(out[:limit])
