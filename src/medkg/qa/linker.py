"""Exact, label-specific fuzzy, then precomputed alias-vector linking."""

import re
from dataclasses import asdict, dataclass

import numpy as np
from rapidfuzz import fuzz, process


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
        words = normalize(question).split()
        candidates, occupied = {}, set()
        for size in range(min(12, len(words)), 0, -1):
            for start in range(len(words)-size+1):
                positions = set(range(start, start+size))
                if occupied & positions:
                    continue
                key = ' '.join(words[start:start+size])
                if key in self.aliases:
                    ids = sorted(set(self.aliases[key]))
                    for uid in ids:
                        candidates[uid] = self._candidate(uid, 100, 'exact', len(ids)>1)
                    occupied |= positions
        if not candidates:
            # Extract explicit noun anchors rather than fuzz-matching the whole question.
            match = re.search(r'\b(?:of|for|about|with|does)\s+(.+?)(?:\?|$)', question, re.I)
            if match:
                candidates = {c.uid: c for c in self.link(match[1].strip())}
        return list(candidates.values())

    def describe(self, candidates: list[Candidate]) -> list[dict]:
        return [asdict(c) for c in candidates]
