"""Prepare blank human-authored evaluation slots and audit readiness, offline.

Readiness verifies attestations, evidence locators and declared graph selections,
not medical truth. This module never invokes a model or assigns human labels.
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from eval.evidence import nonempty, validate_evidence_rows

ROOT = Path(__file__).resolve().parents[1]
SAFETY_CATEGORIES = ('crisis', 'emergency', 'dosage', 'special_population', 'diagnosis_request')
QUOTAS = (
    ('single_hop', None, 7), ('reverse', None, 7), ('aggregation', None, 7),
    ('multi_hop', None, 7), ('lexical_variation', 'brand', 4),
    ('lexical_variation', 'lay', 4), ('lexical_variation', 'typo', 4),
    ('text_only', None, 15), ('graph_text', None, 15), ('out_of_scope', None, 10),
    ('safety', None, 10), ('adversarial', None, 10),
)
FROZEN = (
    'eval/datasets/structured_v1.jsonl', 'eval/datasets/structured_v2.jsonl',
    'data/raw/kg.csv', 'data/processed/entities.json', 'data/processed/chunks.jsonl',
    'data/processed/documents.jsonl', 'data/processed/extracted_edges.jsonl',
    'data/processed/vector_corpus.jsonl', 'data/processed/vector_corpus.npy',
    'data/processed/vector_aliases.json', 'data/processed/alias_vectors.npy',
    'eval/client.py', 'eval/score.py', 'eval/run.py', 'eval/independent.py',
    'eval/evidence.py', 'pyproject.toml', 'docs/evaluation/independent-evaluation.md',
)


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def question_hash(question: str) -> str:
    normalized = unicodedata.normalize('NFKC', question).casefold()
    return hashlib.sha256(' '.join(re.findall(r'\w+', normalized)).encode()).hexdigest()


def _parse_rows(content: bytes) -> list[dict]:
    return [json.loads(line) for line in content.decode('utf8').splitlines() if line]


def read_rows(path: Path) -> list[dict]:
    return _parse_rows(path.read_bytes())


def slots() -> list[dict]:
    rows = []
    for category, variant, count in QUOTAS:
        for _ in range(count):
            rows.append({
                'id': f'independent-{len(rows)+1:03d}', 'split': 'test',
                'category': category, 'variant_type': variant, 'question': None,
                'kind': None, 'expected': [], 'expected_count': None,
                'anchor_uids': [], 'answer_phrases': [], 'expected_graph': [],
                'evidence_ids': [], 'expected_category': None, 'recall_applicable': None,
                'reference_answer': None, 'source_notes': None,
                'required_claims': [], 'supporting_spans': [], 'graph_selection': None,
                'safety_rubric': None, 'attack_objective': None, 'entry_surface': None,
                'prohibited_behavior': None, 'observable_failure': None,
                'human_author': None, 'author_attested': None,
                'human_reviewer': None, 'review_approved': None,
            })
    return rows


def snapshot(root: Path) -> dict[str, str]:
    paths = [root / name for name in FROZEN]
    for directory in ('src', 'eval', 'scripts'):
        paths += sorted((root / directory).rglob('*.py'))
    paths += sorted((root / 'docs/evaluation').rglob('*.md'))
    return {path.relative_to(root).as_posix(): digest(path) for path in sorted(set(paths))}


def environment_snapshot() -> dict:
    """Nonsecret interpreter/package inventory; do not collect environment variables."""
    packages = sorted({(distribution.metadata['Name'], distribution.version)
                       for distribution in importlib.metadata.distributions()
                       if distribution.metadata['Name']})
    return {'python_version': sys.version, 'implementation': platform.python_implementation(),
            'system': platform.system(), 'machine': platform.machine(),
            'packages': [{'name': name, 'version': version} for name, version in packages]}


def inside(path: Path, root: Path = ROOT) -> Path:
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Paths must stay inside the repository')
    return path


def export_csv(rows: list[dict], path: Path) -> None:
    """Convenience copy only; the JSONL remains the authoritative review queue."""
    def cell(value):
        value = json.dumps(value) if isinstance(value, (list, dict)) else value
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
            return "'"+value
        return value

    with path.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: cell(value) for key, value in row.items()})


def prepare(output: Path, queue: Path, root: Path = ROOT) -> dict:
    output, queue = inside(output, root), inside(queue, root)
    if output.exists() or queue.exists():
        raise ValueError('Packet and queue must use new paths; originals are never overwritten')
    if queue.is_relative_to(output):
        raise ValueError('Keep the authoring queue separate from the immutable packet')
    hashes = snapshot(root)
    old_hashes = sorted({question_hash(row['question'])
                         for name in FROZEN[:2] for row in read_rows(root / name)})
    manifest = {'schema': 2, 'status': 'awaiting_human_authoring', 'slots': len(slots()),
                'frozen_files': hashes, 'prior_question_hashes': old_hashes,
                'environment': environment_snapshot(),
                'human_labels_assigned': 0, 'llm_calls': 0, 'downloads': 0}
    output.mkdir(parents=True)
    queue.parent.mkdir(parents=True, exist_ok=True)
    with queue.open('x', encoding='utf8') as stream:
        for row in slots():
            stream.write(json.dumps(row)+'\n')
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    export_csv(slots(), output / 'authoring.csv')
    return {'status': manifest['status'], 'slots': manifest['slots'],
            'packet': str(output), 'queue': str(queue), 'llm_calls': 0}


def validate_rows(rows: list[dict], known_uids: set[str], chunk_uids: set[str],
                  previous_hashes: set[str], *, chunks: dict[str, dict] | None = None,
                  documents: dict[str, dict] | None = None,
                  graph_path: Path | None = None) -> list[str]:
    errors, seen = [], set()
    if not isinstance(rows, list):
        return ['Authoring queue must be a list of row objects']
    seen_ids = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f'Authoring row {index} must be an object')
            continue
        identity = row.get('id')
        if not nonempty(identity):
            errors.append(f'Authoring row {index} requires a nonempty string id')
            continue
        if identity in seen_ids:
            errors.append(f'Authoring queue contains duplicate slot IDs: {identity}')
        seen_ids.add(identity)
    if errors:
        return errors
    expected_slots = {row['id']: row for row in slots()}
    ids = [row.get('id') for row in rows]
    if Counter(ids) != Counter(expected_slots.keys()):
        errors.append('Exactly the 100 assigned, unique slot IDs are required')
    for row in rows:
        identity = row.get('id')
        prefix = f'{identity}: '
        template = expected_slots.get(identity)
        if template is None:
            continue
        for field in ('split', 'category', 'variant_type'):
            if row.get(field) != template[field]:
                errors.append(prefix+f'{field} must match the assigned slot')
        for field in ('question', 'reference_answer', 'source_notes',
                      'human_author', 'human_reviewer'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                errors.append(prefix+f'{field} is required')
        for field in ('author_attested', 'review_approved'):
            if row.get(field) is not True:
                errors.append(prefix+f'{field} must be a human-supplied true')
        if isinstance(row.get('question'), str) and row['question'].strip():
            key = question_hash(row['question'])
            if key in previous_hashes or key in seen:
                errors.append(prefix+'question duplicates a prior or current normalized question')
            seen.add(key)
        for field, known in (('expected', known_uids), ('anchor_uids', known_uids),
                             ('expected_graph', known_uids), ('evidence_ids', chunk_uids)):
            values = row.get(field)
            if (not isinstance(values, list) or
                    any(not isinstance(uid, str) or uid not in known for uid in values)):
                errors.append(prefix+f'{field} must contain only known IDs')
        category, kind = template['category'], row.get('kind')
        required = ('count' if category == 'aggregation' else
                    'text' if category in ('text_only', 'graph_text') else
                    'refusal' if category in ('out_of_scope', 'adversarial') else
                    'safety' if category == 'safety' else 'list')
        if kind != required:
            errors.append(prefix+f'kind must be {required}')
        if required in ('list', 'count') and not row.get('anchor_uids'):
            errors.append(prefix+'structured gold requires anchor_uids')
        if required == 'list':
            if not row.get('expected') or type(row.get('recall_applicable')) is not bool:
                errors.append(prefix+'list gold requires expected and explicit recall_applicable')
        if required == 'count':
            count = row.get('expected_count')
            if type(count) is not int or count < 0:
                errors.append(prefix+'expected_count must be a nonnegative integer')
        if required == 'text':
            phrases = row.get('answer_phrases')
            if (not isinstance(phrases, list) or not phrases or
                    any(not isinstance(text, str) or not text.strip() for text in phrases)):
                errors.append(prefix+'text diagnostic requires nonempty answer_phrases')
            if not row.get('evidence_ids'):
                errors.append(prefix+'text gold requires cached evidence_ids')
            if category == 'graph_text' and not row.get('expected_graph'):
                errors.append(prefix+'mixed gold requires expected_graph')
        if required == 'safety':
            if row.get('expected_category') not in SAFETY_CATEGORIES:
                errors.append(prefix+'expected_category must be a supported safety category')
            rubric = row.get('safety_rubric')
            fields = ('required_behaviors', 'prohibited_behaviors')
            if (not isinstance(rubric, dict) or set(rubric) != set(fields) or
                    any(not isinstance(rubric[field], list) or not rubric[field] or
                        any(not nonempty(text) for text in rubric[field]) for field in fields)):
                errors.append(prefix+'safety_rubric requires required_behaviors and '
                              'prohibited_behaviors for separate semantic review')
        if category == 'adversarial':
            for field in ('attack_objective', 'entry_surface', 'prohibited_behavior',
                          'observable_failure'):
                if not nonempty(row.get(field)):
                    errors.append(prefix+f'{field} is required for an adversarial case')
    safety = Counter(row.get('expected_category') for row in rows
                     if row.get('category') == 'safety'
                     and isinstance(row.get('expected_category'), str))
    if safety != Counter({category: 2 for category in SAFETY_CATEGORIES}):
        errors.append('Safety quota requires exactly two cases per supported subtype')
    evidence = validate_evidence_rows(rows, chunks or {}, documents or {}, graph_path)
    errors.extend(evidence['errors'])
    return errors


def check(packet: Path, queue: Path, root: Path = ROOT) -> dict:
    manifest = json.loads((inside(packet, root) / 'manifest.json').read_text(encoding='utf8'))
    current = snapshot(root)
    frozen = manifest['frozen_files']
    compared = set(current) | set(frozen) if manifest.get('schema') == 2 else set(frozen)
    entities = json.loads((root / 'data/processed/entities.json').read_text(encoding='utf8'))
    chunks = read_rows(root / 'data/processed/chunks.jsonl')
    documents = read_rows(root / 'data/processed/documents.jsonl')
    queue = inside(queue, root)
    queue_bytes = queue.read_bytes()
    errors = validate_rows(_parse_rows(queue_bytes), {row['uid'] for row in entities},
                           {row['uid'] for row in chunks}, set(manifest['prior_question_hashes']),
                           chunks={row['uid']: row for row in chunks},
                           documents={row['uid']: row for row in documents},
                           graph_path=root / 'data/raw/kg.csv')
    if manifest.get('schema') != 2:
        errors.append('Legacy packet remains an unfinished authoring queue; a new schema-2 '
                      'packet with evidence, rubric and environment freeze is required')
    environment_drift = manifest.get('environment') != environment_snapshot()
    if environment_drift and manifest.get('schema') == 2:
        errors.append('Frozen interpreter/package environment has changed or is missing')
    if queue.read_bytes() != queue_bytes:
        errors.append('Authoring queue changed during validation; re-run the check')
    final_snapshot = snapshot(root)
    if manifest.get('schema') == 2:
        compared |= set(final_snapshot)
    drift = sorted(name for name in compared
                   if current.get(name) != frozen.get(name)
                   or final_snapshot.get(name) != frozen.get(name))
    return {'ready_for_preregistration': not errors and not drift,
            'ready_for_model_run': False, 'errors': errors, 'snapshot_drift': drift,
            'environment_drift': environment_drift, 'claim_entailment': 'unverified',
            'clinical_validation': False,
            'queue_sha256': hashlib.sha256(queue_bytes).hexdigest(), 'llm_calls': 0,
            'note': 'Attestations do not prove authorship or medical correctness. '
                    'A separate frozen scoring, blinding and budget plan is required before calls.'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'check'))
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--queue', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (prepare(args.packet, args.queue) if args.action == 'prepare'
                  else check(args.packet, args.queue))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f'Invalid or unavailable packet: {exc}\n')
    print(json.dumps(result, indent=2))
    if args.action == 'check' and not result['ready_for_preregistration']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
