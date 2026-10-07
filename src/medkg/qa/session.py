"""Explicit, request-scoped conversation memory; no shared user session state."""

import re

REFERENCE = re.compile(r'\b(?:this|that|the same) (?:drug|medication|medicine|disease|condition|'
                       r'disorder|gene)\b|\bits\b|\bit\b|\bthat\b', re.I)
# "that" refers to the previous focus only as a demonstrative ("does that ...",
# "what about that?"), never as a relative pronoun ("drugs that treat it").
DEMONSTRATIVE_CUES = {'does', 'do', 'did', 'is', 'was', 'about', 'for', 'with', 'of', 'on', 'to',
                      'treat', 'treats', 'cause', 'causes'}
EXPLETIVE = re.compile(r'\s+(?:true|possible|likely|known|common|normal)\b', re.I)


def _substitute(question: str, focus: str) -> str:
    def replace(match: re.Match) -> str:
        word, lower = match.group(0), match.group(0).casefold()
        before, after = question[:match.start()], question[match.end():]
        previous = re.search(r'(\w+)\s*$', before)
        if lower == 'that':
            return focus if previous is None or previous[1].casefold() in DEMONSTRATIVE_CUES else word
        if lower == 'it' and EXPLETIVE.match(re.sub(r'^\s+(?:is|was)\b', '', after)):
            return word  # "is it true ...", "it is possible ..."
        if lower == 'its':
            return focus + "'s"
        return focus
    return REFERENCE.sub(replace, question)


def resolve(question: str, history: list[dict]) -> tuple[str, str | None]:
    turns = history[-4:]
    if not turns:
        return question, None
    previous = turns[-1]
    focus = previous.get('focus', [])
    intent = previous.get('intent')
    if focus:
        question = _substitute(question, focus[0])
    return question, intent if re.match(r'\s*what about\b', question, re.I) else None
