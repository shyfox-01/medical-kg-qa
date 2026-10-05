"""Explicit, request-scoped conversation memory; no shared user session state."""

import re


def resolve(question: str, history: list[dict]) -> tuple[str, str | None]:
    turns = history[-4:]
    if not turns:
        return question, None
    previous = turns[-1]
    focus = previous.get('focus', [])
    intent = previous.get('intent')
    if focus and re.search(r'\b(it|that|this drug|this disease)\b', question, re.I):
        question = re.sub(r'\b(it|that|this drug|this disease)\b', focus[0], question, flags=re.I)
    return question, intent if re.match(r'\s*what about\b', question, re.I) else None
