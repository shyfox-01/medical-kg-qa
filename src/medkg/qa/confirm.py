"""Confirm corrected names before answering (D105).

Exact mentions are used as written. A one-edit correction of a long name with no
look-alike drug or disease nearby is used with a visible note ("'Metfromin' was
read as Metformin"). Every other correction is asked back to the user: a fuzzy or
look-alike match, a vector-similarity match when the question names nothing else,
and the nearest spellings of an unresolved name. A vector match next to other
recognised entities is dropped, so ordinary words ("hands", "clear") cannot
become anchors. Look-alike and sound-alike drug names are a known source of
medication errors, so a wrong silent correction is worse than a question.
"""

import re
from dataclasses import dataclass, field

from medkg_data.lexicon import COMMON_WORDS, normalize

CONFIDENT_MIN_CHARS = 8


def suggestion_edits(word: str) -> int:
    """Edits allowed when suggesting a spelling for an unresolved word: two from nine
    letters, one from seven, none below. Looser limits turned ordinary words into
    drugs ("pension" -> Edrophonium, "testing" -> Estradiol)."""
    return 2 if len(word) >= 9 else 1 if len(word) >= 7 else 0


def shares_stem(mention: str, name: str) -> bool:
    """A vector match is suggested only when it shares a word stem with the mention
    ("asthmatics" -> asthma); without one it is unrelated ("MEDICINE" -> MED dysplasia)."""
    words = [w[:5] for w in normalize(mention).split() if len(w) >= 4]
    names = normalize(name).split()
    return any(n.startswith(w) or w.startswith(n[:5]) for w in words for n in names if len(n) >= 4)


@dataclass
class Review:
    kept: list = field(default_factory=list)
    unresolved: list = field(default_factory=list)
    corrections: list = field(default_factory=list)   # (mention, [Candidate])
    suggestions: list = field(default_factory=list)   # (mention, [Candidate])
    ignored: list = field(default_factory=list)       # ordinary words that matched an acronym (D116)


def _groups(candidates):
    groups: dict = {}
    for candidate in candidates:
        groups.setdefault(candidate.span or (candidate.mention, candidate.uid), []).append(candidate)
    return list(groups.values())


def review(linker, candidates: list, unresolved: list[str]) -> Review:
    result = Review(unresolved=list(unresolved))
    fuzzy, vector = [], []
    for group in _groups(candidates):
        methods = {c.method for c in group}
        if methods == {'exact'}:
            result.kept.extend(group)
        elif 'vector' in methods:
            vector.append(group)
        else:
            fuzzy.append(group)
    for group in fuzzy:
        mention = group[0].mention or group[0].name
        uids = {c.uid for c in group}
        # Several readings are confident only when they share one name (a Disease and a
        # Phenotype both called "methemoglobinemia"); two different names are asked back.
        # A space fix may also have one reading per label ("heartfailure": the Disease heart
        # failure and the Phenotype Congestive heart failure), as an exact name would.
        spacing = {c.method for c in group} == {'spacing'}
        one_name = len({normalize(c.name) for c in group}) == 1 or (
            spacing and len({c.label for c in group}) == len(group))
        confident = (one_name
                     and len(normalize(mention).replace(' ', '')) >= CONFIDENT_MIN_CHARS
                     # A space fix keeps the name's own letters (D107).
                     and all(c.method == 'spacing' or linker.edits_to(mention, c.uid) <= 1 for c in group)
                     and not linker.lookalikes(mention, uids))
        if confident:
            result.kept.extend(group)
            result.corrections.append((mention, group))
        else:
            result.suggestions.append((mention, group))
    anchored, dropped = bool(result.kept), []
    for group in vector:
        mention = group[0].mention or group[0].name
        related = [c for c in sorted(group, key=lambda c: -c.score) if shares_stem(mention, c.name)][:3]
        if anchored or not related:
            dropped.append(normalize(mention))
            result.unresolved.append(normalize(mention))
        else:
            result.suggestions.append((mention, related))
    # An unresolved single name (or an unrelated vector match) that is spelled like a
    # drug or disease gets suggestions.
    for mention in [*unresolved, *dropped]:
        edits = suggestion_edits(mention)
        if re.fullmatch(r'[a-z]+', mention) and edits and mention not in COMMON_WORDS:
            nearest = linker.nearest(mention, max_edits=edits)
            if nearest:
                result.suggestions.append((mention, nearest))
                result.unresolved.remove(mention)
    return result


JUDGE_PROMPT = (
    'You map a phrase from a medical question to entries of a knowledge graph. Choose the entry '
    'that names what the phrase refers to in this question. Words that only describe the question '
    '(safe, transmitted, prevent, storage, a dose or tablet strength, how severe or how long) do not '
    'change the entry. An entry that is broader than the phrase, or a different thing that shares a '
    'word, does not match: "hay fever" is not Fever, "skin cancer" is not just Cancer, "sodium '
    'deficiency" is not Sodium. If no entry names what the user means, answer 0.')
# The reply format: a bare number, whose token probabilities are read (D108), or JSON.
REPLY_NUMBER = ' Reply with the number only.'
REPLY_JSON = ' Reply with JSON {"choice": <number>} only.'


# The matched entity is kept only when the model gives it at least this probability.
KEEP_AT = 0.5
# Other entries are offered back from this probability on (the likeliest one always).
OFFER_AT = 0.1


def model_judge(llm):
    """The answer model as a constrained chooser among catalog entries (D106). Returns
    probabilities by option number (0 = none of these): read from the reply token where the
    endpoint gives log-probabilities (D108), else one JSON choice as certain; None on failure."""
    def judge(question: str, phrase: str, options: list) -> dict[int, float] | None:
        listing = '\n'.join(f'{i}. {c.name} ({c.label})' for i, c in enumerate(options, 1))
        user = {'role': 'user', 'content': f'Question: {question}\nPhrase: "{phrase.casefold()}"\n'
                                          f'Entries:\n{listing}\n0. none of these'}
        try:
            if callable(getattr(llm, 'choose', None)):
                scores = llm.choose([{'role': 'system', 'content': JUDGE_PROMPT + REPLY_NUMBER}, user],
                                    len(options))
                if scores:
                    return scores
            reply = llm.chat_json([{'role': 'system', 'content': JUDGE_PROMPT + REPLY_JSON}, user], 60)
            choice = int(reply.get('choice'))
        except Exception:
            return None
        return {choice: 1.0} if 0 <= choice <= len(options) else None
    return judge


def written(phrase: str, text: str) -> bool:
    """The phrase occurs in the text as typed (the demo page replaces it there)."""
    pattern = r'\W+'.join(map(re.escape, phrase.split()))
    return bool(re.search(rf'(?<!\w){pattern}(?!\w)', text, re.I))


def check_phrases(linker, question: str, checked: Review, judge, typed: str | None = None) -> Review:
    """Ask the model whether a partly matched phrase names the matched entity (D106).

    The model only chooses among catalog entries found by the linker. The match is kept
    when the model gives it at least KEEP_AT; otherwise the phrase becomes a "Did you mean"
    question for the user, never a silent anchor. A failed or invalid reply keeps the
    exact match, as before. A phrase that is not in
    the typed question (it came from a follow-up rewrite) is not checked, since the
    confirmed name could not replace it.
    """
    if judge is None:
        return checked
    for phrase, group in linker.partial_phrases(question, checked.kept):
        if typed is not None and not written(phrase, typed):
            continue
        options = {c.uid: c for c in group}
        for c in linker.link(phrase):
            options.setdefault(c.uid, c)
        options = list(options.values())[:6]
        scores = judge(question, phrase, options)
        if not scores:
            continue
        decision, offered = decide(scores, options, group)
        if decision == 'keep':
            continue
        checked.kept = [c for c in checked.kept if c not in group]
        if decision == 'ask':
            checked.suggestions.append((phrase, offered))
        else:
            # No entry names the phrase and the match is all but ruled out ("jock itch" is
            # not the gene ITCH): a name the catalog lacks, not a "Did you mean" (D116).
            checked.unresolved.append(normalize(phrase))
    return checked


def decide(scores: dict[int, float], options: list, group: list) -> tuple[str, list]:
    """'keep' the matched entry; 'ask' about the likelier other entries (the likeliest first,
    then any others and the match itself from OFFER_AT); when "none of these" is likelier
    than any other entry, 'ask' about the match if it keeps OFFER_AT, else 'none'."""
    matched = {i for i, c in enumerate(options, 1) if c in group}
    kept = sum(scores.get(i, 0.0) for i in matched)
    if kept >= KEEP_AT:
        return 'keep', []
    others = sorted((i for i in scores if i and i not in matched), key=lambda i: -scores[i])
    if not others or scores[others[0]] < scores.get(0, 0.0):
        return ('ask', list(group)) if kept >= OFFER_AT else ('none', [])
    offered = [options[others[0]-1]] + [options[i-1] for i in others[1:] if scores[i] >= OFFER_AT]
    return 'ask', offered + (group if kept >= OFFER_AT else [])


def rank_suggestions(question: str, checked: Review, judge) -> Review:
    """Order the candidates of an asked-back name by the model's reading of the question
    (D118): "hyptotension" offers hypotension and hypertension, and the question decides
    which comes first. Candidates under OFFER_AT are left out, the likeliest always stays,
    so a clear reading is one confirmation and a spread one a choice. The user still
    confirms; a failed reply, or "none of these" as the likeliest answer, keeps the spelling
    order."""
    if judge is None:
        return checked
    ranked = []
    for mention, group in checked.suggestions:
        scores = judge(question, mention, group[:6]) if len(group) > 1 else None
        if scores and max(scores.get(i+1, 0.0) for i in range(len(group[:6]))) >= scores.get(0, 0.0):
            order = sorted(range(len(group[:6])), key=lambda i: -scores.get(i+1, 0.0))
            group = [group[i] for i in order if i == order[0] or scores.get(i+1, 0.0) >= OFFER_AT]
        ranked.append((mention, group))
    checked.suggestions = ranked
    return checked


def check_words(linker, question: str, checked: Review, judge, typed: str | None = None) -> Review:
    """Ask the model about a lower-case word that matched only an acronym or a gene symbol
    (D116): "hard" (HARDS, hantavirus pulmonary syndrome) is an ordinary word and is dropped;
    "itch" (the gene ITCH) means Pruritus, which is asked back. The options are the match and
    its nearest catalog names; a failed or invalid reply keeps the match."""
    if judge is None:
        return checked
    for group in _groups(list(checked.kept)):
        if not all(linker.capitals_only(c) for c in group):
            continue
        word = group[0].mention
        if typed is not None and not written(word, typed):
            continue
        options = (group + linker.neighbors(word, {c.uid for c in group}))[:6]
        scores = judge(question, word, options)
        if not scores:
            continue
        decision, offered = decide(scores, options, group)
        if decision == 'keep':
            continue
        checked.kept = [c for c in checked.kept if c not in group]
        if decision == 'ask':
            checked.suggestions.append((word, offered))
        else:
            checked.ignored.append(word)
    return checked


def describe(groups: list) -> list[dict]:
    return [{'mention': mention, 'options': [{'uid': c.uid, 'name': c.name, 'label': c.label} for c in group]}
            for mention, group in groups]


def clarification(groups: list) -> str:
    lines = []
    for mention, group in groups:
        names = [c.name for c in group]
        if len(names) == 1:
            lines.append(f'Did you mean {names[0]}? You wrote "{mention}".')
        else:
            lines.append(f'Did you mean one of these? You wrote "{mention}": ' + '; '.join(names) + '.')
    return '\n'.join(lines) + '\nPlease confirm the name before I answer.'


def correction_notice(groups: list) -> str:
    parts = [f'"{mention}" as {" / ".join(c.name for c in group)}' for mention, group in groups]
    return 'Note: read ' + '; '.join(parts) + '.'
