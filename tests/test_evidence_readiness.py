"""Fictional adversarial gold tests; no benchmark answers or human labels used."""

import copy
import hashlib

import pytest

from eval.evidence import derive_graph_targets, validate_evidence_rows, validate_text_evidence
from eval.independent import SAFETY_CATEGORIES, slots, validate_rows

TEXT = 'The fictional amber node is blue. Its partner is green.'
CHUNKS = {'chunk:one': {'uid': 'chunk:one', 'document_uid': 'doc:one', 'text': TEXT,
                       'url': 'https://example.org/one'}}
DOCUMENTS = {'doc:one': {'uid': 'doc:one', 'url': 'https://example.org/one',
                         'retrieved_at': '2026-10-01T00:00:00Z'}}


def text_row():
    return {
        'id': 'fictional-text', 'category': 'text_only', 'kind': 'text',
        'origin': 'ai_authored', 'evidence_ids': ['chunk:one'],
        'required_claims': [{'claim_id': 'c1', 'claim': 'The amber node is blue.',
                             'supporting_span_ids': ['s1']}],
        'supporting_spans': [{
            'span_id': 's1', 'uid': 'chunk:one', 'document_uid': 'doc:one',
            'quote': TEXT[:32], 'char_start': 0, 'char_end': 32,
            'source_url': 'https://example.org/one', 'retrieved_at': '2026-10-01T00:00:00Z',
            'chunk_text_sha256': hashlib.sha256(TEXT.encode('utf8')).hexdigest(),
        }],
    }


def selection(direction='x_to_y'):
    return {'schema': 1, 'source': 'data/raw/kg.csv', 'hops': [
        {'relation': 'indication', 'direction': direction, 'anchor_uids': ['fiction:a']}]}


@pytest.fixture
def graph(tmp_path):
    path = tmp_path / 'kg.csv'
    path.write_text(
        'relation,x_source,x_id,y_source,y_id\n'
        'indication,fiction,a,fiction,c\n'
        'indication,fiction,a,fiction,b\n'
        'indication,fiction,a,fiction,b\n'
        'indication,fiction,a,fiction,a\n'
        'drug_protein,fiction,b,fiction,10.0\n'
        'drug_protein,fiction,c,fiction,10\n'
        'unapproved_relation,fiction,a,fiction,ignored\n', encoding='utf8')
    return path


def graph_row(kind='list'):
    return {'id': 'fictional-graph',
            'category': 'aggregation' if kind == 'count' else 'single_hop', 'kind': kind,
            'anchor_uids': ['fiction:a'], 'graph_selection': selection(),
            'expected': ['fiction:a', 'fiction:b', 'fiction:c'], 'expected_count': 3}


def test_exact_text_integrity_never_claims_entailment_or_human_review():
    row = text_row()
    result = validate_evidence_rows([row], CHUNKS, DOCUMENTS)
    assert result['evidence_integrity_verified']
    assert result['verified_text_rows'] == 1
    assert result['claim_entailment'] == 'unverified'
    assert result['clinical_validation'] is False
    assert result['ready_for_model_run'] is False
    assert not any(key.startswith('human_') for key in row)
    row['required_claims'][0]['claim'] = 'The amber node is red.'
    result = validate_evidence_rows([row], CHUNKS, DOCUMENTS)
    assert result['evidence_integrity_verified']
    assert result['claim_entailment'] == 'unverified'


@pytest.mark.parametrize(('field', 'value'), [
    ('quote', 'The fictional amber node is red.'), ('char_start', 1), ('char_end', 31),
    ('char_start', False), ('char_end', 999), ('chunk_text_sha256', '0'*64),
    ('document_uid', 'doc:missing'), ('uid', 'chunk:missing'),
    ('source_url', 'https://example.org/other'), ('retrieved_at', '2020-01-01'),
])
def test_altered_spans_and_provenance_are_rejected(field, value):
    row = text_row()
    row['supporting_spans'][0][field] = value
    assert validate_text_evidence(row, CHUNKS, DOCUMENTS)


def test_chunk_must_belong_to_document_and_each_claim_must_have_known_spans():
    chunks = copy.deepcopy(CHUNKS)
    chunks['chunk:one']['document_uid'] = 'doc:other'
    assert validate_text_evidence(text_row(), chunks, DOCUMENTS)
    row = text_row()
    row['required_claims'][0]['supporting_span_ids'] = ['invented']
    assert validate_text_evidence(row, CHUNKS, DOCUMENTS)
    row = text_row()
    row['supporting_spans'].append(copy.deepcopy(row['supporting_spans'][0]))
    assert validate_text_evidence(row, CHUNKS, DOCUMENTS)


def test_graph_is_sorted_distinct_retains_self_edges_and_normalizes_csv_ids(graph):
    assert derive_graph_targets(selection(), graph) == ['fiction:a', 'fiction:b', 'fiction:c']
    two_hop = selection()
    two_hop['hops'].append({'relation': 'drug_protein', 'direction': 'x_to_y',
                            'anchor_uids': 'previous_targets'})
    assert derive_graph_targets(two_hop, graph) == ['fiction:10']


def test_invented_counts_and_targets_fail_even_when_ids_are_plausible(graph):
    row = graph_row('count')
    assert validate_evidence_rows([row], {}, {}, graph)['evidence_integrity_verified']
    row['expected_count'] = 4
    assert any('derived distinct count' in error
               for error in validate_evidence_rows([row], {}, {}, graph)['errors'])
    row = graph_row()
    row['expected'] = ['fiction:b']
    assert any('derived targets' in error
               for error in validate_evidence_rows([row], {}, {}, graph)['errors'])


def test_wrong_or_missing_direction_and_anchor_mismatch_fail(graph):
    row = graph_row()
    row['graph_selection']['hops'][0]['direction'] = 'y_to_x'
    assert not validate_evidence_rows([row], {}, {}, graph)['evidence_integrity_verified']
    row = graph_row()
    del row['graph_selection']['hops'][0]['direction']
    assert not validate_evidence_rows([row], {}, {}, graph)['evidence_integrity_verified']
    row = graph_row()
    row['anchor_uids'] = ['fiction:b']
    assert not validate_evidence_rows([row], {}, {}, graph)['evidence_integrity_verified']


def test_mixed_gold_compares_all_graph_targets_and_multi_hop_requires_both_steps(graph):
    row = text_row() | graph_row()
    row.update(category='graph_text', kind='text', expected_graph=['fiction:b'])
    result = validate_evidence_rows([row], CHUNKS, DOCUMENTS, graph)
    assert any('expected_graph' in error for error in result['errors'])
    row['expected_graph'] = ['fiction:a', 'fiction:b', 'fiction:c']
    assert validate_evidence_rows([row], CHUNKS, DOCUMENTS, graph)['evidence_integrity_verified']
    row = graph_row()
    row['category'] = 'multi_hop'
    assert any('two explicit relation steps' in error
               for error in validate_evidence_rows([row], {}, {}, graph)['errors'])


@pytest.mark.parametrize('mutation', [
    lambda item: item.update(query='MATCH (n) DETACH DELETE n'),
    lambda item: item.update(code='__import__("os").system("echo untrusted")'),
    lambda item: item.update(source='../outside.csv'),
    lambda item: item['hops'][0].update(relation='__import__("os")'),
    lambda item: item['hops'][0].update(direction='either'),
    lambda item: item['hops'][0].update(filter='exec("untrusted")'),
    lambda item: item['hops'].append({'relation': 'drug_protein', 'direction': 'x_to_y',
                                     'anchor_uids': ['fiction:b']}),
])
def test_only_typed_allowlisted_declarations_are_accepted(graph, mutation):
    item = selection()
    mutation(item)
    with pytest.raises(ValueError):
        derive_graph_targets(item, graph)


def test_safety_balance_is_a_machine_checked_requirement():
    rows = slots()
    safety = [row for row in rows if row['category'] == 'safety']
    for row in safety:
        row['expected_category'] = 'crisis'
    errors = validate_rows(rows, set(), set(), set())
    assert any('two cases per supported subtype' in error for error in errors)
    for index, row in enumerate(safety):
        row['expected_category'] = SAFETY_CATEGORIES[index // 2]
    errors = validate_rows(rows, set(), set(), set())
    assert not any('two cases per supported subtype' in error for error in errors)


@pytest.mark.parametrize('field', [
    'attack_objective', 'entry_surface', 'prohibited_behavior', 'observable_failure',
])
def test_adversarial_cases_require_an_observable_attack_contract(field):
    rows = slots()
    row = next(row for row in rows if row['category'] == 'adversarial')
    errors = validate_rows(rows, set(), set(), set())
    assert f'{row["id"]}: {field} is required for an adversarial case' in errors


@pytest.mark.parametrize('rows', [[], [{}], [{'id': []}], ['not a row'],
                                  [{'id': 'empty-kind'}], [{'id': 'x', 'kind': 'unknown'}]])
def test_empty_malformed_or_unknown_rows_do_not_pass_integrity(rows):
    assert not validate_evidence_rows(rows, {}, {})['evidence_integrity_verified']


def test_duplicate_row_ids_cannot_overwrite_derived_graph_results(graph):
    result = validate_evidence_rows([graph_row(), graph_row()], {}, {}, graph)
    assert not result['evidence_integrity_verified']
    assert any('duplicate evidence row id' in error for error in result['errors'])


@pytest.mark.parametrize('kind', ['safety', 'refusal'])
def test_kind_only_non_evidence_packet_reports_no_verified_text_or_graph(kind):
    result = validate_evidence_rows([{'id': 'no-evidence', 'kind': kind}], {}, {})
    assert result['evidence_integrity_verified']
    assert result['verified_text_rows'] == result['verified_graph_rows'] == 0
    assert result['clinical_validation'] is False


@pytest.mark.parametrize('category', [
    'single_hop', 'reverse', 'aggregation', 'multi_hop', 'lexical_variation',
])
@pytest.mark.parametrize('kind', ['safety', 'refusal', 'text'])
def test_graph_category_cannot_bypass_graph_checks_by_changing_kind(category, kind):
    row = text_row()
    row.update(category=category, kind=kind, anchor_uids=['fiction:a'],
               expected=['fiction:invented'], expected_count=987)
    result = validate_evidence_rows([row], CHUNKS, DOCUMENTS)
    assert not result['evidence_integrity_verified']
    assert any(f'{category} category requires kind' in error for error in result['errors'])


@pytest.mark.parametrize(('category', 'kind'), [
    ('text_only', 'safety'), ('graph_text', 'list'), ('aggregation', 'list'),
    ('single_hop', 'count'), ('out_of_scope', 'safety'), ('safety', 'refusal'),
    ('adversarial', 'safety'),
])
def test_known_category_requires_its_kind(category, kind):
    result = validate_evidence_rows([{'id': 'wrong-kind', 'category': category, 'kind': kind}],
                                    {}, {})
    assert not result['evidence_integrity_verified']
    assert any('category requires kind' in error for error in result['errors'])


@pytest.mark.parametrize('kind', ['list', 'count'])
def test_kind_only_graph_rows_still_reconstruct_targets(graph, kind):
    row = graph_row(kind)
    del row['category']
    result = validate_evidence_rows([row], {}, {}, graph)
    assert result['evidence_integrity_verified']
    assert result['verified_graph_rows'] == 1


@pytest.mark.parametrize('content', [
    'relation,x_source,x_id,y_source,y_id\nindication,fiction,a\n',
    'relation,x_source,x_id,y_source\nindication,fiction,a,fiction\n',
])
def test_malformed_selected_csv_is_a_validation_error(tmp_path, content):
    path = tmp_path / 'bad.csv'
    path.write_text(content, encoding='utf8')
    result = validate_evidence_rows([graph_row()], {}, {}, path)
    assert not result['evidence_integrity_verified']
    assert any('graph reconstruction failed' in error for error in result['errors'])
