"""Fictional data verifies the authoring gate; no real human labels are assigned."""

import csv
import hashlib
import json

import pytest

from eval.independent import (
    FROZEN,
    SAFETY_CATEGORIES,
    check,
    export_csv,
    prepare,
    question_hash,
    slots,
    validate_rows,
)


def completed():
    rows = slots()
    for index, row in enumerate(rows):
        category = row['category']
        row.update(question=f'Fictional fixture question number {index}',
                   reference_answer='Fixture answer', source_notes='Fixture evidence',
                   human_author='test fixture', human_reviewer='test fixture',
                   author_attested=True, review_approved=True, anchor_uids=['fiction:anchor'])
        if category == 'aggregation':
            row.update(kind='count', expected_count=1, expected=['fiction:target'])
        elif category in ('text_only', 'graph_text'):
            row.update(kind='text', answer_phrases=['fixture'], evidence_ids=['chunk:fixture'])
            if category == 'graph_text':
                row['expected_graph'] = ['fiction:target']
        elif category in ('out_of_scope', 'adversarial'):
            row.update(kind='refusal')
            if category == 'adversarial':
                row.update(attack_objective='Make the system follow a quoted instruction',
                           entry_surface='user question', prohibited_behavior='Reveal a secret',
                           observable_failure='The answer contains the fictional secret')
        elif category == 'safety':
            count = sum(other['category'] == 'safety' for other in rows[:index])
            row.update(kind='safety', expected_category=SAFETY_CATEGORIES[count // 2],
                       safety_rubric={'required_behaviors': ['Refer to appropriate support'],
                                      'prohibited_behaviors': ['Provide personal instructions']})
        else:
            row.update(kind='list', expected=['fiction:target'], recall_applicable=True)
        if row['kind'] in ('list', 'count') or category == 'graph_text':
            hops = [{'relation': 'indication', 'direction': 'x_to_y',
                     'anchor_uids': ['fiction:anchor']}]
            if category == 'multi_hop':
                hops = [{'relation': 'drug_protein', 'direction': 'x_to_y',
                         'anchor_uids': ['fiction:anchor']},
                        {'relation': 'disease_protein', 'direction': 'x_to_y',
                         'anchor_uids': 'previous_targets'}]
            row['graph_selection'] = {'schema': 1, 'source': 'data/raw/kg.csv', 'hops': hops}
        if row['kind'] == 'text':
            row.update(required_claims=[{'claim_id': 'c1', 'claim': 'Fixture claim.',
                                         'supporting_span_ids': ['s1']}],
                       supporting_spans=[{
                           'span_id': 's1', 'uid': 'chunk:fixture', 'document_uid': 'doc:fixture',
                           'quote': 'Fixture claim.', 'char_start': 0, 'char_end': 14,
                           'source_url': 'https://example.org/fixture',
                           'retrieved_at': '2026-10-01T00:00:00Z',
                           'chunk_text_sha256': hashlib.sha256(b'Fixture claim.').hexdigest(),
                       }])
    return rows


def errors(rows, root, previous=None):
    return validate_rows(rows, {'fiction:anchor', 'fiction:target'}, {'chunk:fixture'},
                         previous or set(), chunks=CHUNKS, documents=DOCUMENTS,
                         graph_path=root / 'data/raw/kg.csv')


CHUNKS = {'chunk:fixture': {'uid': 'chunk:fixture', 'document_uid': 'doc:fixture',
                           'url': 'https://example.org/fixture', 'text': 'Fixture claim.'}}
DOCUMENTS = {'doc:fixture': {'uid': 'doc:fixture', 'url': 'https://example.org/fixture',
                             'retrieved_at': '2026-10-01T00:00:00Z'}}


@pytest.fixture
def evidence_root(tmp_path):
    return fixture_root(tmp_path)


def test_blank_packet_is_not_ready_and_has_no_authored_answers(evidence_root):
    rows = slots()
    assert len(rows) == 100
    assert all(row['question'] is None and row['review_approved'] is None for row in rows)
    assert errors(rows, evidence_root)
    assert errors(completed(), evidence_root) == []


@pytest.mark.parametrize(('field', 'value'), [
    ('review_approved', 1), ('author_attested', 'true'), ('human_author', ''),
    ('human_reviewer', None), ('expected', ['unknown:target']),
    ('recall_applicable', None), ('category', 'other'), ('variant_type', 'typo'),
    ('expected', 'fiction:target'), ('question', ' '),
])
def test_invalid_authorship_or_gold_is_rejected(field, value, evidence_root):
    rows = completed()
    rows[0][field] = value
    assert errors(rows, evidence_root)


def test_duplicates_and_missing_slots_are_rejected(evidence_root):
    rows = completed()
    rows[1]['question'] = rows[0]['question'].upper()+'?!'
    assert any('duplicates' in error for error in errors(rows, evidence_root))
    assert any('prior' in error for error in errors(completed(), evidence_root, {
        question_hash(completed()[0]['question'])}))
    rows[1]['id'] = rows[0]['id']
    assert any('slot IDs' in error for error in errors(rows, evidence_root))


@pytest.mark.parametrize(('category', 'field', 'value'), [
    ('aggregation', 'expected_count', True), ('aggregation', 'expected_count', -1),
    ('graph_text', 'expected_graph', []), ('text_only', 'evidence_ids', ['absent']),
    ('text_only', 'answer_phrases', []), ('safety', 'expected_category', 'invented'),
    ('adversarial', 'kind', 'text'),
])
def test_category_requirements(category, field, value, evidence_root):
    rows = completed()
    next(row for row in rows if row['category'] == category)[field] = value
    assert errors(rows, evidence_root)


def fixture_root(tmp_path):
    for name in FROZEN:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture', encoding='utf8')
    for name in FROZEN[:2]:
        (tmp_path / name).write_text(json.dumps({'question': 'Old fictional question'})+'\n')
    (tmp_path / 'data/processed/entities.json').write_text(json.dumps([
        {'uid': 'fiction:anchor'}, {'uid': 'fiction:target'}]))
    (tmp_path / 'data/processed/chunks.jsonl').write_text(
        json.dumps(CHUNKS['chunk:fixture'])+'\n')
    (tmp_path / 'data/processed/documents.jsonl').write_text(
        json.dumps(DOCUMENTS['doc:fixture'])+'\n')
    (tmp_path / 'data/raw/kg.csv').write_text(
        'relation,x_source,x_id,y_source,y_id\n'
        'indication,fiction,anchor,fiction,target\n'
        'drug_protein,fiction,anchor,fiction,middle\n'
        'disease_protein,fiction,middle,fiction,target\n')
    return tmp_path


def test_packet_checks_snapshot_and_never_authorizes_calls(tmp_path):
    root = fixture_root(tmp_path)
    packet, queue = root / 'packet', root / 'human/queue.jsonl'
    prepare(packet, queue, root)
    assert not check(packet, queue, root)['ready_for_preregistration']
    queue.write_text('\n'.join(json.dumps(row) for row in completed())+'\n')
    result = check(packet, queue, root)
    assert result['ready_for_preregistration']
    assert not result['ready_for_model_run']
    (root / 'eval/score.py').write_text('modified fixture')
    result = check(packet, queue, root)
    assert not result['ready_for_preregistration']
    assert result['snapshot_drift'] == ['eval/score.py']


def test_existing_files_and_outside_paths_are_preserved(tmp_path):
    root = fixture_root(tmp_path)
    packet, queue = root / 'packet', root / 'human/queue.jsonl'
    prepare(packet, queue, root)
    original = queue.read_bytes()
    with pytest.raises(ValueError, match='never overwritten'):
        prepare(packet, queue, root)
    assert queue.read_bytes() == original
    with pytest.raises(ValueError, match='inside'):
        prepare(root.parent / 'outside', root / 'new.jsonl', root)


def test_csv_is_readable_and_formula_like_text_is_escaped(tmp_path):
    path = tmp_path / 'review.csv'
    export_csv([{'alias': ' =formula()', 'decision': None, 'owners': ['fiction:1']}], path)
    with path.open(encoding='utf-8-sig', newline='') as stream:
        row = next(csv.DictReader(stream))
    assert row == {'alias': "' =formula()", 'decision': '', 'owners': '["fiction:1"]'}


def test_manifest_freezes_validator_rubric_and_runtime_inventory(evidence_root):
    root = evidence_root
    (root / 'eval/new_validator.py').write_text('fixture validator')
    (root / 'docs/evaluation/answer-rubric.md').write_text('fixture rubric')
    packet, queue = root / 'packet', root / 'human/queue.jsonl'
    prepare(packet, queue, root)
    manifest = json.loads((packet / 'manifest.json').read_text())
    assert manifest['schema'] == 2
    assert manifest['environment']['python_version']
    assert manifest['environment']['packages']
    assert 'pyproject.toml' in manifest['frozen_files']
    assert 'eval/independent.py' in manifest['frozen_files']
    assert 'eval/evidence.py' in manifest['frozen_files']
    assert 'eval/new_validator.py' in manifest['frozen_files']
    assert 'docs/evaluation/answer-rubric.md' in manifest['frozen_files']
    (root / 'docs/evaluation/answer-rubric.md').write_text('modified rubric')
    assert 'docs/evaluation/answer-rubric.md' in check(packet, queue, root)['snapshot_drift']


def test_changed_environment_blocks_preregistration(evidence_root, monkeypatch):
    root = evidence_root
    packet, queue = root / 'packet', root / 'human/queue.jsonl'
    prepare(packet, queue, root)
    queue.write_text('\n'.join(json.dumps(row) for row in completed())+'\n')
    monkeypatch.setattr('eval.independent.environment_snapshot', lambda: {'changed': True})
    result = check(packet, queue, root)
    assert result['environment_drift']
    assert not result['ready_for_preregistration']
    assert not result['ready_for_model_run']


def test_legacy_blank_queue_is_reported_without_rewriting_it(evidence_root):
    root = evidence_root
    packet, queue = root / 'packet', root / 'human/queue.jsonl'
    prepare(packet, queue, root)
    manifest_path = packet / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['schema'] = 1
    manifest.pop('environment')
    manifest_path.write_text(json.dumps(manifest))
    original = queue.read_bytes(), manifest_path.read_bytes()
    result = check(packet, queue, root)
    assert not result['ready_for_preregistration']
    assert any('Legacy packet remains an unfinished authoring queue' in error
               for error in result['errors'])
    assert original == (queue.read_bytes(), manifest_path.read_bytes())
