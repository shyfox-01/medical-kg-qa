"""One-entity lists stated in code (D124) and the page data around an answer (D125), fictional entities only."""

import pytest

from medkg.graph.store import QueryResult
from medkg.qa import answer
from medkg.qa.pipeline import notes
from medkg.retrieval import templates
from tests.unit.test_review_regressions import Model, Store, app


class ListStore(Store):
    """A full side-effect list: 25 rows returned, `recorded` counted; `counts` for the related questions."""

    def __init__(self,recorded=40,counts=None,duplicate=False):
        super().__init__()
        self.recorded,self.counts,self.duplicate = recorded,counts,duplicate

    def read(self,statement,*args,**kwargs):
        if 'RETURN COUNT {' in statement:
            if self.counts is None:
                raise RuntimeError('unavailable')
            return [self.counts]
        return []

    def run_generated(self,statement,params):
        self.executed_statements.append(statement)
        if 'count(DISTINCT b)' in statement:
            return QueryResult([{'count':self.recorded,'sources':['fictional']}],statement)
        rows = [{'uid':f'fiction:spot-{i:02d}','name':f'Spot {i:02d}','source':'fictional'} for i in range(25)]
        if self.duplicate:
            rows[1] = dict(rows[0],source='other',conflict=True)
        return QueryResult(rows,statement,truncated=True)


def test_a_one_entity_list_is_stated_in_code(monkeypatch):
    model = Model()
    result = app(monkeypatch,model).ask('What are the side effects of Asterol?')
    assert model.usage['calls']==0
    assert result['answer'].startswith('The knowledge graph records 1 side effect of Asterol:\n- Amber spots\n\n')
    assert result['answer'].endswith('Research demo; not medical advice.') and 'Only part' not in result['answer']
    assert result['listing']=={'summary':'The knowledge graph records 1 side effect of Asterol.','total':1,
                               'items':[{'name':'Amber spots','uid':'fiction:phenotype-a','conflict':False}]}
    assert not result['truncated'] and result['response_status']=='answered'


def test_a_full_list_is_counted_and_the_first_25_are_listed(monkeypatch):
    pipeline = app(monkeypatch,Model())
    pipeline.store = ListStore(recorded=40)
    result = pipeline.ask('What are the side effects of Asterol?')
    assert result['answer'].startswith('The knowledge graph records 40 side effects of Asterol. '
                                       'The first 25 by name:\n- Spot 00\n- Spot 01')
    assert result['truncated'] and 'Only part' in result['answer']
    assert result['listing']['total']==40 and len(result['listing']['items'])==25
    assert len(result['cypher'])==2 and 'count(DISTINCT b)' in result['cypher'][1]
    assert result['queries'][1]['description']==templates.describe('side_effects',['Asterol'],True)


def test_a_full_list_with_nothing_more_recorded_is_complete(monkeypatch):
    pipeline = app(monkeypatch,Model())
    pipeline.store = ListStore(recorded=25)
    result = pipeline.ask('What are the side effects of Asterol?')
    assert result['answer'].startswith('The knowledge graph records 25 side effects of Asterol:\n')
    assert not result['truncated'] and 'Only part' not in result['answer']


def test_an_entity_recorded_by_two_sources_is_listed_once(monkeypatch):
    pipeline = app(monkeypatch,Model())
    pipeline.store = ListStore(recorded=24,duplicate=True)
    result = pipeline.ask('What are the side effects of Asterol?')
    items = result['listing']['items']
    assert len(items)==24 and items[0]=={'name':'Spot 00','uid':'fiction:spot-00','conflict':True}
    assert result['answer'].count('\n- Spot 00\n')==1 and not result['truncated']


def test_conflicting_records_are_stated_in_words_once():
    claim = {'conflict':True,'relation':'INDICATED_FOR','subject':'Asterol','object':'Orion syndrome','source':'primekg'}
    rows = [dict(claim,relation='CONTRAINDICATED_FOR',source='openfda_extracted'),claim,dict(claim),
            {'conflict':True,'name':'Amber spots','source':'fictional'},dict(claim,conflict=False,object='Lyra')]
    assert answer.claims(rows)==[
        {'claim':'Asterol is contraindicated in Orion syndrome','source':'openfda_extracted'},
        {'claim':'Asterol is indicated for Orion syndrome','source':'primekg'}]


def test_singular_and_plural_list_sentences():
    assert templates.list_summary('drugs_for','Orion syndrome',1)==(
        'The knowledge graph records 1 drug indicated for Orion syndrome.')
    assert templates.list_answer('targets','Asterol',['GENE1','GENE2'],2)==(
        'The knowledge graph records 2 genes or proteins targeted by Asterol:\n- GENE1\n- GENE2')
    assert templates.list_summary('interactions','Asterol',1257)==(
        'The knowledge graph records 1,257 drugs interacting with Asterol.')
    assert set(templates.NOUNS)==set(templates.SPECS)


def test_counts_query_follows_each_template_direction():
    assert templates.counts('Drug',['indications','interactions'])==(
        'MATCH (a:Drug {uid: $uid}) RETURN COUNT { (a)-[:INDICATED_FOR]->(:Disease) } AS indications, '
        'COUNT { (a)-[:INTERACTS_WITH]-(:Drug) } AS interactions')
    assert 'COUNT { (a)<-[:SUBTYPE_OF]-(:Disease) } AS subtypes' in templates.counts('Disease',['subtypes'])
    for label,intents in (('Drug',['drugs_for']),('Ghost',[]),('Drug',['unknown'])):
        with pytest.raises((ValueError,KeyError)):
            templates.counts(label,intents)


def test_related_questions_are_those_the_graph_has_records_for(monkeypatch):
    pipeline = app(monkeypatch,Model())
    pipeline.store = ListStore(counts={'indications':2,'interactions':0,'contraindications':1,'targets':3})
    result = pipeline.ask('What are the side effects of Asterol?')
    assert result['related']==[
        {'intent':'indications','question':'What is Asterol used to treat?'},
        {'intent':'contraindications','question':'In which conditions should Asterol not be used?'},
        {'intent':'targets','question':'Which genes or proteins does Asterol target?'}]


def test_no_related_questions_when_they_cannot_be_counted_or_the_answer_is_refused(monkeypatch):
    pipeline = app(monkeypatch,Model())
    pipeline.store = ListStore(counts=None)
    assert pipeline.ask('What are the side effects of Asterol?')['related']==[]
    pipeline.store = ListStore(counts={'indications':2})
    refused = pipeline.ask('What is the maximum daily dose of Asterol?')
    assert refused['refused'] and 'related' not in refused


def test_a_follow_up_is_shown_as_it_was_read(monkeypatch):
    pipeline = app(monkeypatch,Model())
    history = [{'question':'What is Asterol used to treat?','focus':['Asterol'],'intent':'indications'}]
    pronoun = pipeline.ask('What are its side effects?',history)
    assert pronoun['read_as']=="What are Asterol's side effects?" and pronoun['intent']=='side_effects'
    history = [{'question':'What are the side effects of Asterol?','focus':['Asterol'],'intent':'side_effects'}]
    repeated = pipeline.ask('What about Brinex?',history)
    assert repeated['read_as']=='What are the side effects of Brinex?'
    assert 'Indigo spots' in repeated['answer']
    assert 'read_as' not in pipeline.ask('What are the side effects of Brinex?')


def test_notices_are_split_into_cautions_and_readings(monkeypatch):
    assert notes(['Read as A.\nAnd B.','Careful.'],['Careful.'])==[
        {'kind':'reading','text':'Read as A.'},{'kind':'reading','text':'And B.'},
        {'kind':'caution','text':'Careful.'}]
    result = app(monkeypatch,Model()).ask('I take Asterol 20 mg. What are the side effects of Asterol?')
    assert result['notices'] and {note['kind'] for note in result['notices']}=={'caution'}
    assert result['answer'].startswith(result['notices'][0]['text'])
