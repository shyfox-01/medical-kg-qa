"""LiveQA generation uses only synthetic annotations, catalogs and graph edges."""

import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import pytest

from eval import build_liveqa as liveqa
from eval import generate_v2 as v2
from eval import generate_v3 as v3


@pytest.fixture
def world() -> tuple[v3.Graph, list[dict]]:
    catalog = [
        {'uid': 'drug:a', 'label': 'Drug', 'name': 'Asterol',
         'synonyms': ['ASTEROL', 'Asterolum', 'Asterolum']},
        {'uid': 'drug:b', 'label': 'Drug', 'name': 'Brinex', 'synonyms': ['Shared tonic']},
        {'uid': 'drug:c', 'label': 'Drug', 'name': 'Corvane', 'synonyms': ['Shared tonic']},
        {'uid': 'disease:a', 'label': 'Disease', 'name': 'Orion fever',
         'synonyms': ['Orion-fever']},
        {'uid': 'disease:b', 'label': 'Disease', 'name': 'Lyra disease', 'synonyms': []},
        {'uid': 'phenotype:a', 'label': 'Phenotype', 'name': 'Orion fever', 'synonyms': []},
        {'uid': 'phenotype:b', 'label': 'Phenotype', 'name': 'Amber spots', 'synonyms': []},
    ]
    edges = [
        ('INDICATED_FOR', 'drug:c', 'disease:a'),
        ('INDICATED_FOR', 'drug:a', 'disease:a'),
        ('HAS_SIDE_EFFECT', 'drug:a', 'phenotype:b'),
        ('HAS_PHENOTYPE', 'disease:a', 'phenotype:b'),
        ('CONTRAINDICATED_FOR', 'drug:a', 'disease:b'),
        ('INTERACTS_WITH', 'drug:b', 'drug:a'),
    ]
    graph = v3.Graph(catalog, [{'type': kind, 'a': a, 'b': b} for kind, a, b in edges])
    return graph, catalog


def question_xml(
    types: list[tuple[str, str]],
    foci: list[tuple[str, str, str]],
    *,
    qid: str = 'TQ1',
    subject: str = 'A health question',
    message: str = 'Please explain this question.',
    summary: str = 'What is the recorded answer?',
    keywords: list[tuple[str, str, str]] | None = None,
    keyword_refs: list[str] | None = None,
) -> str:
    focus_xml = ''.join(
        f'<FOCUS fid="{fid}" fcategory="{category}">{escape(text)}</FOCUS>'
        for fid, text, category in foci
    )
    keyword_xml = ''.join(
        f'<KEYWORD kid="{kid}" kcategory="{category}">{escape(text)}</KEYWORD>'
        for kid, text, category in keywords or []
    )
    type_xml = ''
    for i, (kind, refs) in enumerate(types, start=1):
        keyword_attribute = (f' hasKeyword="{keyword_refs[i - 1]}"'
                             if keyword_refs is not None else '')
        type_xml += f'<TYPE tid="T{i}" hasFocus="{refs}"{keyword_attribute}>{kind}</TYPE>'
    return f'''<NLM-QUESTION qid="{qid}">
        <Original-Question><SUBJECT>{escape(subject)}</SUBJECT>
            <MESSAGE>{escape(message)}</MESSAGE></Original-Question>
        <NLM-Summary>{escape(summary)}</NLM-Summary>
        <ANNOTATIONS>{focus_xml}{keyword_xml}{type_xml}</ANNOTATIONS>
    </NLM-QUESTION>'''


def build(world: tuple[v3.Graph, list[dict]], *questions: str) -> list[dict]:
    root = ET.fromstring(
        '<LiveQA2017-Medical-Test-Set-Full>' + ''.join(questions)
        + '</LiveQA2017-Medical-Test-Set-Full>'
    )
    return liveqa.build_rows(root, *world)


@pytest.mark.parametrize('text,expected', [
    ('  ＯＲＩＯＮ－Ｆｅｖｅｒ!!\t  ', 'orion fever'),
    ('Vitamin_B₁₂ / ５mg', 'vitamin b12 5mg'),
    ('Été—Straße', 'été straße'),
    ('...___---', ''),
])
def test_key_uses_nfkc_lowercase_and_alphanumeric_runs(text: str, expected: str) -> None:
    assert liveqa.key(text) == expected


@pytest.mark.parametrize('text,category,status,uid', [
    ('ORION--FEVER', 'Problem', 'linked', 'disease:a'),
    ('ＡＳＴＥＲＯＬＵＭ', 'DrugSupplement', 'linked', 'drug:a'),
    ('Asterol', 'DrugSupplement', 'linked', 'drug:a'),
    ('Shared tonic', 'DrugSupplement', 'ambiguous', None),
    ('Unknown tonic', 'DrugSupplement', 'unlinked', None),
    ('Amber spots', 'Problem', 'unlinked', None),
    ('Asterol', 'Problem', 'unlinked', None),
    ('Orion fever syndrome', 'Problem', 'unlinked', None),
    ('Asteroll', 'DrugSupplement', 'unlinked', None),
])
def test_linking_is_exact_and_restricted_to_required_label(
    world: tuple[v3.Graph, list[dict]], text: str, category: str,
    status: str, uid: str | None,
) -> None:
    focus = {'fid': 'F1', 'text': text, 'category': category}
    result = liveqa.link_focus(focus, liveqa.build_index(world[1]))
    assert result == {**focus, 'status': status, 'uid': uid}


@pytest.mark.parametrize('kind,category,text,intent,anchor,expected', [
    ('TREATMENT', 'Problem', 'Orion fever', 'drugs_for', 'disease:a', ['drug:a', 'drug:c']),
    ('INDICATION', 'DrugSupplement', 'Asterol', 'indications', 'drug:a', ['disease:a']),
    ('SIDE_EFFECT', 'DrugSupplement', 'Asterol', 'side_effects', 'drug:a', ['phenotype:b']),
    ('SYMPTOM', 'Problem', 'Orion fever', 'phenotypes', 'disease:a', ['phenotype:b']),
    ('CONTRAINDICATION', 'DrugSupplement', 'Asterol', 'contraindications',
     'drug:a', ['disease:b']),
    ('INTERACTION', 'DrugSupplement', 'Asterol', 'interactions', 'drug:a', ['drug:b']),
])
def test_all_single_focus_mappings_use_graph_gold(
    world: tuple[v3.Graph, list[dict]], kind: str, category: str, text: str,
    intent: str, anchor: str, expected: list[str],
) -> None:
    rows = build(world, question_xml([(kind, 'F1')], [('F1', text, category)]))
    names = {entity['uid']: entity['name'] for entity in world[1]}
    assert len(rows) == 2
    for row in rows:
        assert row['split'] == 'liveqa'
        assert row['scope'] == 'in'
        assert row['kind'] == 'list'
        assert row['intent'] == intent
        assert row['capability'] == f'real.{intent}'
        assert row['category'] == f'real_{intent}'
        assert row['expected'] == expected
        assert row['expected_names'] == {uid: [names[uid]] for uid in expected}
        assert row['gold_query'] == v3.single_query(intent)
        assert row['gold_params'] == {'uid': anchor}
        assert row['recall_applicable'] is True
        assert row['anchors'] == [text]
        assert row['anchor_uids'] == [anchor]
        assert row['anchor_pool'] == 'real'
        assert row['test_type'] == 'REAL'
        assert row['generator_version'] == 'liveqa-2'
        assert row['question_template'] == row['question']
        assert row['liveqa']['qid'] == 'TQ1'
        assert row['liveqa']['types'] == [kind]
        assert row['liveqa']['foci'] == [
            {'fid': 'F1', 'text': text, 'category': category,
             'uid': anchor, 'status': 'linked'}]
        assert row['liveqa']['keywords'] == []
        assert row['liveqa']['malformed_annotation'] is False
        assert row['liveqa']['reason']


@pytest.mark.parametrize('partner,expected_answer,expected', [
    ('Brinex', True, ['drug:b']),
    ('Corvane', False, []),
])
def test_interaction_yesno_covers_recorded_and_absent_edges(
    world: tuple[v3.Graph, list[dict]], partner: str,
    expected_answer: bool, expected: list[str],
) -> None:
    rows = build(world, question_xml([('INTERACTION', 'F1,F2')], [
        ('F1', 'Asterol', 'DrugSupplement'), ('F2', partner, 'DrugSupplement')]))
    partner_uid = 'drug:b' if expected_answer else 'drug:c'
    for row in rows:
        assert row['split'] == 'liveqa'
        assert row['scope'] == 'in'
        assert row['kind'] == 'yesno'
        assert row['capability'] == 'real.interaction_yesno'
        assert row['category'] == 'real_interaction_yesno'
        assert row['intent'] == 'interactions'
        assert row['target_label'] == 'Drug'
        assert row['expected_answer'] is expected_answer
        assert row['expected'] == expected
        assert row['gold_params'] == {'a': 'drug:a', 'b': partner_uid}
        assert row['gold_query'] == (
            'MATCH (a:Drug {uid:$a})-[:INTERACTS_WITH]-(b:Drug {uid:$b}) '
            'RETURN DISTINCT b.uid AS uid')
        assert row['recall_applicable'] is False


@pytest.mark.parametrize('answer', [True, False])
@pytest.mark.parametrize('kind,focus,intent,anchor,pairs,target_label,pattern', [
    ('TREATMENT', ('Orion fever', 'Problem'), 'drugs_for', 'disease:a',
     [('Asterol', 'drug:a'), ('Brinex', 'drug:b')], 'Drug',
     '(a:Disease {uid:$a})<-[:INDICATED_FOR]-(b:Drug {uid:$b})'),
    ('INDICATION', ('Asterol', 'DrugSupplement'), 'indications', 'drug:a',
     [('Orion fever', 'disease:a'), ('Lyra disease', 'disease:b')], 'Disease',
     '(a:Drug {uid:$a})-[:INDICATED_FOR]->(b:Disease {uid:$b})'),
    ('SIDE_EFFECT', ('Asterol', 'DrugSupplement'), 'side_effects', 'drug:a',
     [('Amber spots', 'phenotype:b'), ('Orion fever', 'phenotype:a')], 'Phenotype',
     '(a:Drug {uid:$a})-[:HAS_SIDE_EFFECT]->(b:Phenotype {uid:$b})'),
    ('SYMPTOM', ('Orion fever', 'Problem'), 'phenotypes', 'disease:a',
     [('Amber spots', 'phenotype:b'), ('Orion fever', 'phenotype:a')], 'Phenotype',
     '(a:Disease {uid:$a})-[:HAS_PHENOTYPE]->(b:Phenotype {uid:$b})'),
    ('CONTRAINDICATION', ('Asterol', 'DrugSupplement'), 'contraindications', 'drug:a',
     [('Lyra disease', 'disease:b'), ('Orion fever', 'disease:a')], 'Disease',
     '(a:Drug {uid:$a})-[:CONTRAINDICATED_FOR]->(b:Disease {uid:$b})'),
    ('INTERACTION', ('Asterol', 'DrugSupplement'), 'interactions', 'drug:a',
     [('Brinex', 'drug:b'), ('Corvane', 'drug:c')], 'Drug',
     '(a:Drug {uid:$a})-[:INTERACTS_WITH]-(b:Drug {uid:$b})'),
])
def test_keyword_pair_gold_uses_each_intents_target_label_and_direction(
    world: tuple[v3.Graph, list[dict]], answer: bool, kind: str,
    focus: tuple[str, str], intent: str, anchor: str, pairs: list[tuple[str, str]],
    target_label: str, pattern: str,
) -> None:
    keyword, target = pairs[0 if answer else 1]
    rows = build(world, question_xml([(kind, 'F1')], [('F1', *focus)],
                 keywords=[('K1', keyword, 'UnrelatedCategory')], keyword_refs=['K1']))
    capability = 'interaction_yesno' if intent == 'interactions' else f'{intent}_yesno'
    category = 'interaction_yesno' if intent == 'interactions' else intent
    names = {entity['uid']: entity['name'] for entity in world[1]}
    for row in rows:
        assert row['split'] == 'liveqa'
        assert row['scope'] == 'in'
        assert row['kind'] == 'yesno'
        assert row['intent'] == intent
        assert row['capability'] == f'real.{capability}'
        assert row['category'] == f'real_{category}'
        assert row['target_label'] == target_label
        assert row['expected_answer'] is answer
        assert row['expected'] == ([target] if answer else [])
        assert row['expected_names'] == ({target: [names[target]]} if answer else {})
        assert row['gold_query'] == f'MATCH {pattern} RETURN DISTINCT b.uid AS uid'
        assert row['gold_params'] == {'a': anchor, 'b': target}
        assert row['recall_applicable'] is False
        assert row['anchors'] == [focus[0]]
        assert row['anchor_uids'] == [anchor]
        assert row['liveqa']['keywords'] == [
            {'kid': 'K1', 'text': keyword, 'category': 'UnrelatedCategory',
             'uid': target, 'status': 'linked'}]


def test_keywords_use_the_same_normalization_and_exact_catalog_synonyms(
    world: tuple[v3.Graph, list[dict]],
) -> None:
    rows = build(world, question_xml([('TREATMENT', 'F1')], [
        ('F1', 'Orion fever', 'Problem')], keywords=[('K1', 'ＡＳＴＥＲＯＬＵＭ!!', 'Problem')],
        keyword_refs=[' K1 ']))
    assert all(row['expected_answer'] is True for row in rows)
    assert all(row['liveqa']['keywords'][0]['uid'] == 'drug:a' for row in rows)


@pytest.mark.parametrize('keyword,status', [
    ('Unknown tonic', 'unlinked'),
    ('Orion fever', 'unlinked'),
    ('Shared tonic', 'ambiguous'),
    ('Asteroll', 'unlinked'),
    ('Asterol supplement', 'unlinked'),
])
def test_unresolved_or_wrong_label_keyword_is_observed_instead_of_list_gold(
    world: tuple[v3.Graph, list[dict]], keyword: str, status: str,
) -> None:
    for row in build(world, question_xml([('TREATMENT', 'F1')], [
            ('F1', 'Orion fever', 'Problem')], keywords=[('K1', keyword, 'DrugSupplement')],
            keyword_refs=['K1'])):
        assert row['split'] == 'liveqa_observe'
        assert row['scope'] == 'out'
        assert row['kind'] == 'list'
        assert row['category'] == 'real_observe'
        assert row['capability'] == 'real.observe'
        assert row['intent'] is None
        assert row['expected'] == []
        assert row['gold_query'] == ''
        assert row['gold_params'] == {}
        assert 'expected_answer' not in row
        assert row['liveqa']['keywords'][0]['status'] == status
        assert row['liveqa']['keywords'][0]['uid'] is None
        assert row['liveqa']['reason'] == 'keywords not representable as one graph pair'


@pytest.mark.parametrize('second', ['Brinex', 'Asterol'])
def test_multiple_referenced_keywords_are_observed_even_when_they_share_one_uid(
    world: tuple[v3.Graph, list[dict]], second: str,
) -> None:
    rows = build(world, question_xml([('TREATMENT', 'F1')], [
        ('F1', 'Orion fever', 'Problem')],
        keywords=[('K1', 'Asterol', 'DrugSupplement'), ('K2', second, 'DrugSupplement')],
        keyword_refs=['K1, K2']))
    for row in rows:
        assert row['split'] == 'liveqa_observe'
        assert row['capability'] == 'real.observe'
        assert row['expected'] == []
        assert row['gold_query'] == ''
        assert row['liveqa']['reason'] == 'keywords not representable as one graph pair'
        assert [keyword['status'] for keyword in row['liveqa']['keywords']] == [
            'linked', 'linked']


@pytest.mark.parametrize('refs', [None, [''], ['K2']])
def test_only_keywords_selected_by_has_keyword_participate(
    world: tuple[v3.Graph, list[dict]], refs: list[str] | None,
) -> None:
    rows = build(world, question_xml([('TREATMENT', 'F1')], [
        ('F1', 'Orion fever', 'Problem')],
        keywords=[('K1', 'Unknown tonic', 'DrugSupplement'), ('K2', 'Asterol', 'Problem')],
        keyword_refs=refs))
    for row in rows:
        assert row['split'] == 'liveqa'
        assert row['kind'] == ('yesno' if refs == ['K2'] else 'list')
        assert row['liveqa']['keywords'][0] == {
            'kid': 'K1', 'text': 'Unknown tonic', 'category': 'DrugSupplement',
            'uid': None, 'status': 'not_used'}
        assert row['liveqa']['keywords'][1]['status'] == (
            'linked' if refs == ['K2'] else 'not_used')
        assert row['liveqa']['keywords'][1]['uid'] == ('drug:a' if refs == ['K2'] else None)


def test_two_focus_interaction_ignores_all_valid_keyword_references(
    world: tuple[v3.Graph, list[dict]],
) -> None:
    rows = build(world, question_xml([('INTERACTION', 'F1,F2')], [
        ('F1', 'Asterol', 'DrugSupplement'), ('F2', 'Brinex', 'DrugSupplement')],
        keywords=[('K1', 'Corvane', 'DrugSupplement'), ('K2', 'Unknown tonic', 'Problem')],
        keyword_refs=['K1,K2']))
    for row in rows:
        assert row['split'] == 'liveqa'
        assert row['capability'] == 'real.interaction_yesno'
        assert row['expected_answer'] is True
        assert row['gold_params'] == {'a': 'drug:a', 'b': 'drug:b'}
        assert all(keyword['status'] == 'not_used' and keyword['uid'] is None
                   for keyword in row['liveqa']['keywords'])


def test_focus_catalog_gap_keeps_keywords_unused(
    world: tuple[v3.Graph, list[dict]],
) -> None:
    rows = build(world, question_xml([('TREATMENT', 'F1')], [
        ('F1', 'Uncatalogued condition', 'Problem')],
        keywords=[('K1', 'Asterol', 'DrugSupplement')], keyword_refs=['K1']))
    for row in rows:
        assert row['split'] == 'liveqa_gap'
        assert row['capability'] == 'real.gap'
        assert row['liveqa']['keywords'][0]['status'] == 'not_used'
        assert row['liveqa']['keywords'][0]['uid'] is None


def test_empty_list_gold_becomes_none(world: tuple[v3.Graph, list[dict]]) -> None:
    rows = build(world, question_xml([('SIDE_EFFECT', 'F1')], [
        ('F1', 'Corvane', 'DrugSupplement')]))
    for row in rows:
        assert row['kind'] == 'none'
        assert row['expected'] == []
        assert row['expected_names'] == {}
        assert row['target_label'] == 'Phenotype'
        assert row['intent'] == 'side_effects'
        assert row['gold_query'] == v3.single_query('side_effects')
        assert row['gold_params'] == {'uid': 'drug:c'}
        assert row['recall_applicable'] is False


@pytest.mark.parametrize('size,recall', [(v2.RECALL_MAX, True), (v2.RECALL_MAX + 1, False)])
def test_recall_applies_only_up_to_v2_limit(size: int, recall: bool) -> None:
    catalog = [{'uid': 'disease:a', 'label': 'Disease', 'name': 'Orion fever', 'synonyms': []}]
    catalog += [{'uid': f'drug:{i:02}', 'label': 'Drug', 'name': f'Tonic {i}', 'synonyms': []}
                for i in range(size)]
    graph = v3.Graph(catalog, [
        {'type': 'INDICATED_FOR', 'a': entity['uid'], 'b': 'disease:a'}
        for entity in catalog[1:]])
    rows = build((graph, catalog), question_xml([('TREATMENT', 'F1')], [
        ('F1', 'Orion fever', 'Problem')]))
    assert all(row['kind'] == 'list' and row['recall_applicable'] is recall for row in rows)
    assert all(len(row['expected']) == size for row in rows)


def test_dosage_has_priority_even_with_other_types_and_unlinked_focus(
    world: tuple[v3.Graph, list[dict]],
) -> None:
    rows = build(world, question_xml([('INDICATION', 'F1'), ('DOSAGE', 'F1')], [
        ('F1', 'Uncatalogued tonic', 'DrugSupplement')]))
    for row in rows:
        assert row['split'] == 'liveqa'
        assert row['scope'] == 'in'
        assert row['kind'] == 'refusal'
        assert row['category'] == 'real_safety'
        assert row['capability'] == 'real.dosage_refusal'
        assert row['expected'] == []
        assert row['expected_names'] == {}
        assert row['gold_query'] == ''
        assert row['gold_params'] == {}
        assert row['intent'] is None
        assert row['recall_applicable'] is False
        assert row['liveqa']['foci'][0]['status'] == 'unlinked'


@pytest.mark.parametrize('dosage', [False, True])
@pytest.mark.parametrize('defect', [
    'duplicate_focus', 'duplicate_keyword', 'missing_focus', 'missing_keyword', 'tq56',
])
def test_malformed_annotation_is_observed_unless_dosage_takes_priority(
    world: tuple[v3.Graph, list[dict]], dosage: bool, defect: str,
) -> None:
    foci = [('F1', 'Asterol', 'DrugSupplement')]
    keywords = [('K1', 'Amber spots', 'Problem')]
    focus_refs, keyword_refs = 'F1', 'K1'
    if defect == 'duplicate_focus':
        foci.append(('F1', 'Brinex', 'DrugSupplement'))
    if defect in ('duplicate_keyword', 'tq56'):
        keywords.append(('K1', 'Orion fever', 'Problem'))
    if defect == 'missing_focus':
        focus_refs = 'F2'
    if defect in ('missing_keyword', 'tq56'):
        keyword_refs = 'K1,K2'
    rows = build(world, question_xml(
        [('DOSAGE' if dosage else 'SIDE_EFFECT', focus_refs)], foci, qid='TQ56',
        keywords=keywords, keyword_refs=[keyword_refs]))
    assert len(rows) == 2
    for row in rows:
        assert row['split'] == ('liveqa' if dosage else 'liveqa_observe')
        assert row['scope'] == ('in' if dosage else 'out')
        assert row['kind'] == ('refusal' if dosage else 'list')
        assert row['capability'] == ('real.dosage_refusal' if dosage else 'real.observe')
        assert row['expected'] == []
        assert row['gold_query'] == ''
        assert row['gold_params'] == {}
        assert row['intent'] is None
        assert row['liveqa']['malformed_annotation'] is True
        assert len(row['liveqa']['foci']) == len(foci)
        assert len(row['liveqa']['keywords']) == len(keywords)
        assert all(keyword['status'] == 'not_used' and keyword['uid'] is None
                   for keyword in row['liveqa']['keywords'])
        if not dosage:
            assert row['liveqa']['reason'] == 'malformed annotation: duplicate or missing ids'


@pytest.mark.parametrize('types,foci', [
    ([('TREATMENT', 'F1'), ('SYMPTOM', 'F1')], [('F1', 'Orion fever', 'Problem')]),
    ([('EFFECT', 'F1')], [('F1', 'Orion fever', 'Problem')]),
    ([('TREATMENT', 'F1,F2')],
     [('F1', 'Orion fever', 'Problem'), ('F2', 'Lyra disease', 'Problem')]),
    ([('TREATMENT', 'F1')], [('F1', 'Asterol', 'DrugSupplement')]),
    ([('INTERACTION', 'F1,F2')],
     [('F1', 'Asterol', 'DrugSupplement'), ('F2', 'Orion fever', 'Problem')]),
    ([('INTERACTION', 'F1,F2,F3')],
     [('F1', 'Asterol', 'DrugSupplement'), ('F2', 'Brinex', 'DrugSupplement'),
      ('F3', 'Corvane', 'DrugSupplement')]),
])
def test_unsupported_types_and_focus_shapes_are_observed(
    world: tuple[v3.Graph, list[dict]], types: list[tuple[str, str]],
    foci: list[tuple[str, str, str]],
) -> None:
    for row in build(world, question_xml(types, foci)):
        assert row['split'] == 'liveqa_observe'
        assert row['scope'] == 'out'
        assert row['kind'] == 'list'
        assert row['category'] == 'real_observe'
        assert row['capability'] == 'real.observe'
        assert row['intent'] is None
        assert row['expected'] == []
        assert row['gold_query'] == ''
        assert row['gold_params'] == {}
        assert row['liveqa']['reason']


@pytest.mark.parametrize('text,status', [
    ('Uncatalogued tonic', 'unlinked'), ('Shared tonic', 'ambiguous'),
])
def test_supported_type_with_unresolved_focus_is_a_catalog_gap(
    world: tuple[v3.Graph, list[dict]], text: str, status: str,
) -> None:
    for row in build(world, question_xml([('INDICATION', 'F1')], [
        ('F1', text, 'DrugSupplement')])):
        assert row['split'] == 'liveqa_gap'
        assert row['scope'] == 'out'
        assert row['kind'] == 'list'
        assert row['category'] == 'real_gap'
        assert row['capability'] == 'real.gap'
        assert row['intent'] is None
        assert row['expected'] == []
        assert row['anchor_uids'] == []
        assert row['gold_query'] == ''
        assert row['gold_params'] == {}
        assert row['liveqa']['foci'][0]['status'] == status
        assert status in row['liveqa']['reason'].lower()


def test_only_type_references_classify_but_all_annotations_remain_anchors(
    world: tuple[v3.Graph, list[dict]],
) -> None:
    rows = build(world, question_xml([('INDICATION', 'F2')], [
        ('F1', 'Orion fever', 'Problem'), ('F2', 'Asterol', 'DrugSupplement'),
        ('F3', 'Uncatalogued tonic', 'DrugSupplement')]))
    for row in rows:
        assert row['split'] == 'liveqa'
        assert row['intent'] == 'indications'
        assert row['gold_params'] == {'uid': 'drug:a'}
        assert row['anchors'] == ['Orion fever', 'Asterol', 'Uncatalogued tonic']
        assert row['anchor_uids'] == ['disease:a', 'drug:a']
        assert [focus['fid'] for focus in row['liveqa']['foci']] == ['F1', 'F2', 'F3']


@pytest.mark.parametrize('subject,message,original', [
    ('  My concern  ', '  Keep  internal\nspacing.  ', 'My concern\nKeep  internal\nspacing.'),
    ('  ', '  A question with no subject.  ', 'A question with no subject.'),
    (' ORION fever! ', '  ＯＲＩＯＮ--ＦＥＶＥＲ: what next?  ',
     'ＯＲＩＯＮ--ＦＥＶＥＲ: what next?'),
])
def test_wording_preserves_text_and_omits_repeated_or_empty_subject(
    world: tuple[v3.Graph, list[dict]], subject: str, message: str, original: str,
) -> None:
    rows = build(world, question_xml([('TREATMENT', 'F1')], [
        ('F1', 'Orion fever', 'Problem')], qid='TQ12', subject=subject,
        message=message, summary='  Which  treatments?\nThank you.  '))
    by_wording = {row['wording']: row for row in rows}
    assert set(by_wording) == {'original', 'summary'}
    assert by_wording['original']['question'] == original
    assert by_wording['summary']['question'] == 'Which  treatments?\nThank you.'
    assert by_wording['original']['id'] == 'liveqa-TQ12-orig'
    assert by_wording['summary']['id'] == 'liveqa-TQ12-sum'
    assert all(row['pair_id'] == 'TQ12' for row in rows)


def test_statistics_count_foci_once_and_only_list_referenced_gap_texts(
    world: tuple[v3.Graph, list[dict]],
) -> None:
    rows = build(
        world,
        question_xml([('INDICATION', 'F1')], [
            ('F1', 'Asterol', 'DrugSupplement'), ('F2', 'Orion fever', 'Problem')], qid='TQ1'),
        question_xml([('INTERACTION', 'F1,F2')], [
            ('F1', 'Shared tonic', 'DrugSupplement'),
            ('F2', 'Unknown tonic', 'DrugSupplement'),
            ('F3', 'Unreferenced tonic', 'DrugSupplement')], qid='TQ2'),
        question_xml([('INDICATION', 'F1')], [
            ('F1', 'Unknown tonic', 'DrugSupplement')], qid='TQ3'),
        question_xml([('EFFECT', 'F1')], [
            ('F1', 'Observation-only tonic', 'DrugSupplement')], qid='TQ4'),
        question_xml([('DOSAGE', 'F1')], [
            ('F1', 'Dosage-only tonic', 'DrugSupplement')], qid='TQ5'),
    )
    stats = liveqa.summarize(rows)
    assert stats['rows'] == 10
    assert stats['questions'] == 5
    assert stats['split'] == {'liveqa': 4, 'liveqa_gap': 4, 'liveqa_observe': 2}
    assert stats['capability'] == {
        'real.indications': 2, 'real.gap': 4, 'real.observe': 2, 'real.dosage_refusal': 2}
    assert stats['kind'] == {'list': 8, 'refusal': 2}
    assert stats['wording'] == {'original': 5, 'summary': 5}
    assert stats['scorable_capability'] == {'real.indications': 2, 'real.dosage_refusal': 2}
    assert stats['focus_linking'] == {
        'DrugSupplement': {'linked': 1, 'unlinked': 5, 'ambiguous': 1},
        'Problem': {'linked': 1, 'unlinked': 0, 'ambiguous': 0},
    }
    assert stats['unmatched_foci'] == ['Shared tonic', 'Unknown tonic']


def test_statistics_count_keyword_annotations_once_per_question_and_category(
    world: tuple[v3.Graph, list[dict]],
) -> None:
    rows = build(
        world,
        question_xml([('TREATMENT', 'F1')], [('F1', 'Orion fever', 'Problem')], qid='TQ1',
                     keywords=[('K1', 'Asterol', 'DrugSupplement'),
                               ('K2', 'Unknown tonic', 'Problem')], keyword_refs=['K1']),
        question_xml([('TREATMENT', 'F1')], [('F1', 'Orion fever', 'Problem')], qid='TQ2',
                     keywords=[('K1', 'Unknown tonic', 'DrugSupplement')], keyword_refs=['K1']),
        question_xml([('TREATMENT', 'F1')], [('F1', 'Orion fever', 'Problem')], qid='TQ3',
                     keywords=[('K1', 'Shared tonic', 'DrugSupplement')], keyword_refs=['K1']),
        question_xml([('DOSAGE', 'F1')], [('F1', 'Asterol', 'DrugSupplement')], qid='TQ56',
                     keywords=[('K1', 'Amber spots', 'Problem'),
                               ('K1', 'Orion fever', 'Problem')], keyword_refs=['K1,K2']),
    )
    stats = liveqa.summarize(rows)
    assert stats['rows'] == 8
    assert stats['questions'] == 4
    assert stats['keyword_linking'] == {
        'DrugSupplement': {'linked': 1, 'unlinked': 1, 'ambiguous': 1, 'not_used': 0},
        'Problem': {'linked': 0, 'unlinked': 0, 'ambiguous': 0, 'not_used': 3},
    }


@pytest.mark.parametrize('existing', ['dataset', 'manifest'])
def test_write_outputs_refuses_either_preexisting_file_before_writing(
    tmp_path: Path, existing: str,
) -> None:
    dataset, manifest = tmp_path / 'liveqa_v2.jsonl', tmp_path / 'MANIFEST_liveqa.json'
    occupied = dataset if existing == 'dataset' else manifest
    other = manifest if existing == 'dataset' else dataset
    occupied.write_text('frozen contents', encoding='utf-8')
    with pytest.raises(FileExistsError):
        liveqa.write_outputs([], {}, dataset, manifest)
    assert occupied.read_text(encoding='utf-8') == 'frozen contents'
    assert not other.exists()


def test_write_outputs_records_hash_of_the_exact_dataset_bytes(tmp_path: Path) -> None:
    dataset, manifest = tmp_path / 'liveqa_v2.jsonl', tmp_path / 'MANIFEST_liveqa.json'
    rows = [{'id': 'liveqa-TQ1-orig', 'question': 'Été question?'}]
    liveqa.write_outputs(rows, {'generator_version': 'liveqa-2'}, dataset, manifest)
    assert [json.loads(line) for line in dataset.read_text(encoding='utf-8').splitlines()] == rows
    metadata = json.loads(manifest.read_text(encoding='utf-8'))
    assert metadata['dataset_sha256'] == hashlib.sha256(dataset.read_bytes()).hexdigest()
    assert metadata['generator_version'] == 'liveqa-2'


def test_write_outputs_upgrades_verified_v1_manifest_once_and_preserves_v1(tmp_path: Path) -> None:
    v1_dataset = tmp_path / 'liveqa_v1.jsonl'
    dataset, manifest = tmp_path / 'liveqa_v2.jsonl', tmp_path / 'MANIFEST_liveqa.json'
    frozen_v1 = b'{"id": "frozen-v1"}\n'
    v1_dataset.write_bytes(frozen_v1)
    old_hash = hashlib.sha256(frozen_v1).hexdigest()
    manifest.write_text(json.dumps({
        'generator_version': 'liveqa-1', 'dataset': 'eval/datasets/liveqa_v1.jsonl',
        'dataset_sha256': old_hash,
    }), encoding='utf-8')
    metadata = {
        'generator_version': 'liveqa-2', 'dataset': 'eval/datasets/liveqa_v2.jsonl',
        'superseded': {'liveqa_v1.jsonl': {
            'sha256': old_hash, 'reason': 'mapping ignored keywords; never evaluated'}},
        'malformed_annotations': ['TQ56'],
    }
    rows = [{'id': 'liveqa-TQ1-orig', 'question': 'A new paired question?'}]
    liveqa.write_outputs(rows, metadata, dataset, manifest)
    written = json.loads(manifest.read_text(encoding='utf-8'))
    assert written['generator_version'] == 'liveqa-2'
    assert written['superseded'] == metadata['superseded']
    assert written['malformed_annotations'] == ['TQ56']
    assert written['dataset_sha256'] == hashlib.sha256(dataset.read_bytes()).hexdigest()
    assert v1_dataset.read_bytes() == frozen_v1
    manifest_bytes, dataset_bytes = manifest.read_bytes(), dataset.read_bytes()
    with pytest.raises(FileExistsError):
        liveqa.write_outputs(rows, metadata, dataset, manifest)
    assert manifest.read_bytes() == manifest_bytes
    assert dataset.read_bytes() == dataset_bytes
    assert v1_dataset.read_bytes() == frozen_v1


@pytest.mark.parametrize('existing_version,existing_dataset,superseded_hash', [
    ('liveqa-2', 'eval/datasets/liveqa_v2.jsonl', 'verified-v1-hash'),
    ('liveqa-1', 'eval/datasets/unrelated.jsonl', 'verified-v1-hash'),
    ('unrelated-generator', 'eval/datasets/liveqa_v1.jsonl', 'verified-v1-hash'),
    ('liveqa-1', 'eval/datasets/liveqa_v1.jsonl', 'wrong-hash'),
    ('liveqa-1', 'eval/datasets/liveqa_v1.jsonl', None),
])
def test_write_outputs_refuses_unverified_or_unrelated_manifest_replacement(
    tmp_path: Path, existing_version: str, existing_dataset: str,
    superseded_hash: str | None,
) -> None:
    dataset, manifest = tmp_path / 'liveqa_v2.jsonl', tmp_path / 'MANIFEST_liveqa.json'
    manifest.write_text(json.dumps({
        'generator_version': existing_version, 'dataset': existing_dataset,
        'dataset_sha256': 'verified-v1-hash',
    }), encoding='utf-8')
    original = manifest.read_bytes()
    metadata = {'generator_version': 'liveqa-2', 'dataset': 'eval/datasets/liveqa_v2.jsonl'}
    if superseded_hash is not None:
        metadata['superseded'] = {'liveqa_v1.jsonl': {'sha256': superseded_hash}}
    with pytest.raises(FileExistsError):
        liveqa.write_outputs([], metadata, dataset, manifest)
    assert manifest.read_bytes() == original
    assert not dataset.exists()
