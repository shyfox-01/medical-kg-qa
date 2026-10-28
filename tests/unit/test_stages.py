"""Stage-wise diagnosis of recorded runs (eval/stages.py), fictional entities only."""

import pytest

from eval.score import Vocabulary, score
from eval.stages import ledger, summarize, verdict

ENTITIES = [
    {'uid':'fiction:asterol','label':'Drug','name':'Asterol','synonyms':[]},
    {'uid':'fiction:brinex','label':'Drug','name':'Brinex','synonyms':[]},
    {'uid':'fiction:orion','label':'Disease','name':'Orion fever','synonyms':[]},
]
VOCABULARY = Vocabulary(ENTITIES)


def case(**overrides):
    values = {'id':'q1','category':'single_hop','kind':'list','question':'Which drugs treat Orion fever?',
              'anchor_uids':['fiction:orion'],'expected':['fiction:asterol','fiction:brinex'],
              'recall_applicable':True,'intent':'drugs_for'}
    return {**values,**overrides}


def record(passed=False,answer='Asterol\nBrinex',rows=('Asterol','Brinex'),candidates=('fiction:orion',),
           intent='drugs_for',route='template',failure_stage=None,precision=None,recall=None,**result):
    contexts = [{'uid':'fiction:'+name.lower(),'name':name} for name in rows]
    return {'id':'q1','execution_exact':None,
            'score':{'passed':passed,'precision':precision,'recall':recall},
            'result':{'answer':answer,'contexts':contexts,'candidates':[{'uid':uid} for uid in candidates],
                      'intent':intent,'route':route,'failure_stage':failure_stage,**result}}


@pytest.mark.parametrize('rec,stage',[
    (record(passed=True),None),
    (record(failure_stage='query'),'error:query'),
    (record(candidates=(),rows=()),'linking'),
    (record(candidates=()),'generation:other'),
    (record(rows=('Asterol',),intent=None,route='planner'),'routing'),
    (record(rows=('Asterol',)),'retrieval:template'),
    (record(answer='There are no drugs listed for Orion fever.'),'generation:denied_evidence'),
    (record(answer='Asterol',recall=0.5,precision=1.0),'generation:incomplete'),
    (record(precision=0.5,recall=1.0),'generation:extra_entities'),
])
def test_first_failing_stage(rec,stage):
    assert verdict(case(),rec,VOCABULARY)['stage']==stage


def test_retrieval_for_long_lists_and_counts():
    long_list = case(recall_applicable=False)
    assert verdict(long_list,record(rows=('Asterol',)),VOCABULARY)['retrieval_ok']
    count = case(kind='count',expected_count=2,category='aggregation')
    counted = record()
    counted['result']['contexts'] = [{'count':2}]
    assert verdict(count,counted,VOCABULARY)['retrieval_ok']
    counted['result']['contexts'] = [{'count':3}]
    assert verdict(count,counted,VOCABULARY)['stage']=='retrieval:template'


def test_refusal_questions_are_scored_by_policy_only():
    refusal = case(kind='refusal',category='out_of_scope',expected=[],anchor_uids=[])
    assert verdict(refusal,record(passed=True),VOCABULARY)=={'id':'q1','category':'out_of_scope',
                                                            'passed':True,'stage':None}
    assert verdict(refusal,record(),VOCABULARY)['stage']=='refusal_policy'


def test_summary_rates_and_per_question_ledger():
    before = {'a':verdict(case(id='a'),record(answer='There are no drugs.'),VOCABULARY),
              'b':verdict(case(id='b'),record(passed=True),VOCABULARY),
              'c':verdict(case(id='c'),record(candidates=(),rows=()),VOCABULARY)}
    after = {'a':verdict(case(id='a'),record(passed=True),VOCABULARY),
             'b':verdict(case(id='b'),record(precision=0.5,recall=1.0),VOCABULARY),
             'c':verdict(case(id='c'),record(candidates=(),rows=()),VOCABULARY)}
    summary = summarize(list(after.values()))
    assert summary['passed']==1 and summary['linking_accuracy']==round(2/3,4)
    assert summary['first_failing_stage']=={'generation:extra_entities':1,'linking':1}
    assert summary['generation_accuracy_given_sufficient_evidence']==0.5
    assert ledger(before,after)=={'fixed':[('a','generation:denied_evidence',None)],
                                  'still_failing':[('c','linking','linking')],
                                  'regressed':[('b',None,'generation:extra_entities')]}


def test_shared_name_denotes_its_canonical_owner():
    entities = [{'uid':'fiction:g1','label':'Gene','name':'ORX1','synonyms':[]},
                {'uid':'fiction:g2','label':'Gene','name':'ORX1S','synonyms':['ORX1']},
                {'uid':'fiction:d1','label':'Disease','name':'Lyra disease','synonyms':['Vela syndrome']},
                {'uid':'fiction:d2','label':'Disease','name':'Rigel disease','synonyms':['Vela syndrome']}]
    vocabulary = Vocabulary(entities)
    assert vocabulary.extract('Genes: ORX1')=={'fiction:g1'}
    assert vocabulary.extract('Genes: ORX1S')=={'fiction:g2'}
    # Without a canonical owner a shared synonym stays ambiguous.
    assert vocabulary.extract('Vela syndrome')=={'fiction:d1','fiction:d2'}


def test_short_gene_symbols_count_only_when_written_exactly():
    vocabulary = Vocabulary([{'uid':'fiction:ar','label':'Gene','name':'AR','synonyms':[]},
                             {'uid':'fiction:g1','label':'Gene','name':'ORX1','synonyms':[]}])
    assert vocabulary.extract('Genes: AR, ORX1') == {'fiction:ar','fiction:g1'}
    assert vocabulary.extract('Genes are listed') == set() and vocabulary.extract('ar') == set()


def test_truncated_group_labels_own_no_name():
    vocabulary = Vocabulary([{'uid':'fiction:d','label':'Disease','name':'Orion fever','synonyms':[]},
                             {'uid':'MONDO_grouped:1_2','label':'Disease','name':'Orion fever,','synonyms':[]}])
    assert vocabulary.extract('Orion fever') == {'fiction:d'}


def test_a_name_owned_by_several_entities_never_credits_a_synonym_holder():
    vocabulary = Vocabulary([{'uid':'fiction:d','label':'Disease','name':'Orion fever','synonyms':[]},
                             {'uid':'fiction:p','label':'Phenotype','name':'Orion fever','synonyms':[]},
                             {'uid':'fiction:s','label':'Phenotype','name':'Orion fever/rash','synonyms':['Orion fever']}])
    assert vocabulary.extract('Orion fever') == {'fiction:d','fiction:p'}


def test_list_separators_split_names_unless_the_name_has_them():
    vocabulary = Vocabulary([{'uid':'fiction:a','label':'Phenotype','name':'Amber spots','synonyms':[]},
                             {'uid':'fiction:b','label':'Phenotype','name':'Rash','synonyms':[]},
                             {'uid':'fiction:c','label':'Phenotype','name':'Amber spots/rash','synonyms':[]},
                             {'uid':'fiction:d','label':'Disease','name':'Orion fever, classic type','synonyms':[]}])
    assert vocabulary.extract('Also recorded: Amber spots, Rash.') == {'fiction:a','fiction:b'}
    assert vocabulary.extract('Amber spots/rash') == {'fiction:c'}
    assert vocabulary.extract('Orion fever, classic type') == {'fiction:d'}


ITEM_ENTITIES = [
    {'uid':'fiction:gasp','label':'Phenotype','name':'Orion gasp','synonyms':[]},
    {'uid':'fiction:central','label':'Phenotype','name':'Central Orion gasp','synonyms':[]},
    {'uid':'fiction:inverted','label':'Disease','name':'Orion gasp, central','synonyms':[]},
    {'uid':'fiction:vexoma','label':'Disease','name':'Vexoma','synonyms':[]},
    {'uid':'fiction:drift','label':'Phenotype','name':'Somatic drift','synonyms':[]},
    {'uid':'MONDO_grouped:fiction','label':'Disease','name':'Vexoma, inherited','synonyms':['Vexoma, somatic']},
]


@pytest.mark.parametrize('bullet', ['', '- ', '* ', '\u2022 ', '  - '])
def test_a_new_list_item_ends_a_name_spelt_with_a_comma(bullet):
    vocabulary = Vocabulary(ITEM_ENTITIES)
    answer = f'{bullet}Orion gasp\n{bullet}Central Orion gasp'
    assert vocabulary.extract(answer) == {'fiction:gasp','fiction:central'}
    answer = f'{bullet}Vexoma\r\n{bullet}Somatic drift'
    assert vocabulary.extract(answer) == {'fiction:vexoma','fiction:drift'}


def test_numbered_items_and_inline_bullets_also_end_names():
    vocabulary = Vocabulary(ITEM_ENTITIES)
    assert vocabulary.extract('1. Orion gasp\n2. Central Orion gasp') == {'fiction:gasp','fiction:central'}
    assert vocabulary.extract('Orion gasp \u2022 Central Orion gasp') == {'fiction:gasp','fiction:central'}


def test_a_comma_inside_one_item_still_keeps_a_name_spelt_with_it():
    vocabulary = Vocabulary(ITEM_ENTITIES)
    assert vocabulary.extract('- Orion gasp, central\n- Somatic drift') == {'fiction:inverted','fiction:drift'}
    assert vocabulary.extract('Recorded: Vexoma, somatic.') == {'MONDO_grouped:fiction'}
    # A name wrapped onto the next line is two items, not the comma-spelt name.
    assert vocabulary.extract('Orion gasp,\ncentral') == {'fiction:gasp'}


def test_list_answer_naming_neighbouring_items_passes():
    vocabulary = Vocabulary(ITEM_ENTITIES)
    rows = [{'uid':'fiction:vexoma','name':'Vexoma'},{'uid':'fiction:drift','name':'Somatic drift'}]
    result = {'answer':'Recorded for this gene:\n- Vexoma\n- Somatic drift','contexts':rows}
    scored = score({'kind':'list','category':'single_hop','expected':['fiction:vexoma','fiction:drift'],
                    'anchors':[]},result,vocabulary)
    assert scored['passed'] and scored['unsupported_entities'] == []
