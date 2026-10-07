"""Exact, label-specific fuzzy, then precomputed alias-vector linking."""

import re
from dataclasses import asdict, dataclass

import numpy as np
from rapidfuzz import fuzz, process

from medkg_data.lexicon import COMMON_WORDS, GENERIC_ANCHORS, ambiguous_word


def normalize(text: str) -> str:
    words = re.sub(r'[^\w\s]', ' ', text.casefold()).split()
    return ' '.join(w[:-1] if len(w)>4 and w.endswith('s') and not w.endswith(('ss','is','us'))
                    else w for w in words)


@dataclass
class Candidate:
    uid: str
    name: str
    label: str
    score: float
    method: str
    ambiguous: bool = False
    mention: str | None = None
    span: tuple[int,int] | None = None


class Linker:
    def __init__(self, entities: list[dict], embedder=None, vectors=None, vector_aliases=None):
        self.entities = {e['uid']: e for e in entities}
        self.aliases: dict[str, list[str]] = {}
        self.by_label: dict[str, dict[str, list[str]]] = {}
        for e in entities:
            for alias in [e['name'], *(e.get('synonyms') or [])]:
                key = normalize(alias)
                if key:
                    self.aliases.setdefault(key, []).append(e['uid'])
                    self.by_label.setdefault(e['label'], {}).setdefault(key, []).append(e['uid'])
        self.embedder, self.vectors, self.vector_aliases = embedder, vectors, vector_aliases
        self.alias_sizes = sorted({len(key.split()) for key in self.aliases},reverse=True)

    def link(self, mention: str, label: str | None = None) -> list[Candidate]:
        aliases = self.by_label.get(label, {}) if label else self.aliases
        key = normalize(mention)
        if key in aliases:
            ids = sorted(set(aliases[key]))
            return [self._candidate(uid, 100, 'exact', len(ids)>1) for uid in ids]
        matches = process.extract(key, aliases.keys(), scorer=fuzz.token_sort_ratio, limit=5,
                                  score_cutoff=92)
        scored = {}
        for alias, score, _ in matches:
            for uid in aliases[alias]:
                scored[uid] = max(score, scored.get(uid, 0))
        if scored:
            ranked = sorted(scored.items(), key=lambda x: (-x[1], x[0]))
            ambiguous = len(ranked)>1 and ranked[0][1]-ranked[1][1]<3
            return [self._candidate(uid, score, 'fuzzy', ambiguous) for uid, score in ranked[:5]]
        if self.vectors is not None and self.embedder is not None:
            similarities = self.vectors @ self.embedder.encode([mention])[0]
            ranked = []
            seen = set()
            for i in np.argsort(-similarities):
                uid = self.vector_aliases[int(i)]['uid']
                if similarities[i]<0.85:
                    break
                if uid not in seen and (not label or self.entities[uid]['label']==label):
                    ranked.append((uid, float(similarities[i])))
                    seen.add(uid)
                if len(ranked)==5:
                    break
            ambiguous = len(ranked)>1 and ranked[0][1]-ranked[1][1]<0.02
            return [self._candidate(uid, score, 'vector', ambiguous) for uid, score in ranked]
        return []

    def _candidate(self, uid: str, score: float, method: str, ambiguous: bool) -> Candidate:
        entity = self.entities[uid]
        return Candidate(uid, entity['name'], entity['label'], score, method, ambiguous)

    def in_question(self, question: str) -> list[Candidate]:
        return self.question_mentions(question)[0]

    def question_mentions(self, question: str) -> tuple[list[Candidate],list[str]]:
        """Link explicit mention spans independently, retaining unresolved anchors."""
        words = normalize(question).split()
        original = re.findall(r'\w+',question)
        candidates, occupied = {}, set()
        for size in self.alias_sizes:
            if size>len(words):
                continue
            for start in range(len(words)-size+1):
                positions = set(range(start, start+size))
                if occupied & positions:
                    continue
                key = ' '.join(words[start:start+size])
                if key in GENERIC_ANCHORS or ambiguous_word(key,' '.join(original[start:start+size])):
                    continue
                if key in self.aliases:
                    ids = sorted(set(self.aliases[key]))
                    for uid in ids:
                        candidates[uid] = self._candidate(uid, 100, 'exact', len(ids)>1)
                        candidates[uid].mention = ' '.join(original[start:start+size])
                        candidates[uid].span = (start,start+size)
                    occupied |= positions
        cues = {'of','for','about','with','does','and','between','versus','vs','is','are'}
        stops = cues | {'interact','interacts','target','targets','treat','treats','is',
                        'are','has','have','associated','recorded','indicated','cause','causes',
                        'side','effects','phenotypes','symptoms','contraindicated','indications'}
        generic = {'the','a','an','what','which','it','its','their','that','drug','drugs',
                   'disease','diseases','condition','conditions','gene','genes','protein',
                   'proteins','symptom','symptoms','phenotype','phenotypes','other','both',
                   'relationship','relationships','relation','relations','shared','common',
                   'how','can','could','should','i','you','we','explain','tell','list','find',
                   'information','data','evidence','these','those','some','any','warnings','warning',
                   'treatment','treatments','used','use','why','entities','anything','something',
                   'nothing','all','known','available','recorded'}
        unresolved = []
        interaction = bool(re.search(r'\binteract',question,re.I))
        labels = {c.label for c in candidates.values()}
        hint = 'Drug' if interaction else next(iter(labels)) if len(labels)==1 else None
        if hint is None and re.search(r'side effects?|targets?|indicated|contraindicated',question,re.I):
            hint = 'Drug'
        for start in range(len(words)):
            if (start and words[start-1] not in cues) or start in occupied or words[start] in generic:
                continue
            end = start
            while end<len(words) and end-start<12 and words[end] not in stops and end not in occupied:
                end += 1
            # A span such as "let me know which drug" is phrasing, not an entity:
            # drop leading generic/common words before treating it as a mention.
            first = start
            while first<end and (words[first] in generic or words[first] in COMMON_WORDS):
                first += 1
            if first==end:
                continue
            mention = ' '.join(words[first:end])
            linked = self.link(mention,hint)
            if linked:
                # Non-winning fuzzy/vector neighbors are alternatives, not extra
                # explicit anchors in a question. Preserve all ambiguous choices.
                for candidate in linked if linked[0].ambiguous else linked[:1]:
                    candidate.mention = ' '.join(original[first:end])
                    candidate.span = (first,end)
                    candidates.setdefault(candidate.uid,candidate)
                occupied.update(range(first,end))
            else:
                unresolved.append(mention)
        return list(candidates.values()),unresolved

    def describe(self, candidates: list[Candidate]) -> list[dict]:
        return [asdict(c) for c in candidates]


def label_choices(candidates: list) -> list[list] | None:
    """Group ambiguous mentions whose readings differ only by label.

    PrimeKG often has a Disease and a Phenotype with the same name ("gout"). Such
    a mention is resolvable from the requested relation. Returns the groups (empty
    when nothing is ambiguous), or None when a mention has several readings of one
    label, or lacks a span, which only a clarification can resolve. Accepts
    Candidate objects or their describe() dictionaries.
    """
    def field(candidate,key):
        return candidate.get(key) if isinstance(candidate,dict) else getattr(candidate,key,None)
    groups: dict[tuple,list] = {}
    for candidate in candidates:
        if not field(candidate,'ambiguous'):
            continue
        span = field(candidate,'span')
        if not span:
            return None
        groups.setdefault(tuple(span),[]).append(candidate)
    for group in groups.values():
        labels = [field(c,'label') for c in group]
        if len(group)<2 or None in labels or len(set(labels))<len(labels):
            return None
    return list(groups.values())
