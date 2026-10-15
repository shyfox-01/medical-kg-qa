"""Offline evidence integrity checks, independent of QA and clinical judgment.

Offsets are Python Unicode character offsets into the exact cached chunk text.
Graph selections use raw CSV relation names and explicit x/y directions. They
retain self-edges, apply no implicit target or anchor exclusion, and collapse
duplicate paths/rows to a sorted set of final UIDs. These checks reconstruct
declared evidence; they do not verify that a question or claim means that evidence.
"""

import csv
import hashlib
from pathlib import Path

GRAPH_SOURCE = 'data/raw/kg.csv'
GRAPH_RELATIONS = frozenset({
    'indication', 'contraindication', 'off-label use', 'drug_drug', 'drug_effect',
    'disease_phenotype_positive', 'disease_protein', 'drug_protein', 'disease_disease',
})


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _strings(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(nonempty(x) for x in value)


def _unique_ids(values: list[dict], key: str, label: str) -> dict[str, dict]:
    found = {}
    for value in values:
        if not isinstance(value, dict) or not nonempty(value.get(key)):
            raise ValueError(f'{label} requires nonempty {key}')
        if value[key] in found:
            raise ValueError(f'{label} has duplicate {key}: {value[key]}')
        found[value[key]] = value
    return found


def validate_text_evidence(row: dict, chunks: dict[str, dict],
                           documents: dict[str, dict]) -> list[str]:
    """Check exact locators and claim-to-span references, never claim entailment."""
    errors = []
    spans, claims = row.get('supporting_spans'), row.get('required_claims')
    if not isinstance(spans, list) or not spans:
        errors.append('nonempty supporting_spans are required')
    if not isinstance(claims, list) or not claims:
        errors.append('nonempty required_claims are required')
    if errors:
        return errors
    try:
        by_span = _unique_ids(spans, 'span_id', 'supporting_spans')
        _unique_ids(claims, 'claim_id', 'required_claims')
    except ValueError as exc:
        return [str(exc)]
    used_spans = set()
    for claim in claims:
        references = claim.get('supporting_span_ids')
        if not nonempty(claim.get('claim')) or not _strings(references):
            errors.append('each required claim needs text and supporting_span_ids')
            continue
        if len(references) != len(set(references)) or not set(references) <= by_span.keys():
            errors.append(f'{claim["claim_id"]}: supporting_span_ids must be unique known spans')
        used_spans.update(references)
    if set(by_span) - used_spans:
        errors.append('every supporting span must be referenced by a required claim')
    evidence_ids = row.get('evidence_ids')
    if not _strings(evidence_ids):
        errors.append('nonempty evidence_ids are required')
    else:
        cited = [span.get('uid') for span in spans]
        if (any(not nonempty(uid) for uid in cited) or
                set(evidence_ids) != set(cited) or len(set(evidence_ids)) != len(evidence_ids)):
            errors.append('evidence_ids must equal the unique supporting chunk UIDs')
    for span in spans:
        prefix = f'{span["span_id"]}: '
        uid, document_uid = span.get('uid'), span.get('document_uid')
        chunk = chunks.get(uid) if isinstance(uid, str) else None
        document = documents.get(document_uid) if isinstance(document_uid, str) else None
        if chunk is None or document is None:
            errors.append(prefix+'chunk/document UID is absent from the frozen corpus')
            continue
        if chunk.get('document_uid') != document_uid:
            errors.append(prefix+'chunk does not belong to the declared document')
        url, date = span.get('source_url'), span.get('retrieved_at')
        if not nonempty(url) or url != document.get('url') or url != chunk.get('url'):
            errors.append(prefix+'source_url does not match chunk and document')
        if not nonempty(date) or date != document.get('retrieved_at'):
            errors.append(prefix+'retrieved_at does not match the cached document')
        text = chunk.get('text')
        if not isinstance(text, str):
            errors.append(prefix+'cached chunk has no text')
            continue
        if span.get('chunk_text_sha256') != hashlib.sha256(text.encode('utf8')).hexdigest():
            errors.append(prefix+'chunk_text_sha256 does not match cached text')
        start, end, quote = span.get('char_start'), span.get('char_end'), span.get('quote')
        if (type(start) is not int or type(end) is not int or
                not 0 <= start < end <= len(text) or not nonempty(quote) or
                text[start:end] != quote):
            errors.append(prefix+'quote and character offsets do not match cached text')
    return errors


def _selection_hops(selection: object) -> list[dict]:
    if not isinstance(selection, dict) or set(selection) != {'schema', 'source', 'hops'}:
        raise ValueError('graph_selection accepts only schema, source and hops; no query/code')
    if type(selection['schema']) is not int or selection['schema'] != 1:
        raise ValueError('graph_selection schema must be 1')
    if selection['source'] != GRAPH_SOURCE:
        raise ValueError(f'graph_selection source must be {GRAPH_SOURCE}')
    hops = selection['hops']
    if not isinstance(hops, list) or not 1 <= len(hops) <= 2:
        raise ValueError('graph_selection requires one or two hops')
    for index, hop in enumerate(hops):
        if not isinstance(hop, dict) or set(hop) != {'relation', 'direction', 'anchor_uids'}:
            raise ValueError('each hop accepts only relation, direction and anchor_uids')
        if not isinstance(hop['relation'], str) or hop['relation'] not in GRAPH_RELATIONS:
            raise ValueError('hop relation is outside the frozen raw CSV allowlist')
        if hop['direction'] not in ('x_to_y', 'y_to_x'):
            raise ValueError('hop direction must be x_to_y or y_to_x')
        anchors = hop['anchor_uids']
        if index == 0:
            if not _strings(anchors) or len(set(anchors)) != len(anchors):
                raise ValueError('first hop requires unique nonempty anchor_uids')
        elif anchors != 'previous_targets':
            raise ValueError('second-hop anchor_uids must be previous_targets')
    return hops


def derive_graph_targets(selection: dict, graph_path: Path) -> list[str]:
    """Stream only the supplied frozen CSV; never execute supplied strings.

    UID construction follows medkg_data.primekg.node: source + ':' + identifier,
    stripping a trailing '.0'. Direction is raw CSV x/y, not inferred medical
    direction or ontology subsumption. In particular disease_disease does not
    establish SUBTYPE_OF. No target filters or arbitrary expressions are accepted.
    """
    return _derive_many([selection], graph_path)[0]


def _derive_many(selections: list[dict], graph_path: Path) -> list[list[str]]:
    # At most two CSV passes for the whole batch, without loading the graph in RAM.
    plans = [_selection_hops(selection) for selection in selections]
    current = [set(plan[0]['anchor_uids']) for plan in plans]
    for index in range(max((len(plan) for plan in plans), default=0)):
        next_targets = [set() if index < len(plan) else current[i]
                        for i, plan in enumerate(plans)]
        lookup: dict[tuple[str, str], dict[str, set[int]]] = {}
        for i, plan in enumerate(plans):
            if index >= len(plan):
                continue
            hop = plan[index]
            anchors = lookup.setdefault((hop['relation'], hop['direction']), {})
            for uid in current[i]:
                anchors.setdefault(uid, set()).add(i)
        with graph_path.open(encoding='utf8', newline='') as stream:
            reader = csv.DictReader(stream)
            needed = {'relation', 'x_source', 'x_id', 'y_source', 'y_id'}
            if not needed <= set(reader.fieldnames or []):
                raise ValueError('frozen graph CSV is missing required columns')
            for edge in reader:
                relation = edge.get('relation')
                if not any((relation, direction) in lookup for direction in ('x_to_y', 'y_to_x')):
                    continue
                uids = {}
                for side in ('x', 'y'):
                    source, identifier = edge.get(f'{side}_source'), edge.get(f'{side}_id')
                    if not nonempty(source) or not nonempty(identifier):
                        raise ValueError('selected graph relation contains a missing source/ID')
                    uids[side] = source+':'+identifier.removesuffix('.0')
                for direction, a, b in (('x_to_y', 'x', 'y'), ('y_to_x', 'y', 'x')):
                    for i in lookup.get((relation, direction), {}).get(uids[a], ()):
                        next_targets[i].add(uids[b])
        current = next_targets
    return [sorted(targets) for targets in current]


def validate_evidence_rows(rows: list[dict], chunks: dict[str, dict],
                           documents: dict[str, dict], graph_path: Path | None = None) -> dict:
    """Reusable AI/human evidence lane, with no authorship or review attestations."""
    errors, graph_rows, selections, seen = [], [], [], set()
    verified_text_rows = verified_graph_rows = checked_text_rows = 0
    if not isinstance(rows, list) or not rows:
        errors.append('A nonempty list of evidence rows is required')
        rows = []
    for row in rows:
        if not isinstance(row, dict) or not nonempty(row.get('id')):
            errors.append('Every evidence row requires a nonempty string id')
            continue
        if row['id'] in seen:
            errors.append(f'{row["id"]}: duplicate evidence row id')
            continue
        seen.add(row['id'])
        prefix = f'{row.get("id", "<missing id>")}: '
        if row.get('kind') not in ('text', 'list', 'count', 'safety', 'refusal'):
            errors.append(prefix+'kind must be text, list, count, safety or refusal')
            continue
        if row.get('kind') == 'text' or row.get('category') in ('text_only', 'graph_text'):
            checked_text_rows += 1
            text_errors = validate_text_evidence(row, chunks, documents)
            errors.extend(prefix+error for error in text_errors)
            verified_text_rows += not text_errors
        if row.get('kind') in ('list', 'count') or row.get('category') == 'graph_text':
            try:
                hops = _selection_hops(row.get('graph_selection'))
                if row.get('category') == 'multi_hop' and len(hops) != 2:
                    raise ValueError('multi_hop requires two explicit relation steps')
                anchors = row.get('anchor_uids')
                if (not _strings(anchors) or len(set(anchors)) != len(anchors) or
                        set(anchors) != set(hops[0]['anchor_uids'])):
                    raise ValueError('row anchor_uids must equal first-hop anchor_uids')
                if graph_path is None:
                    raise ValueError('frozen graph CSV is required for graph verification')
                graph_rows.append(row)
                selections.append(row['graph_selection'])
            except ValueError as exc:
                errors.append(prefix+str(exc))
    derived = {}
    if selections:
        try:
            targets = _derive_many(selections, graph_path)
        except (ValueError, OSError, csv.Error) as exc:
            errors.append(f'graph reconstruction failed: {exc}')
        else:
            for row, expected in zip(graph_rows, targets, strict=True):
                identity = row.get('id', '<missing id>')
                derived[identity] = {'target_uids': expected, 'count': len(expected)}
                field = 'expected_graph' if row.get('category') == 'graph_text' else 'expected'
                before = len(errors)
                if row.get(field) != expected:
                    errors.append(f'{identity}: {field} must equal sorted distinct derived targets')
                if row.get('kind') == 'count' and (
                        type(row.get('expected_count')) is not int or
                        row['expected_count'] != len(expected)):
                    errors.append(f'{identity}: expected_count differs from derived distinct count')
                verified_graph_rows += len(errors) == before
    return {'evidence_integrity_verified': not errors, 'errors': errors,
            'checked_text_rows': checked_text_rows, 'verified_text_rows': verified_text_rows,
            'checked_graph_rows': len(graph_rows), 'verified_graph_rows': verified_graph_rows,
            'derived_graph': derived,
            'claim_entailment': 'unverified', 'clinical_validation': False,
            'ready_for_model_run': False}
