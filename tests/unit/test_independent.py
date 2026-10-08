"""Fictional data verifies the authoring gate; no real human labels are assigned."""

import csv
import json

import pytest

from eval.independent import (
    FROZEN,
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
            row.update(kind='count', expected_count=0)
        elif category in ('text_only', 'graph_text'):
            row.update(kind='text', answer_phrases=['fixture'], evidence_ids=['chunk:fixture'])
            if category == 'graph_text':
                row['expected_graph'] = ['fiction:target']
        elif category in ('out_of_scope', 'adversarial'):
            row.update(kind='refusal')
        elif category == 'safety':
            row.update(kind='safety', expected_category='crisis')
        else:
            row.update(kind='list', expected=['fiction:target'], recall_applicable=True)
    return rows


def errors(rows, previous=None):
    return validate_rows(rows, {'fiction:anchor', 'fiction:target'}, {'chunk:fixture'},
                         previous or set())


def test_blank_packet_is_not_ready_and_has_no_authored_answers():
    rows = slots()
    assert len(rows) == 100
    assert all(row['question'] is None and row['review_approved'] is None for row in rows)
    assert errors(rows)
    assert errors(completed()) == []


@pytest.mark.parametrize(('field', 'value'), [
    ('review_approved', 1), ('author_attested', 'true'), ('human_author', ''),
    ('human_reviewer', None), ('expected', ['unknown:target']),
    ('recall_applicable', None), ('category', 'other'), ('variant_type', 'typo'),
    ('expected', 'fiction:target'), ('question', ' '),
])
def test_invalid_authorship_or_gold_is_rejected(field, value):
    rows = completed()
    rows[0][field] = value
    assert errors(rows)


def test_duplicates_and_missing_slots_are_rejected():
    rows = completed()
    rows[1]['question'] = rows[0]['question'].upper()+'?!'
    assert any('duplicates' in error for error in errors(rows))
    assert any('prior' in error for error in errors(completed(), {
        question_hash(completed()[0]['question'])}))
    rows[1]['id'] = rows[0]['id']
    assert any('slot IDs' in error for error in errors(rows))


@pytest.mark.parametrize(('category', 'field', 'value'), [
    ('aggregation', 'expected_count', True), ('aggregation', 'expected_count', -1),
    ('graph_text', 'expected_graph', []), ('text_only', 'evidence_ids', ['absent']),
    ('text_only', 'answer_phrases', []), ('safety', 'expected_category', 'invented'),
    ('adversarial', 'kind', 'text'),
])
def test_category_requirements(category, field, value):
    rows = completed()
    next(row for row in rows if row['category'] == category)[field] = value
    assert errors(rows)


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
        json.dumps({'uid': 'chunk:fixture'})+'\n')
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
