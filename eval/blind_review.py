"""Freeze two output sets for offline blinded review; never run or judge QA."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'blind-review-1'
MAX_CASES = 10000
LIMITATION = ('Reviewer judgments are recorded, not verified semantic correctness or '
              'clinical safety. AI review is not human review. Hashes require a trusted '
              'manifest digest; stylistic and source-selection clues may remain.')


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf8')


def value_hash(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _pairs(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f'Invalid JSON constant: {value}')


def _parse_json(text: str, filename: str) -> dict:
    value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
    if not isinstance(value, dict):
        raise ValueError(f'JSON object required: {filename}')
    return value


def read_json(path: Path) -> dict:
    return _parse_json(path.read_text(encoding='utf8'), path.name)


def _parse_rows(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
        if not isinstance(row, dict):
            raise ValueError('Every JSONL row must be an object')
        rows.append(row)
    return rows


def read_rows(path: Path) -> list[dict]:
    return _parse_rows(path.read_text(encoding='utf8'))


def _read_snapshot(path: Path) -> tuple[bytes, str]:
    content = path.read_bytes()
    return content, hashlib.sha256(content).hexdigest()


def _verified_snapshot(path: Path, expected: str) -> bytes:
    content, digest = _read_snapshot(path)
    if digest != expected:
        raise ValueError(f'Frozen file changed: {path.name}')
    return content


def _label_snapshot(path: Path) -> tuple[list[dict], str]:
    content, digest = _read_snapshot(path)
    return _parse_rows(content.decode('utf8')), digest


def inside(path: Path, root: Path) -> Path:
    result = path.resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('All input/output paths must stay inside the repository')
    return result


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be nonempty text')
    return value


def _indexed(rows: list[dict], field: str = 'id') -> dict[str, dict]:
    result = {}
    for row in rows:
        key = _text(row.get(field), field)
        if key in result:
            raise ValueError(f'Duplicate {field}: {key}')
        result[key] = row
    return result


def _items(row: dict, field: str, id_field: str, text_field: str,
           nonempty: bool = False) -> list[dict]:
    values = row.get(field)
    if not isinstance(values, list) or (nonempty and not values):
        raise ValueError(f'{field} must be a {"nonempty " if nonempty else ""}list')
    if any(not isinstance(item, dict) for item in values):
        raise ValueError(f'{field} requires objects')
    _indexed(values, id_field)
    for item in values:
        _text(item.get(text_field), f'{field}.{text_field}')
    return values


def _cases(rows: list[dict]) -> dict[str, dict]:
    if not 1 <= len(rows) <= MAX_CASES:
        raise ValueError(f'Provide 1..{MAX_CASES} frozen cases')
    indexed = _indexed(rows)
    questions = set()
    for row in rows:
        question = _text(row.get('question'), 'question')
        normalized = ' '.join(question.casefold().split())
        if normalized in questions:
            raise ValueError('Duplicate question wording')
        questions.add(normalized)
        if row.get('origin') not in {'ai_authored', 'human_authored', 'synthetic'}:
            raise ValueError('Case origin must be ai_authored, human_authored or synthetic')
        _items(row, 'required_claims', 'claim_id', 'claim', nonempty=True)
        _items(row, 'contexts', 'id', 'text')
        _items(row, 'safety_expectations', 'id', 'text')
    return indexed


def _outputs(rows: list[dict], cases: dict[str, dict]) -> dict[str, dict]:
    indexed = _indexed(rows)
    if set(indexed) != set(cases):
        raise ValueError('Each system must provide exactly one output for every frozen case')
    for key, row in indexed.items():
        status = row.get('response_status')
        if status not in {'completed', 'failed'}:
            raise ValueError('response_status must be completed or failed')
        answer = row.get('answer')
        if not isinstance(answer, str) or (status == 'completed' and not answer.strip()):
            raise ValueError('Completed answers must be nonempty; failed answers remain strings')
        if status == 'failed':
            _text(row.get('failure_reason'), 'failure_reason')
        elif row.get('failure_reason') not in (None, ''):
            raise ValueError('Completed outputs cannot carry a failure_reason')
        cited = row.get('cited_context_ids')
        if (not isinstance(cited, list) or any(not isinstance(x, str) for x in cited)
                or len(cited) != len(set(cited))
                or not set(cited) <= {item['id'] for item in cases[key]['contexts']}):
            raise ValueError('cited_context_ids must be unique supplied context IDs')
    return indexed


def environment() -> dict:
    return {
        'python': sys.version, 'implementation': platform.python_implementation(),
        'platform': platform.platform(), 'executable': sys.executable,
        'packages': sorted((item.metadata['Name'], item.version)
                           for item in importlib.metadata.distributions()
                           if item.metadata['Name']),
    }


def _write_json(path: Path, value: object) -> None:
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def _write_rows(path: Path, rows: list[dict]) -> None:
    with path.open('xb') as stream:
        for row in rows:
            stream.write(canonical(row) + b'\n')


def _display_answer(text: str, sources: dict[str, str]) -> str:
    """Rewrite explicit [source-id] citations only; preserve factual prose."""
    replacements = {f'[{source}]': f'[{public}]' for source, public in sources.items()}
    if not replacements:
        return text
    pattern = '|'.join(re.escape(key) for key in sorted(replacements, key=len, reverse=True))
    return re.sub(pattern, lambda match: replacements[match.group()], text)


def _source_ids(contexts: list[dict], answers: list[str]) -> dict[str, str]:
    """Keep unknown citations unknown when assigning the public source namespace."""
    reserved = {item['id'] for item in contexts}
    for answer in answers:
        reserved.update(re.findall(r'\[([^\[\]]*)\]', answer))
    sources = {}
    number = 1
    for item in contexts:
        while f'S{number}' in reserved:
            number += 1
        sources[item['id']] = f'S{number}'
        number += 1
    return sources


def _has_identity(text: str, identities: list[str]) -> bool:
    """Flag declared prose identity clues without editing the answer being judged."""
    return any(re.search(r'(?<!\w)' + re.escape(token) + r'(?!\w)', text, re.IGNORECASE)
               for token in identities)


def prepare(cases_path: Path, systems: list[tuple[str, Path]], rubric_path: Path,
            public: Path, private: Path, seed: int,
            identity_tokens: tuple[str, ...] = (), root: Path = ROOT) -> dict:
    """Accept already authorized frozen inputs; authorization is not inferred here."""
    root = root.resolve()
    public, private = inside(public, root), inside(private, root)
    if public.exists() or private.exists():
        raise ValueError('Public and private output directories must use new paths')
    if public.is_relative_to(private) or private.is_relative_to(public):
        raise ValueError('Public packet and private records must be separate directories')
    if type(seed) is not int:
        raise ValueError('seed must be an integer')
    if len(systems) != 2:
        raise ValueError('Exactly two system output sets are required')
    names = [_text(name, 'system name') for name, _ in systems]
    if len({name.casefold() for name in names}) != 2:
        raise ValueError('Two distinct private system names are required')
    systems = [(name, inside(path, root)) for name, path in systems]
    cases_path, rubric_path = inside(cases_path, root), inside(rubric_path, root)
    inputs = [cases_path, rubric_path, *(path for _, path in systems)]
    if len(set(inputs)) != 4:
        raise ValueError('Cases, rubric and both output sets need distinct input files')
    before = {path.relative_to(root).as_posix(): file_hash(path) for path in inputs}
    cases = _cases(read_rows(cases_path))
    outputs = {name: _outputs(read_rows(path), cases) for name, path in systems}
    rubric_input = read_json(rubric_path)
    if rubric_input.get('schema') != SCHEMA:
        raise ValueError(f'Rubric schema must be {SCHEMA}')
    rubric = {key: _text(rubric_input.get(key), f'rubric.{key}')
              for key in ('rubric_id', 'instructions')}
    rubric['schema'] = SCHEMA
    rubric_hash = value_hash(rubric)
    identities = list(dict.fromkeys(names + [_text(x, 'identity token')
                                            for x in identity_tokens]))
    # Rubric text is shared and must be identity-neutral before it is frozen.
    if _has_identity(canonical(rubric).decode(), identities):
        raise ValueError('Rubric contains a declared system/model identity')
    rng = random.Random(seed)
    packet, mappings = [], []
    for index, (case_id, case) in enumerate(sorted(cases.items()), 1):
        blind_id = f'case-{index:05d}'
        sources = _source_ids(case['contexts'],
                              [outputs[name][case_id]['answer'] for name in names])
        claims = {item['claim_id']: f'C{i}'
                  for i, item in enumerate(case['required_claims'], 1)}
        behaviors = {item['id']: f'B{i}'
                     for i, item in enumerate(case['safety_expectations'], 1)}
        # Metadata is allowlisted; source IDs, paths, titles, timings and traces stay private.
        case_view = {
            'blind_id': blind_id, 'question': case['question'],
            'required_claims': [{'claim_id': claims[x['claim_id']],
                                 'claim': x['claim']}
                                for x in case['required_claims']],
            'contexts': [{'id': sources[x['id']], 'text': x['text']}
                         for x in case['contexts']],
            'safety_expectations': [{'id': behaviors[x['id']],
                                     'text': x['text']}
                                    for x in case['safety_expectations']],
        }
        if _has_identity(canonical(case_view).decode(), identities):
            raise ValueError('Case/source text contains a declared identity; '
                             'use neutral private system names or review the input')
        case_hash = value_hash(case_view)
        order = names.copy()
        rng.shuffle(order)
        answers, assignment = {}, {}
        for slot, name in zip(('A', 'B'), order, strict=True):
            output = outputs[name][case_id]
            view = {
                'answer': _display_answer(output['answer'], sources),
                'cited_context_ids': [sources[uid] for uid in output['cited_context_ids']],
                'response_status': output['response_status'],
            }
            answers[slot] = {**view, 'answer_sha256': value_hash(view)}
            assignment[slot] = {
                'system': name, 'raw_output_sha256': value_hash(output),
                'raw_answer_sha256': value_hash(output['answer']),
                'response_status': output['response_status'],
                'failure_reason': output.get('failure_reason'),
                'display_transformed': view['answer'] != output['answer'],
                'identity_clues_present': _has_identity(view['answer'], identities),
            }
        packet.append({**case_view, 'case_sha256': case_hash,
                       'rubric_sha256': rubric_hash, 'answers': answers})
        mappings.append({'blind_id': blind_id, 'case_id': case_id,
                         'case_origin': case['origin'], 'category': case.get('category'),
                         'raw_case_sha256': value_hash(case),
                         'source_ids': sources, 'claim_ids': claims, 'behavior_ids': behaviors,
                         'assignments': assignment})
    after = {path.relative_to(root).as_posix(): file_hash(path) for path in inputs}
    if before != after:
        raise ValueError('Input changed while preparing the package')
    runtime = environment()
    mapping = {'schema': SCHEMA, 'seed': seed, 'system_names': names,
               'identity_tokens': identities, 'cases': mappings}
    # Only create directories after every input is validated. Partial failures are preserved.
    public.mkdir(parents=True, exist_ok=False)
    private.mkdir(parents=True, exist_ok=False)
    _write_rows(public / 'packet.jsonl', packet)
    _write_json(public / 'rubric.json', rubric)
    _write_json(private / 'mapping.json', mapping)
    _write_json(private / 'environment.json', runtime)
    manifest = {
        'schema': SCHEMA, 'input_sha256': before, 'code_sha256': file_hash(Path(__file__)),
        'public_directory': public.relative_to(root).as_posix(),
        'packet_sha256': file_hash(public / 'packet.jsonl'),
        'rubric_file_sha256': file_hash(public / 'rubric.json'),
        'rubric_sha256': rubric_hash, 'mapping_sha256': file_hash(private / 'mapping.json'),
        'environment_sha256': file_hash(private / 'environment.json'),
        'case_count': len(packet), 'answer_count': len(packet) * 2,
        'case_origins': dict(Counter(case['origin'] for case in cases.values())),
        'answers_with_identity_clues': sum(assignment['identity_clues_present']
                                          for row in mappings
                                          for assignment in row['assignments'].values()),
        'llm_calls': 0, 'clinical_validation': False, 'limitation': LIMITATION,
    }
    manifest['blinding_status'] = (
        'declared_identity_clues_present' if manifest['answers_with_identity_clues'] else
        'metadata_blinded_residual_clues_unverified')
    _write_json(private / 'manifest.json', manifest)
    return {'schema': SCHEMA, 'cases': len(packet), 'answers': len(packet) * 2,
            'public': str(public), 'private': str(private),
            'manifest_sha256': file_hash(private / 'manifest.json'),
            'answers_with_identity_clues': manifest['answers_with_identity_clues'],
            'blinding_status': manifest['blinding_status'],
            'labels_assigned': 0, 'llm_calls': 0, 'limitation': LIMITATION}


def _load(public: Path, private: Path, manifest_sha256: str,
          root: Path) -> tuple[list[dict], dict, dict]:
    public, private = inside(public, root), inside(private, root)
    manifest_content, digest = _read_snapshot(private / 'manifest.json')
    if digest != manifest_sha256:
        raise ValueError('Manifest differs from the trusted prepare receipt')
    manifest = _parse_json(manifest_content.decode('utf8'), 'manifest.json')
    packet_content = _verified_snapshot(public / 'packet.jsonl', manifest['packet_sha256'])
    mapping_content = _verified_snapshot(private / 'mapping.json', manifest['mapping_sha256'])
    runtime_content = _verified_snapshot(private / 'environment.json',
                                         manifest['environment_sha256'])
    expected = {
        public / 'rubric.json': manifest['rubric_file_sha256'],
        Path(__file__): manifest['code_sha256'],
    }
    expected.update({inside(root / name, root): digest
                     for name, digest in manifest['input_sha256'].items()})
    for path, digest in expected.items():
        if file_hash(path) != digest:
            raise ValueError(f'Frozen file changed: {path.name}')
    runtime = _parse_json(runtime_content.decode('utf8'), 'environment.json')
    if value_hash(environment()) != value_hash(runtime):
        raise ValueError('Review runtime differs from the frozen environment')
    packet = _parse_rows(packet_content.decode('utf8'))
    mapping = _parse_json(mapping_content.decode('utf8'), 'mapping.json')
    return packet, mapping, manifest


def _enum(value: object, choices: set[str], name: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f'{name} must be one of {sorted(choices)}')
    return value


def _review_text(value: object, field: str) -> str:
    text = _text(value, field)
    if text.strip().casefold() in {
            'todo', 'tbd', 'pending', 'unreviewed', 'n/a', 'unknown', 'placeholder', '...',
            'not reviewed', 'fill in', 'none', 'null'}:
        raise ValueError(f'{field} cannot be a placeholder')
    return text


def _labels(rows: list[dict], packet: list[dict]) -> dict[tuple[str, str], dict]:
    cases = {row['blind_id']: row for row in packet}
    indexed = {}
    for row in rows:
        blind_id, slot = row.get('blind_id'), row.get('slot')
        if not isinstance(blind_id, str) or blind_id not in cases or slot not in ('A', 'B'):
            raise ValueError('Label must identify a blinded case and A/B slot')
        key = blind_id, slot
        if key in indexed:
            raise ValueError('Duplicate label for blinded case and slot')
        case = cases[blind_id]
        for field, expected in (
                ('case_sha256', case['case_sha256']),
                ('answer_sha256', case['answers'][slot]['answer_sha256']),
                ('rubric_sha256', case['rubric_sha256'])):
            if row.get(field) != expected:
                raise ValueError(f'Label {field} does not bind to this frozen answer')
        origin = _enum(row.get('origin'), {'ai_review', 'human_review'}, 'review origin')
        _review_text(row.get('reviewer_id'), 'reviewer_id')
        if row.get('clinical_validation') is not False:
            raise ValueError('clinical_validation must remain false')
        if origin == 'ai_review':
            _review_text(row.get('reviewer_model'), 'AI reviewer_model')
            if row.get('human_attested') is not False:
                raise ValueError('AI labels require human_attested=false')
        elif row.get('human_attested') is not True or row.get('reviewer_model') is not None:
            raise ValueError('Human review requires explicit attestation and no model identity')
        coverage, safety = row.get('required_claims'), row.get('safety_behaviors')
        if not isinstance(coverage, dict) or set(coverage) != {
                item['claim_id'] for item in case['required_claims']}:
            raise ValueError('Labels must cover exactly every required claim')
        if not isinstance(safety, dict) or set(safety) != {
                item['id'] for item in case['safety_expectations']}:
            raise ValueError('Labels must cover exactly every required safety behavior')
        for value in coverage.values():
            _enum(value, {'covered', 'missing', 'uncertain'}, 'claim status')
        for value in safety.values():
            _enum(value, {'met', 'violated', 'uncertain'}, 'safety status')
        for field in ('unsupported_claims', 'contradictions', 'uncertainty'):
            judgment = row.get(field)
            if not isinstance(judgment, dict):
                raise ValueError(f'{field} requires status and rationale')
            choices = ({'appropriate', 'inappropriate', 'uncertain'} if field == 'uncertainty'
                       else {'none', 'present', 'uncertain'})
            _enum(judgment.get('status'), choices, field)
            _review_text(judgment.get('rationale'), f'{field}.rationale')
        _review_text(row.get('rationale'), 'overall rationale')
        indexed[key] = row
    return indexed


def check(public: Path, private: Path, labels: Path, manifest_sha256: str,
          root: Path = ROOT) -> dict:
    packet, _, manifest = _load(public, private, manifest_sha256, root)
    rows, labels_sha256 = _label_snapshot(inside(labels, root))
    reviewed = _labels(rows, packet)
    return {'schema': SCHEMA, 'integrity_valid': True, 'labels_schema_valid': True,
            'labels_complete': len(reviewed) == len(packet) * 2,
            'expected_labels': len(packet) * 2, 'received_labels': len(reviewed),
            'missing_labels': len(packet) * 2 - len(reviewed),
            'review_origins': dict(Counter(row['origin'] for row in rows)),
            'case_origins': manifest['case_origins'], 'labels_sha256': labels_sha256,
            'answers_with_identity_clues': manifest['answers_with_identity_clues'],
            'blinding_status': manifest['blinding_status'],
            'clinical_validation': False, 'llm_calls': 0, 'limitation': LIMITATION}


def _verdict(label: dict | None, response_status: str,
             safety_applicable: bool) -> tuple[str, str]:
    if label is None:
        return ('fail' if response_status == 'failed' else 'unresolved'), (
            'not_applicable' if not safety_applicable else
            'fail' if response_status == 'failed' else 'unresolved')
    statuses = [*label['required_claims'].values(), *label['safety_behaviors'].values(),
                *(label[key]['status'] for key in
                  ('unsupported_claims', 'contradictions', 'uncertainty'))]
    bad = {'missing', 'violated', 'present', 'inappropriate'}
    quality = ('fail' if response_status == 'failed' or bad.intersection(statuses) else
               'unresolved' if 'uncertain' in statuses else 'pass')
    safety = label['safety_behaviors'].values()
    safety_result = ('not_applicable' if not safety_applicable else
                     'fail' if response_status == 'failed' or 'violated' in safety else
                     'unresolved' if 'uncertain' in safety else 'met')
    return quality, safety_result


def summarize(public: Path, private: Path, labels: Path, manifest_sha256: str,
              root: Path = ROOT) -> dict:
    """Unblind only for the custodian; missing/uncertain labels never imply a pass."""
    packet, mapping, manifest = _load(public, private, manifest_sha256, root)
    rows, labels_sha256 = _label_snapshot(inside(labels, root))
    reviewed = _labels(rows, packet)
    assignments = {row['blind_id']: row for row in mapping['cases']}
    totals = {name: {'all_cases': len(packet), 'pass': 0, 'fail': 0, 'unresolved': 0,
                     'response_failures': 0, 'missing_labels': 0, 'safety_cases': 0,
                     'safety_met': 0, 'safety_fail': 0, 'safety_unresolved': 0,
                     'safety_response_failures': 0, 'observed_safety_violations': 0}
              for name in mapping['system_names']}
    paired, items = Counter(), []
    common = {name: Counter() for name in totals}
    by_origin = {name: {} for name in totals}
    for case in packet:
        decisions = {}
        both_completed = all(answer['response_status'] == 'completed'
                             for answer in case['answers'].values())
        for slot, answer in case['answers'].items():
            assignment = assignments[case['blind_id']]['assignments'][slot]
            name = assignment['system']
            label = reviewed.get((case['blind_id'], slot))
            verdict, safety = _verdict(label, answer['response_status'],
                                       bool(case['safety_expectations']))
            tally = totals[name]
            tally[verdict] += 1
            tally['response_failures'] += answer['response_status'] == 'failed'
            tally['missing_labels'] += label is None
            if case['safety_expectations']:
                tally['safety_cases'] += 1
                tally[f'safety_{safety}'] += 1
                tally['safety_response_failures'] += answer['response_status'] == 'failed'
                tally['observed_safety_violations'] += (
                    label is not None and 'violated' in label['safety_behaviors'].values())
            if both_completed:
                common[name][verdict] += 1
            origin = label['origin'] if label else 'missing_label'
            origin_counts = by_origin[name].setdefault(origin, Counter())
            origin_counts['cases'] += 1
            origin_counts[verdict] += 1
            decisions[name] = verdict
            items.append({'case_id': assignments[case['blind_id']]['case_id'],
                          'case_origin': assignments[case['blind_id']]['case_origin'],
                          'category': assignments[case['blind_id']]['category'],
                          'blind_id': case['blind_id'], 'slot': slot, 'system': name,
                          'response_status': answer['response_status'],
                          'failure_reason': assignment['failure_reason'],
                          'identity_clues_present': assignment['identity_clues_present'],
                          'review_origin': label['origin'] if label else None,
                          'quality_judgment': verdict, 'safety_judgment': safety})
        paired[' / '.join(f'{name}:{decisions[name]}' for name in totals)] += 1
    for tally in totals.values():
        tally['reviewer_pass_fraction_all_cases'] = (
            tally['pass'] / tally['all_cases']
            if not tally['missing_labels'] and not tally['unresolved'] else None)
        tally['safety_gate'] = ('not_assessed' if not tally['safety_cases'] else
                                'failed' if tally['safety_fail'] else
                                'unresolved' if tally['safety_unresolved'] else
                                'reviewer_requirements_met')
    origins = Counter(row['origin'] for row in reviewed.values())
    return {'schema': SCHEMA, 'systems': totals, 'paired_all_cases': dict(paired),
            'common_completed_subset': {name: dict(counts) for name, counts in common.items()},
            'by_review_origin': {name: {origin: dict(counts) for origin, counts in groups.items()}
                                 for name, groups in by_origin.items()},
            'review_origins': dict(origins), 'case_origins': manifest['case_origins'],
            'mixed_reviewer_origins': len(origins) > 1,
            'labels_complete': len(reviewed) == len(packet) * 2,
            'labels_sha256': labels_sha256, 'manifest_sha256': manifest_sha256,
            'public_directory': manifest['public_directory'],
            'answers_with_identity_clues': manifest['answers_with_identity_clues'],
            'blinding_status': manifest['blinding_status'],
            'items': items, 'clinical_validation': False, 'llm_calls': 0,
            'limitation': LIMITATION}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prepare_parser = sub.add_parser('prepare')
    prepare_parser.add_argument('--cases', type=Path, required=True)
    prepare_parser.add_argument('--rubric', type=Path, required=True)
    prepare_parser.add_argument('--system', action='append', required=True, metavar='NAME=JSONL')
    prepare_parser.add_argument('--seed', type=int, required=True)
    prepare_parser.add_argument('--identity-token', action='append', default=[])
    for command in (prepare_parser, sub.add_parser('check'), sub.add_parser('summarize')):
        command.add_argument('--public', type=Path, required=True)
        command.add_argument('--private', type=Path, required=True)
        if command is not prepare_parser:
            command.add_argument('--labels', type=Path, required=True)
            command.add_argument('--manifest-sha256', required=True)
        if command.prog.endswith('summarize'):
            command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == 'prepare':
            systems = []
            for item in args.system:
                name, separator, path = item.partition('=')
                if not separator or not path:
                    raise ValueError('--system must use NAME=JSONL')
                systems.append((name, Path(path)))
            result = prepare(args.cases, systems, args.rubric, args.public, args.private,
                             args.seed, tuple(args.identity_token))
        else:
            func = check if args.action == 'check' else summarize
            result = func(args.public, args.private, args.labels, args.manifest_sha256)
            if args.action == 'summarize':
                output = inside(args.output, ROOT)
                public_paths = (inside(args.public, ROOT),
                                inside(ROOT / result['public_directory'], ROOT))
                if any(output.is_relative_to(path) for path in public_paths):
                    raise ValueError('Unblinded summaries must stay outside the public packet')
                _write_json(output, result)
                result = {'output': str(output), 'labels_complete': result['labels_complete'],
                          'clinical_validation': False, 'limitation': LIMITATION}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(2, f'Invalid blinded-review package: {exc}\n')
    print(json.dumps(result, indent=2))
    if args.action == 'check' and not result['labels_complete']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
