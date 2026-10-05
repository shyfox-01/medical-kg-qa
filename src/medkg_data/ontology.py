"""Minimal OBO reader: identifiers, names, EXACT/layperson synonyms, parents, xrefs."""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Term:
    id: str = ''
    name: str = ''
    synonyms: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)
    xrefs: list[str] = field(default_factory=list)


def parse_obo(text: str) -> dict[str, Term]:
    terms: dict[str, Term] = {}
    term = None
    obsolete = False

    def save() -> None:
        if term and term.id and not obsolete:
            terms[term.id] = term

    for line in text.splitlines():
        line = line.strip()
        if line.startswith('['):
            save()
            term = Term() if line == '[Term]' else None
            obsolete = False
        elif term and ': ' in line:
            key, value = line.split(': ', 1)
            if key in ('id', 'name'):
                setattr(term, key, value)
            elif key == 'synonym':
                match = re.match(r'"((?:\\.|[^"\\])*)"\s+(.*)', value)
                if match and ('EXACT' in match[2] or 'layperson' in match[2].lower()):
                    term.synonyms.append(match[1].replace('\\"', '"'))
            elif key == 'is_a':
                term.parents.append(value.split()[0])
            elif key == 'xref':
                term.xrefs.append(value.split()[0])
            elif key == 'is_obsolete':
                obsolete = value == 'true'
    save()
    return terms


def load_obo(path: Path) -> dict[str, Term]:
    return parse_obo(path.read_text(encoding='utf8'))


def mondo_ids(node_id: str) -> list[str]:
    return ['MONDO:' + part.removeprefix('MONDO:').zfill(7)
            for part in node_id.split('_')]


def orientation(a: str, b: str, terms: dict[str, Term]) -> tuple[str, str] | None:
    aa, bb = set(mondo_ids(a)), set(mondo_ids(b))
    a_child = any(set(terms[x].parents) & bb for x in aa if x in terms)
    b_child = any(set(terms[x].parents) & aa for x in bb if x in terms)
    if a_child and not b_child:
        return a, b
    if b_child and not a_child:
        return b, a
    return None
