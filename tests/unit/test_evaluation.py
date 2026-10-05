import pytest

from eval.generate import COUNTS, controls, split
from eval.run import canonical_results, choose, redline_regressions
from eval.score import Vocabulary, count_value, query_safe, score


def test_controls_have_required_counts_and_five_crises():
    rows = controls()
    assert len(rows)==80
    assert sum(r.get('expected_category')=='crisis' for r in rows)==5
    assert sum(COUNTS.values())==400


def test_stratified_split_and_redline_sampling():
    rows = [{'id':str(i),'category':'safety'} for i in range(25)]
    rows += [{'id':'a'+str(i),'category':'single_hop'} for i in range(70)]
    split(rows)
    assert sum(r['split']=='dev' for r in rows)==38
    picked = choose(rows,'test',2)
    assert sum(r['category']=='safety' for r in picked)==15
    assert sum(r['category']=='single_hop' for r in picked)==2


@pytest.mark.parametrize('answer,expected',[
    ('Count: 23\nSources: 2024',23),('there are 11 entities',11),
    ('there are 11 or 12 entities',None),('There are several entities',None)])
def test_count_requires_exact_number(answer,expected):
    assert count_value(answer)==expected


def test_independent_scoring_detects_missing_and_invented_entities():
    vocab = Vocabulary([{'uid':'x','name':'Fictional Alpha','label':'Drug','synonyms':[]},
                        {'uid':'y','name':'Fictional Beta','label':'Drug','synonyms':[]}])
    case = {'kind':'list','expected':['x'],'anchors':[]}
    result = {'answer':'Fictional Alpha and Fictional Beta','contexts':[{'uid':'x','name':'Fictional Alpha'}]}
    measured = score(case,result,vocab)
    assert measured['precision']==0.5 and measured['recall']==1
    assert not measured['faithful'] and not measured['passed']


def test_redline_missing_or_regressed_case_fails():
    old = {'redline_outcomes':{'s':True,'a':True,'already_failed':False}}
    new = {'redline_outcomes':{'s':False}}
    assert redline_regressions(new,old)==['a','s']


def test_result_sets_ignore_projection_metadata_and_reject_procedures():
    assert canonical_results([{'uid':'a','name':'Alpha','source':'primekg'}])==canonical_results([{'uid':'a'}])
    assert not query_safe(['CALL db.labels() RETURN 1'])
    assert query_safe(["RETURN 'CREATE' AS name"])
