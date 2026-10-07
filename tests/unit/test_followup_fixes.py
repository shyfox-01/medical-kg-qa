"""Independent fictional input families from the follow-up review."""

import copy

import pytest

from eval.score import Vocabulary, count_value, forbidden_content, query_safe, score
from medkg.graph.store import QueryResult
from medkg.ingest.extract import Relation, cached_edge_supported, extract, link_relations
from medkg.ingest.openfda import parse
from medkg.ingest.reconcile import reconcile_edges
from medkg.qa.linker import Linker
from medkg.qa.router import route
from medkg.qa.safety import assess
from tests.unit.test_review_regressions import ENTITIES, Model, app


@pytest.mark.parametrize('instruction',[
    'Take Asterol 2 times a day.', 'Take Asterol four times per week.',
    'Use Asterol every morning.', 'Administer Asterol each evening.',
    'Swallow Asterol twice a day.', 'Take Asterol three times a day.',
])
def test_frequency_equivalents_at_all_boundaries(monkeypatch,instruction):
    assert assess(instruction).category=='dosage'
    assert forbidden_content(instruction)
    result = app(monkeypatch,Model(text=instruction)).ask('What is Asterol indicated for?')
    assert result['refused'] and result['safety']=='dosage'
    assert instruction not in result['answer']


@pytest.mark.parametrize('body',[
    'There are 2 drugs and four phenotypes.',
    'The query was run 2 times a day.', 'Amber spots recur every morning.',
])
def test_calendar_and_graph_counts_without_medication_instruction(body):
    assert not assess(body).blocked and not forbidden_content(body)


@pytest.mark.parametrize('question',[
    'What symptoms are associated with diseases treated by Asterol?',
    'Which phenotypes occur in conditions Asterol is indicated for?',
    'Which side effects are associated with drugs for Orion syndrome?',
    'Which genes and symptoms are associated with Orion syndrome?',
    'Which contraindications and targets are recorded for Asterol?',
])
def test_relation_families_reach_planning(question):
    assert route(question,Linker(copy.deepcopy(ENTITIES)).in_question(question)) is None


@pytest.mark.parametrize('question,intent',[
    ('What is Asterol indicated for?','indications'),
    ('What are the side effects of Asterol?','side_effects'),
    ('Which symptoms are recorded for Orion syndrome?','phenotypes'),
    ('Which drugs are used for Orion syndrome?','drugs_for'),
])
def test_simple_relation_templates_still_available(question,intent):
    assert route(question,Linker(ENTITIES).in_question(question))==intent


@pytest.mark.parametrize('question',[
    'Does Asterol interact with Brinexamne?',
    'Does Brinexamne interact with Asterol?',
])
def test_exact_and_typo_mentions_link_independently(question):
    entities = copy.deepcopy(ENTITIES)
    entities[1]['name'] = 'Brinexamine'
    candidates,unresolved = Linker(entities).question_mentions(question)
    assert {c.uid for c in candidates}=={'fiction:drug-a','fiction:drug-b'}
    assert not unresolved and any(c.method=='fuzzy' for c in candidates)


def test_unresolved_interaction_never_becomes_neighborhood_query(monkeypatch):
    model = Model()
    result = app(monkeypatch,model).ask('Does Asterol interact with Zorblax?')
    assert result['refused'] and result['route']=='linking' and not result['cypher']
    assert result['unresolved_mentions']==['zorblax'] and model.usage['calls']==0


@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('second_names',[['Asterol','Brinex'],['Unidentified ingredient']])
def test_brand_ambiguity_is_global_and_removes_prior_alias(reverse,second_names):
    entities = copy.deepcopy(ENTITIES)
    entities[0]['synonyms'] = ['FamilyBrand']
    records = [{'results':[{'id':str(i),'openfda':{'generic_name':names,
                'brand_name':['FamilyBrand']}}]} for i,names in enumerate([['Asterol'],second_names])]
    parse(records[::-1] if reverse else records,entities,'fictional')
    assert 'familybrand' not in Linker(entities).aliases


def test_prefix_and_fuzzy_endpoint_identity_rejected_on_fresh_path(tmp_path):
    text = 'Asterol is contraindicated for Orion syndrome.'
    entities = copy.deepcopy(ENTITIES)+[
        {'uid':'fiction:prefix','name':'Aster','label':'Drug','synonyms':[]}]
    payload = {'subject':'Aster','object':'Orion syndrome','relation':'CONTRAINDICATED_FOR',
               'evidence':text,'confidence':0.9}
    assert extract(Model(plan={'relations':[payload]}),text)==[]
    chunk = {'uid':'fiction:chunk','text':text}
    assert link_relations([Relation(**payload)],chunk,Linker(entities),tmp_path/'unlinked.jsonl')==[]
    entities[0]['synonyms'] = ['Fictional Aster']
    text = 'Fictional Aster is contraindicated for Orion syndrome.'
    payload.update(subject='Fictional Aster',evidence=text)
    chunk['text'] = text
    edges = link_relations([Relation(**payload)],chunk,Linker(entities),tmp_path/'unlinked.jsonl')
    assert len(edges)==1 and cached_edge_supported(edges[0],chunk,{e['uid']:e for e in entities})


def test_scoped_reconciliation_retains_other_chunks_and_is_idempotent():
    base = {'a':'fiction:drug-a','b':'fiction:disease','type':'CONTRAINDICATED_FOR',
            'source':'openfda_extracted','confidence':0.8,'evidence':['selected','outside']}
    other = {**base,'b':'fiction:other','evidence':['unrelated']}
    updated = reconcile_edges([base,other],{'selected'},[])
    assert updated[0]['evidence']==['outside'] and updated[1]==other
    assert reconcile_edges(updated,{'selected'},[])==updated
    updated = reconcile_edges(updated,{'selected'},[{**base,'evidence':['selected']}])
    assert next(e for e in updated if e['b']==base['b'])['evidence']==['outside','selected']
    assert reconcile_edges([base],{'outside','selected'},[])==[]


@pytest.mark.parametrize('rows,partial',[(25,False),(26,True)])
def test_reference_truncation_is_explicit(monkeypatch,rows,partial):
    pipeline = app(monkeypatch,Model())
    flags = []
    output = [[{'uid':f'fiction:{i}'} for i in range(rows)]]
    resolved = pipeline._resolve_args({'uids':'$step1'},output,flags)
    assert len(resolved['uids'])==25 and bool(flags)==partial
    flags = []
    pipeline._resolve_args({'uids':'$step1'},[[{'uid':'same'}]*30],flags)
    assert not flags


@pytest.mark.parametrize('body',['Count: \u22122.','Count: - 2.','Count: \uff0d2.','Count: \u20132.'])
def test_negative_count_representations_cannot_pass(body):
    assert count_value(body) is None
    assert not score({'kind':'count','expected_count':2},{'answer':body},Vocabulary([]))['passed']


def test_composite_quality_rejects_correct_list_with_unsafe_completion():
    result = {'answer':'Amber spots. Take Asterol every morning.','contexts':ENTITIES,
              'refused':False,'failure_stage':None,'executed_statements':[]}
    case = {'kind':'list','expected':['fiction:phenotype-a'],'anchors':['Asterol']}
    measured = score(case,result,Vocabulary(ENTITIES))
    assert measured['passed'] and measured['forbidden_content'] and not measured['quality_passed']


def test_generated_explicit_refusal_has_consistent_public_status(monkeypatch):
    result = app(monkeypatch,Model(text='I cannot answer this from the provided evidence.')).ask(
        'What is Asterol indicated for?')
    assert result['refused'] and result['response_status']=='unsupported'


def test_incomplete_reference_blocks_exact_aggregate(monkeypatch):
    class ManyStore:
        def __init__(self):
            self.executed_statements = []
        def read(self,*args):
            return []
        def run_generated(self,statement,params):
            self.executed_statements.append(statement)
            return QueryResult([{'uid':f'fiction:{i}','name':f'Fixture item {i}'}
                                for i in range(26)],statement)
    plan = {'steps':[{'tool':'template','args':{'intent':'drugs_for','uids':['fiction:disease']}},
                     {'tool':'template','args':{'intent':'targets','uids':'$step1','count':True}}]}
    pipeline = app(monkeypatch,Model(plan=plan))
    pipeline.store = ManyStore()
    result = pipeline.ask('Explain the count of targets of drugs for Orion syndrome.')
    assert result['truncated'] and result['refused'] and result['failure_stage'] is None
    assert len(result['cypher'])==1 and 'exact count is unavailable' in result['answer']


def test_quality_distinguishes_code_owned_reads_from_generated_procedures():
    statements = ['CALL db.index.fulltext.queryNodes($index,$query) YIELD node RETURN node.uid']
    assert not query_safe(statements) and query_safe(statements,trusted_retrieval=True)
    assert not query_safe(statements+['DELETE node'],trusted_retrieval=True)
    assert not query_safe(['CALL dbms.listConfig() RETURN 1'],trusted_retrieval=True)
    result = {'answer':'Amber spots','contexts':[ENTITIES[3]],'executed_statements':statements,'cypher':[]}
    case = {'kind':'list','expected':['fiction:phenotype-a']}
    assert score(case,result,Vocabulary(ENTITIES))['quality_passed']
    result['cypher'] = statements
    assert not score(case,result,Vocabulary(ENTITIES))['quality_passed']


def test_discourse_words_and_root_aliases_do_not_create_entity_anchors():
    entities = copy.deepcopy(ENTITIES)+[
        {'uid':'fiction:acronym','name':'Fictional syndrome','label':'Disease','synonyms':['HAS']},
        {'uid':'fiction:root','name':'disease or disorder','label':'Disease','synonyms':['disease']}]
    question = 'Which genes are associated with diseases Asterol has treated?'
    assert {c.uid for c in Linker(entities).in_question(question)}=={'fiction:drug-a'}
    assert Vocabulary(entities).extract(question)=={'fiction:drug-a'}
    assert Linker(entities).in_question('Which genes for HAS?')[0].uid=='fiction:acronym'
    assert Vocabulary(entities).extract('HAS')=={'fiction:acronym'}
