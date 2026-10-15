"""Synthetic offline package tests; no benchmark questions or system runs."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from eval import blind_review as blind


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf8')


@pytest.fixture
def inputs(tmp_path):
    cases = []
    for number, color in enumerate(('red', 'blue', 'green'), 1):
        cases.append({
            'id': f'fixture-{number}', 'question': f'What color is widget {number}?',
            'origin': 'synthetic',
            'required_claims': [{'claim_id': f'widget-{number}-color',
                                 'claim': f'Widget {number} is {color}.'}],
            'contexts': [{'id': f'private-graph/cache/source-{number}',
                          'text': f'Widget {number} is {color}.',
                          'path': 'do-not-export/private-graph.txt',
                          'uid': 'do-not-export'}],
            'safety_expectations': [{'id': 'no-invention',
                                     'text': 'Do not invent a widget property.'}],
            'author_model': 'NotPublic', 'old_judge_score': 100,
        })
    first = [{
        'id': case['id'], 'answer': f"{case['required_claims'][0]['claim']} "
        f"[{case['contexts'][0]['id']}]",
        'response_status': 'completed',
        'cited_context_ids': [case['contexts'][0]['id']],
        'model': 'NotPublic', 'trace': 'private-graph', 'elapsed_ms': 10, 'score': 1,
    } for case in cases]
    second = copy.deepcopy(first)
    second[1].update(answer='', response_status='failed', failure_reason='synthetic timeout',
                     cited_context_ids=[])
    for name, rows in [('cases', cases), ('first', first), ('second', second)]:
        write_rows(tmp_path / f'{name}.jsonl', rows)
    rubric = {'schema': blind.SCHEMA, 'rubric_id': 'fixture-rubric-1',
              'instructions': 'Inspect every claim against the frozen widget source.',
              'private_model': 'NotPublic'}
    (tmp_path / 'rubric.json').write_text(json.dumps(rubric), encoding='utf8')
    return tmp_path


def prepare(root, suffix='', seed=451):
    return blind.prepare(root / 'cases.jsonl',
                         [('private-graph', root / 'first.jsonl'),
                          ('private-vector', root / 'second.jsonl')],
                         root / 'rubric.json', root / f'public{suffix}',
                         root / f'private{suffix}', seed,
                         ('NotPublic',), root=root)


def make_labels(root, public='public'):
    labels = []
    for case in blind.read_rows(root / public / 'packet.jsonl'):
        for slot, answer in case['answers'].items():
            labels.append({
                'blind_id': case['blind_id'], 'slot': slot,
                'case_sha256': case['case_sha256'],
                'answer_sha256': answer['answer_sha256'],
                'rubric_sha256': case['rubric_sha256'],
                'origin': 'ai_review', 'reviewer_id': 'synthetic-test-reviewer',
                'reviewer_model': 'synthetic-fixture', 'human_attested': False,
                'clinical_validation': False,
                'required_claims': {item['claim_id']: 'covered'
                                    for item in case['required_claims']},
                'unsupported_claims': {'status': 'none', 'rationale': 'Synthetic test label.'},
                'contradictions': {'status': 'none', 'rationale': 'Synthetic test label.'},
                'uncertainty': {'status': 'appropriate', 'rationale': 'Synthetic test label.'},
                'safety_behaviors': {item['id']: 'met' for item in case['safety_expectations']},
                'rationale': 'Synthetic fixture only; no real assessment occurred.',
            })
    write_rows(root / 'labels.jsonl', labels)
    return labels


def summarize(root, receipt):
    return blind.summarize(root / 'public', root / 'private', root / 'labels.jsonl',
                           receipt['manifest_sha256'], root=root)


def test_synthetic_round_trip_preserves_failures_and_source_context(inputs):
    receipt = prepare(inputs)
    assert receipt['labels_assigned'] == 0
    make_labels(inputs)
    checked = blind.check(inputs / 'public', inputs / 'private', inputs / 'labels.jsonl',
                          receipt['manifest_sha256'], root=inputs)
    assert checked['integrity_valid'] and checked['labels_complete']
    assert checked['case_origins'] == {'synthetic': 3}
    result = summarize(inputs, receipt)
    assert result['systems']['private-graph']['pass'] == 3
    vector = result['systems']['private-vector']
    assert vector['all_cases'] == 3
    assert vector['pass'] == 2 and vector['fail'] == 1
    assert vector['response_failures'] == 1
    assert vector['reviewer_pass_fraction_all_cases'] == pytest.approx(2 / 3)
    assert vector['safety_gate'] == 'failed'
    assert vector['safety_response_failures'] == 1
    assert vector['observed_safety_violations'] == 0
    assert result['common_completed_subset']['private-vector'] == {'pass': 2}
    assert sum(result['paired_all_cases'].values()) == 3
    failed = next(item for item in result['items'] if item['response_status'] == 'failed')
    assert failed['quality_judgment'] == 'fail'
    assert failed['failure_reason'] == 'synthetic timeout'
    packet_text = (inputs / 'public' / 'packet.jsonl').read_text(encoding='utf8')
    for forbidden in ('private-graph', 'private-vector', 'NotPublic', 'elapsed_ms',
                      'trace', 'old_judge_score', 'do-not-export', 'synthetic timeout'):
        assert forbidden not in packet_text
    packet = blind.read_rows(inputs / 'public' / 'packet.jsonl')
    assert packet[0]['contexts'] == [{'id': 'S1', 'text': 'Widget 1 is red.'}]
    assert all('[S1]' in answer['answer'] for answer in packet[0]['answers'].values())


def test_reproducible_seed_mapping_and_recorded_display_transformation(inputs):
    first = blind.read_rows(inputs / 'first.jsonl')
    first[0]['answer'] += ' I am NOTPUBLIC.'
    write_rows(inputs / 'first.jsonl', first)
    receipt = prepare(inputs)
    prepare(inputs, '-repeat')
    assert (inputs / 'public/packet.jsonl').read_bytes() == (
        inputs / 'public-repeat/packet.jsonl').read_bytes()
    mapping = blind.read_json(inputs / 'private/mapping.json')
    assert mapping == blind.read_json(inputs / 'private-repeat/mapping.json')
    case = blind.read_rows(inputs / 'public/packet.jsonl')[0]
    slot = next(slot for slot, item in mapping['cases'][0]['assignments'].items()
                if item['system'] == 'private-graph')
    assert 'I am NOTPUBLIC.' in case['answers'][slot]['answer']
    assert mapping['cases'][0]['assignments'][slot]['identity_clues_present']
    assert mapping['cases'][0]['assignments'][slot]['display_transformed']
    make_labels(inputs)
    checked = blind.check(inputs / 'public', inputs / 'private', inputs / 'labels.jsonl',
                          receipt['manifest_sha256'], root=inputs)
    summary = summarize(inputs, receipt)
    for result in (receipt, checked, summary):
        assert result['answers_with_identity_clues'] == 1
        assert result['blinding_status'] == 'declared_identity_clues_present'
    # Different seeds can coincide for small samples; this pair demonstrably differs.
    prepare(inputs, '-different', seed=0)
    assert mapping['cases'] != blind.read_json(inputs / 'private-different/mapping.json')['cases']


@pytest.mark.parametrize('target', ['public/packet.jsonl', 'public/rubric.json',
                                  'private/mapping.json', 'private/manifest.json',
                                  'private/environment.json', 'cases.jsonl', 'first.jsonl'])
def test_tamper_detection_on_every_frozen_layer(inputs, target):
    receipt = prepare(inputs)
    make_labels(inputs)
    path = inputs / target
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='changed|differs'):
        summarize(inputs, receipt)


@pytest.mark.parametrize('field', ['case_sha256', 'answer_sha256', 'rubric_sha256'])
def test_rejects_labels_for_different_case_answer_or_rubric(inputs, field):
    receipt = prepare(inputs)
    labels = make_labels(inputs)
    labels[0][field] = '0' * 64
    write_rows(inputs / 'labels.jsonl', labels)
    with pytest.raises(ValueError, match='does not bind'):
        summarize(inputs, receipt)


@pytest.mark.parametrize('file,mutation', [
    ('first.jsonl', 'missing'), ('second.jsonl', 'missing'),
    ('first.jsonl', 'duplicate'), ('cases.jsonl', 'duplicate'),
    ('first.jsonl', 'empty_answer'), ('first.jsonl', 'unknown_source'),
    ('first.jsonl', 'no_status'), ('second.jsonl', 'no_failure_reason'),
])
def test_rejects_asymmetric_missing_duplicate_and_malformed_inputs(inputs, file, mutation):
    path = inputs / file
    rows = blind.read_rows(path)
    if mutation == 'missing':
        rows.pop()
    elif mutation == 'duplicate':
        rows.append(copy.deepcopy(rows[0]))
    elif mutation == 'empty_answer':
        rows[0]['answer'] = ''
    elif mutation == 'unknown_source':
        rows[0]['cited_context_ids'] = ['unknown-source']
    elif mutation == 'no_status':
        rows[0].pop('response_status')
    elif mutation == 'no_failure_reason':
        rows[1].pop('failure_reason')
    write_rows(path, rows)
    with pytest.raises(ValueError):
        prepare(inputs)
    assert not (inputs / 'public').exists()
    assert not (inputs / 'private').exists()


def test_existing_output_nested_output_and_duplicate_json_keys_rejected(inputs):
    prepare(inputs)
    with pytest.raises(ValueError, match='new paths'):
        prepare(inputs)
    with pytest.raises(ValueError, match='separate directories'):
        blind.prepare(inputs / 'cases.jsonl', [], inputs / 'rubric.json',
                      inputs / 'new', inputs / 'new/private', 1, root=inputs)
    (inputs / 'first.jsonl').write_text('{"id":"x","id":"x"}\n', encoding='utf8')
    with pytest.raises(ValueError, match='Duplicate JSON key'):
        prepare(inputs, '-invalid')


@pytest.mark.parametrize('change', [
    {'origin': 'human'}, {'origin': 'ai_review', 'human_attested': True},
    {'reviewer_model': None}, {'reviewer_id': 'TODO'}, {'rationale': 'pending'},
    {'origin': 'human_review', 'human_attested': False, 'reviewer_model': None},
    {'origin': 'human_review', 'human_attested': True}, {'clinical_validation': True},
    {'required_claims': {}}, {'safety_behaviors': {}},
    {'unsupported_claims': {'status': None, 'rationale': 'Synthetic label.'}},
])
def test_provenance_placeholders_and_incomplete_criteria_rejected(inputs, change):
    receipt = prepare(inputs)
    labels = make_labels(inputs)
    labels[0].update(change)
    write_rows(inputs / 'labels.jsonl', labels)
    with pytest.raises(ValueError):
        summarize(inputs, receipt)


def test_explicit_human_provenance_retained_separately(inputs):
    receipt = prepare(inputs)
    labels = make_labels(inputs)
    labels[0].update(origin='human_review', human_attested=True, reviewer_model=None)
    write_rows(inputs / 'labels.jsonl', labels)
    result = summarize(inputs, receipt)
    assert result['mixed_reviewer_origins'] is True
    assert result['review_origins'] == {'human_review': 1, 'ai_review': 5}
    assert result['clinical_validation'] is False


def test_uncertain_missing_and_negative_judgments_do_not_become_passes(inputs):
    receipt = prepare(inputs)
    labels = make_labels(inputs)
    labels[0]['required_claims']['C1'] = 'uncertain'
    labels[1]['unsupported_claims']['status'] = 'present'
    labels[2]['contradictions']['status'] = 'present'
    labels[3]['uncertainty']['status'] = 'inappropriate'
    labels[4]['safety_behaviors']['B1'] = 'uncertain'
    labels.pop()
    write_rows(inputs / 'labels.jsonl', labels)
    result = summarize(inputs, receipt)
    assert result['labels_complete'] is False
    assert sum(item['pass'] for item in result['systems'].values()) == 0
    assert sum(item['unresolved'] for item in result['systems'].values()) >= 2
    assert sum(item['missing_labels'] for item in result['systems'].values()) == 1


def test_no_labels_means_unresolved_with_failure_still_retained(inputs):
    receipt = prepare(inputs)
    (inputs / 'labels.jsonl').write_text('', encoding='utf8')
    result = summarize(inputs, receipt)
    assert result['systems']['private-graph']['unresolved'] == 3
    assert result['systems']['private-vector']['unresolved'] == 2
    assert result['systems']['private-vector']['fail'] == 1
    assert result['systems']['private-vector']['safety_response_failures'] == 1
    assert result['systems']['private-vector']['observed_safety_violations'] == 0
    assert result['systems']['private-graph']['reviewer_pass_fraction_all_cases'] is None
    assert result['systems']['private-vector']['reviewer_pass_fraction_all_cases'] is None
    assert result['review_origins'] == {}


def test_observed_safety_violation_is_distinct_from_response_failure(inputs):
    receipt = prepare(inputs)
    labels = make_labels(inputs)
    labels[0]['safety_behaviors']['B1'] = 'violated'
    write_rows(inputs / 'labels.jsonl', labels)
    totals = summarize(inputs, receipt)['systems'].values()
    assert sum(item['observed_safety_violations'] for item in totals) == 1
    assert sum(item['safety_response_failures'] for item in totals) == 1
    assert sum(item['safety_fail'] for item in totals) == 2


def test_identity_in_source_text_is_rejected_without_mutating_source(inputs):
    cases = blind.read_rows(inputs / 'cases.jsonl')
    cases[0]['contexts'][0]['text'] += ' NotPublic is the author.'
    write_rows(inputs / 'cases.jsonl', cases)
    with pytest.raises(ValueError, match='Case/source text contains'):
        prepare(inputs)
    assert blind.read_rows(inputs / 'cases.jsonl') == cases


def test_numeric_and_case_sensitive_source_ids_only_rewrite_explicit_citations(inputs):
    cases = blind.read_rows(inputs / 'cases.jsonl')
    cases[0]['contexts'] = [
        {'id': '1', 'text': 'There are 10 fictional widgets.'},
        {'id': 'chunk:a', 'text': 'The first observation.'},
        {'id': 'chunk:A', 'text': 'The second observation.'},
    ]
    write_rows(inputs / 'cases.jsonl', cases)
    for filename in ('first.jsonl', 'second.jsonl'):
        outputs = blind.read_rows(inputs / filename)
        outputs[0].update(answer='There are 10 fictional widgets. [1] [chunk:a] [chunk:A]',
                          cited_context_ids=['1', 'chunk:a', 'chunk:A'])
        write_rows(inputs / filename, outputs)
    prepare(inputs)
    for answer in blind.read_rows(inputs / 'public/packet.jsonl')[0]['answers'].values():
        assert answer['answer'] == 'There are 10 fictional widgets. [S1] [S2] [S3]'
        assert answer['cited_context_ids'] == ['S1', 'S2', 'S3']


@pytest.mark.parametrize('tokens,clues', [((), 0), (('10',), 1)])
def test_short_identity_tokens_do_not_change_factual_prose(inputs, tokens, clues):
    cases = blind.read_rows(inputs / 'cases.jsonl')
    for case in cases:
        case['safety_expectations'][0]['text'] = 'Do not invent widget properties.'
    write_rows(inputs / 'cases.jsonl', cases)
    outputs = blind.read_rows(inputs / 'first.jsonl')
    original = 'A1 and B2 are labels. There are 10 fictional widgets. [private-graph/cache/source-1]'
    outputs[0]['answer'] = original
    write_rows(inputs / 'first.jsonl', outputs)
    receipt = blind.prepare(inputs / 'cases.jsonl',
                            [('A', inputs / 'first.jsonl'), ('B', inputs / 'second.jsonl')],
                            inputs / 'rubric.json', inputs / 'public', inputs / 'private',
                            451, tokens, root=inputs)
    packet = blind.read_rows(inputs / 'public/packet.jsonl')
    assert any(answer['answer'] == 'A1 and B2 are labels. There are 10 fictional widgets. [S1]'
               for answer in packet[0]['answers'].values())
    assert receipt['answers_with_identity_clues'] == clues


def test_cli_subcommands_available_without_services():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-m', 'eval.blind_review', '--help'],
                            cwd=root, capture_output=True, text=True, check=False, timeout=20)
    assert result.returncode == 0
    assert 'prepare,check,summarize' in result.stdout
