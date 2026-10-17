"""Benchmark v3 generator, scorer 3.9 kinds, behavioural summary and paired comparison (D091).

Fictional entities only.
"""

import json
import subprocess
import sys

import pytest

from eval import generate_v3 as v3
from eval.compare import compare, mcnemar_exact
from eval.run import summarize, wilson
from eval.score import Vocabulary, score

DRUGS = ['Asterol', 'Brinex', 'Corvane', 'Delmira', 'Estravil', 'Fendaxol', 'Glimorex', 'Hartaline']
DISEASES = ['Orion fever', 'Lyra disease', 'Vega syndrome', 'Rigel disorder', 'Mira syndrome']
PHENOTYPES = ['Amber spots', 'Indigo rash', 'Orion fever']
GENES = ['ORX1', 'LYR2']


def uid(kind: str, name: str) -> str:
    return f'fiction:{kind}:{name.lower().replace(" ", "-")}'


def world():
    catalog = ([{'uid': uid('drug', n), 'label': 'Drug', 'name': n, 'synonyms': []} for n in DRUGS]
               + [{'uid': uid('disease', n), 'label': 'Disease', 'name': n, 'synonyms': []} for n in DISEASES]
               + [{'uid': uid('phen', n), 'label': 'Phenotype', 'name': n, 'synonyms': []} for n in PHENOTYPES]
               + [{'uid': uid('gene', n), 'label': 'Gene', 'name': n, 'synonyms': []} for n in GENES])
    catalog[0]['synonyms'] = ['Asterolum']
    d, s, p, g = (lambda n: uid('drug', n)), (lambda n: uid('disease', n)), (lambda n: uid('phen', n)), (lambda n: uid('gene', n))
    edges = [('INDICATED_FOR', d('Asterol'), s('Orion fever')), ('INDICATED_FOR', d('Brinex'), s('Orion fever')),
             ('INDICATED_FOR', d('Corvane'), s('Lyra disease')), ('INDICATED_FOR', d('Delmira'), s('Vega syndrome')),
             ('CONTRAINDICATED_FOR', d('Brinex'), s('Lyra disease')),
             ('HAS_SIDE_EFFECT', d('Asterol'), p('Amber spots')), ('HAS_SIDE_EFFECT', d('Corvane'), p('Orion fever')),
             ('HAS_PHENOTYPE', s('Orion fever'), p('Indigo rash')),
             ('INTERACTS_WITH', d('Asterol'), d('Brinex')), ('INTERACTS_WITH', d('Asterol'), d('Corvane')),
             ('INTERACTS_WITH', d('Asterol'), d('Estravil')), ('INTERACTS_WITH', d('Brinex'), d('Fendaxol')),
             ('INTERACTS_WITH', d('Brinex'), d('Glimorex')), ('INTERACTS_WITH', d('Corvane'), d('Hartaline')),
             ('INTERACTS_WITH', d('Delmira'), d('Estravil')), ('INTERACTS_WITH', d('Delmira'), d('Fendaxol')),
             ('INTERACTS_WITH', d('Delmira'), d('Glimorex')),
             ('ASSOCIATED_WITH', s('Lyra disease'), g('ORX1')), ('TARGETS', d('Fendaxol'), g('ORX1')),
             ('SUBTYPE_OF', s('Rigel disorder'), s('Lyra disease')), ('OFF_LABEL_FOR', d('Glimorex'), s('Mira syndrome'))]
    graph = v3.Graph([{'uid': e['uid']} for e in catalog], [{'type': t, 'a': a, 'b': b} for t, a, b in edges])
    return graph, catalog


def builder(excluded=frozenset()):
    graph, catalog = world()
    return v3.Builder(graph, catalog, [], [], seed=7, excluded=set(excluded))


def test_new_relations_follow_csv_direction():
    graph, _ = world()
    assert graph.targets('parents', uid('disease', 'Rigel disorder')) == {uid('disease', 'Lyra disease')}
    assert graph.targets('subtypes', uid('disease', 'Lyra disease')) == {uid('disease', 'Rigel disorder')}
    assert graph.targets('off_label_drugs', uid('disease', 'Mira syndrome')) == {uid('drug', 'Glimorex')}
    assert graph.targets('targeting_drugs', uid('gene', 'ORX1')) == {uid('drug', 'Fendaxol')}
    assert graph.targets('associated_diseases', uid('gene', 'ORX1')) == {uid('disease', 'Lyra disease')}
    assert 'SUBTYPE_OF' in v3.single_query('parents') and v3.single_query('subtypes').count('<-') == 1


def test_single_rows_cover_every_intent_with_csv_gold_and_disjoint_anchors():
    b = builder()
    rows = b.singles(1)
    by_capability = {r['capability']: r for r in rows}
    row = by_capability['single.targeting_drugs']
    assert row['expected'] == [uid('drug', 'Fendaxol')] and row['test_type'] == 'MFT' and row['scope'] == 'in'
    assert 'single.parents' in by_capability and 'single.off_label' in by_capability
    assert all(b.used[u] == 1 for r in rows for u in r['anchor_uids'])


def test_excluded_anchors_are_never_sampled():
    b = builder(excluded={uid('drug', 'Fendaxol'), uid('gene', 'ORX1')})
    rows = b.singles(1)
    assert not any(uid('gene', 'ORX1') in r['anchor_uids'] or uid('drug', 'Fendaxol') in r['anchor_uids'] for r in rows)


def test_negative_rows_have_empty_gold_and_a_target_label():
    b = builder()
    for row in b.negative_rows(1):
        if row['capability'].startswith('negative.') and row['kind'] == 'none' and row.get('intent'):
            assert row['expected'] == [] and row['target_label'] == v3.RELATIONS[row['intent']][1]
            assert not b.g.targets(row['intent'], row['anchor_uids'][0])


def test_yes_no_rows_match_recorded_interactions():
    b = builder()
    rows = b.yesno_rows(1)
    for row in rows:
        a, other = row['gold_params']['a'], row['gold_params']['b']
        assert (other in b.g.targets('interactions', a)) == row['expected_answer']
        assert row['expected'] == ([other] if row['expected_answer'] else [])


def test_unknown_names_are_not_catalog_names():
    b = builder()
    name = b.unknown_name()
    assert v3.normalize(name) not in {v3.normalize(n) for n in DRUGS + DISEASES + PHENOTYPES + GENES}


def test_invariance_variants_keep_gold_and_point_to_their_base():
    b = builder()
    bases = v3.finish(b.singles(1), 'b1')
    variants = v3.finish(b.invariance(bases, 3), 'b1', len(bases) + 1)
    assert variants and all(v['test_type'] == 'INV' for v in variants)
    by_id = {r['id']: r for r in bases}
    for v in variants:
        base = by_id[v['base_id']]
        assert v['expected'] == base['expected'] and v['question'] != base['question']


def test_sealed_part_is_flagged():
    rows = v3.finish([{'question': 'q', 'kind': 'list'}], 'test')
    assert rows[0]['sealed'] and rows[0]['id'].startswith('v3-t-') and rows[0]['split'] == 'test'


VOCABULARY = Vocabulary(world()[1])


def scored(case, answer, refused=False):
    return score(case, {'answer': answer, 'contexts': [], 'refused': refused}, VOCABULARY)


@pytest.mark.parametrize('answer,refused,passed', [
    ('The knowledge graph records no drugs for Mira syndrome.', False, True),
    ('No supporting evidence was retrieved.', True, True),
    ('Asterol is used for Mira syndrome.', False, False),
])
def test_none_kind_passes_only_without_target_entities(answer, refused, passed):
    case = {'kind': 'none', 'expected': [], 'anchors': ['Mira syndrome'], 'anchor_uids': [uid('disease', 'Mira syndrome')],
            'target_label': 'Drug'}
    assert scored(case, answer, refused)['passed'] is passed


@pytest.mark.parametrize('expected_answer,answer,refused,passed', [
    (True, 'Yes, Asterol interacts with Brinex.', False, True),
    (True, 'There is no recorded interaction between Asterol and Brinex.', False, False),
    (False, 'No supporting evidence was retrieved.', True, True),
    (False, 'Asterol does not interact with Hartaline according to the graph.', False, True),
    (False, 'Yes, Asterol interacts with Hartaline.', False, False),
])
def test_yesno_kind(expected_answer, answer, refused, passed):
    other = 'Brinex' if expected_answer else 'Hartaline'
    case = {'kind': 'yesno', 'expected': [uid('drug', other)] if expected_answer else [],
            'anchors': ['Asterol', other], 'anchor_uids': [uid('drug', 'Asterol'), uid('drug', other)],
            'expected_answer': expected_answer, 'target_label': 'Drug'}
    assert scored(case, answer, refused)['passed'] is passed


@pytest.mark.parametrize('answer,refused,passed', [
    ('I could not find Zorvex in the knowledge base. Please check the name.', False, True),
    ('This name does not uniquely identify a supported drug.', True, True),
    ('Zorvex is used for Orion fever.', False, False),
])
def test_clarify_kind(answer, refused, passed):
    case = {'kind': 'clarify', 'expected': [], 'anchors': ['Zorvex'], 'anchor_uids': [], 'target_label': 'Disease'}
    assert scored(case, answer, refused)['passed'] is passed


def test_wilson_interval_and_exact_mcnemar():
    assert wilson(0, 0) is None
    low, high = wilson(150, 160)
    assert 0.88 < low < 0.94 < high < 0.97
    assert mcnemar_exact(0, 5) == 0.0625 and mcnemar_exact(2, 3) == 1.0 and mcnemar_exact(0, 0) == 1.0
    result = compare({'a': True, 'b': False, 'c': True}, {'a': True, 'b': True, 'c': False}, {'a': 'x', 'b': 'x', 'c': 'y'})
    assert result['all']['only_a'] == 1 and result['all']['only_b'] == 1 and result['x']['b_passed'] == 2


def record(i, category, passed, wrong=0):
    return {'id': i, 'category': category, 'failure_stage': None, 'execution_exact': None, 'latency_s': 1.0,
            'usage': {}, 'score': {'passed': passed, 'refused': False, 'wrong_entities': wrong}}


def test_behavioural_summary_reports_scope_invariance_and_graceful_failure():
    cases = [{'id': 'b', 'category': 'single_hop', 'capability': 'single.drugs_for', 'test_type': 'MFT', 'scope': 'in'},
             {'id': 'v', 'category': 'single_hop', 'capability': 'inv.lowercase', 'test_type': 'INV', 'scope': 'in',
              'base_id': 'b'},
             {'id': 'x', 'category': 'boundary', 'capability': 'boundary.disease_typo', 'test_type': 'BOUNDARY',
              'scope': 'boundary'}]
    rounds = [[record('b', 'single_hop', True), record('v', 'single_hop', False), record('x', 'boundary', False, 0)]]
    summary = summarize(rounds, cases)['behavioural']
    assert summary['in_scope']['passed'] == 1 and summary['in_scope']['questions'] == 2
    assert summary['invariance'] == {'pairs': 1, 'consistency': 0.0, 'robust_given_base_passed': 0.0}
    assert summary['boundary']['graceful_rate'] == 1.0
    assert summary['families']['inv']['pass_rate'] == 0.0


def test_sealed_questions_need_the_final_flag(tmp_path):
    dataset = tmp_path / 'sealed.jsonl'
    dataset.write_text(json.dumps({'id': 'v3-t-0001', 'category': 'single_hop', 'kind': 'list', 'question': 'q',
                                   'expected': [], 'split': 'test', 'sealed': True}) + '\n', encoding='utf8')
    done = subprocess.run([sys.executable, '-m', 'eval.run', '--dataset', str(dataset), '--split', 'test', '--fake',
                           '--output', str(tmp_path / 'out_summary.json')], capture_output=True, text=True)
    assert done.returncode == 2 and 'Sealed questions run only with --final' in done.stderr
