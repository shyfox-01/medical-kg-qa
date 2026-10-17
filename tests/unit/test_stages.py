"""Stage-wise diagnosis of recorded runs (eval/stages.py), fictional entities only."""

import pytest

from eval.score import Vocabulary
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
