"""Progress events while a question is answered, for the web page's star map (D128).

A pipeline given an event callback reports what it found as it goes: the entities it linked,
each lookup's result entities, and when it writes the answer. Events describe; nothing in
answering depends on them, and a failing callback is ignored.
"""

import json
import re

RESULTS = 100   # result entities reported per lookup


def entity_rows(rows: list[dict]) -> list[dict]:
    """The entities among a lookup's rows (text chunks and counts are not entities), once each."""
    seen, found = set(), []
    for row in rows:
        uid = row.get('uid')
        if not isinstance(uid, str) or uid in seen or 'text' in row or not row.get('name'):
            continue
        seen.add(uid)
        found.append({'uid': uid, 'name': row['name']})
    return found


def step(kind: str, description: str | None, sources, rows: list[dict], within=(), expected=()) -> dict:
    """One lookup: the entities it started from, the earlier steps whose results it used
    ("$N" in the chain, "$stepN" in a plan), what it found, and the pair it checked."""
    results = entity_rows(rows)
    return {'kind': kind, 'description': description or '', 'sources': list(dict.fromkeys(sources))[:25],
            'within': sorted(set(within)), 'expected': list(expected), 'results': results[:RESULTS],
            'found': len(results), 'rows': len(rows)}


def plan_refs(args: dict) -> list[int]:
    """The plan steps a step's arguments refer to ("$step2" -> 2)."""
    return [int(n) for n in re.findall(r'\$step(\d+)', json.dumps(args))]
