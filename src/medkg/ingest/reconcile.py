"""Scoped assertion replacement preserving evidence from unselected chunks."""

import copy


def reconcile_edges(existing: list[dict],selected: set[str],retained: list[dict]) -> list[dict]:
    merged = {}
    for edge in existing:
        remaining = set(edge.get('evidence',[]))-selected
        if remaining:
            row = copy.deepcopy(edge)
            row['evidence'] = sorted(remaining)
            merged[(row['a'],row['b'],row['type'])] = row
    for edge in retained:
        key = (edge['a'],edge['b'],edge['type'])
        row = copy.deepcopy(edge)
        if key in merged:
            prior = merged[key]
            row['evidence'] = sorted(set(row['evidence'])|set(prior['evidence']))
            row['confidence'] = min(row.get('confidence',1),prior.get('confidence',1))
        merged[key] = row
    return list(merged.values())
