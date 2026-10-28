"""Design defects found by the v3 b1 first-look round (D092), fictional entities only."""

import json

import pytest

from medkg.config import Settings
from medkg.graph.store import QueryResult
from medkg.qa.linker import Linker
from medkg.qa.pipeline import Pipeline
from medkg.qa.router import route
from medkg.qa.safety import assess, english
from tests.unit.test_review_regressions import Model, both, span, trace

ENTITIES = [
    {'uid':'fiction:asterol','label':'Drug','name':'Asterol','synonyms':['Asterolum']},
    {'uid':'fiction:brinex','label':'Drug','name':'Brinex','synonyms':[]},
    {'uid':'fiction:orion','label':'Disease','name':'Orion fever','synonyms':[]},
    {'uid':'fiction:rigel','label':'Disease','name':'Rigel disorder','synonyms':[]},
    {'uid':'fiction:lyra-d','label':'Disease','name':'Lyra disorder','synonyms':[]},
    {'uid':'fiction:lyra-p','label':'Phenotype','name':'Lyra disorder','synonyms':[]},
    {'uid':'fiction:amber','label':'Phenotype','name':'Amber spots','synonyms':[]},
]


@pytest.mark.parametrize('question,category',[
    ('How often can I take Asterol for my pain?','dosage'),
    ('How long should I use Asterol?','dosage'),
    ('My mother collapsed after taking Asterol and is not breathing. What do I do?','emergency'),
    ('My friend passed out and is unresponsive right now.','emergency'),
    ('Can I give Asterol to my 2-year-old?','special_population'),
    ('Is Asterol safe for my 18-month-old daughter?','special_population'),
])
def test_personal_dosing_emergencies_and_young_children_are_refused(question,category):
    assert assess(question).category==category


@pytest.mark.parametrize('question',[
    'Which drugs list breathing difficulty as a side effect?',
    'What are the symptoms of Orion fever in children?',
    'How many drugs are indicated for Orion fever?',
    'Which diseases have collapsed lung as a symptom?',
])
def test_knowledge_questions_stay_answerable(question):
    assert not assess(question).blocked


@pytest.mark.parametrize('question,is_english',[
    ('¿Para qué se usa Asterol?',False), ('Quels sont les effets secondaires de Asterol ?',False),
    ('Wofür wird Asterol verwendet?',False), ('Para que serve Asterol?',False),
    ('What drugs treat Sjögren syndrome?',True), ('What causes de Quervain thyroiditis?',True),
    ('Which drugs treat Ménière disease?',True),
])
def test_language_is_judged_by_function_words_not_diacritics(question,is_english):
    assert english(question) is is_english


@pytest.mark.parametrize('question,intent',[
    ('What does Asterol act on at the molecular level?','targets'),
    ('What unwanted effects does Asterol have?','side_effects'),
    ('What should not be combined with Asterol?','interactions'),
    ('In which conditions must Asterol not be given?','contraindications'),
    ('Which medicines are unsafe for people with Orion fever?','contraindicated_drugs'),
    ('What can be prescribed for Orion fever?','drugs_for'),
    ('How does Orion fever present?','phenotypes'),
    ('Which disease categories does Rigel disorder belong to?','parents'),
    ('What broader condition is Rigel disorder a form of?','parents'),
    ('Which diseases are a form of Orion fever?','subtypes'),
    ('Which diseases are subtypes of Lyra disorder?','subtypes'),
    ('What specific forms of Orion fever are recorded?','subtypes'),
    ('Which medicines are known to trigger Amber spots?','drugs_with_side_effect'),
])
def test_relation_wordings_route_to_their_template(question,intent):
    candidates,unresolved = Linker(ENTITIES).question_mentions(question)
    assert not unresolved and route(question,candidates)==intent


@pytest.mark.parametrize('question',['In which conditions should Asterol not be used?',
                                     'When must Asterol not be taken?','Is Asterol unsafe in Orion fever?'])
def test_negated_use_is_never_an_indication_question(question):
    candidates,_ = Linker(ENTITIES).question_mentions(question)
    assert route(question,candidates)!='indications'


class InteractionStore:
    def __init__(self,rows):
        self.rows,self.executed_statements = rows,[]

    def read(self,*args,**kwargs):
        return []

    def run_generated(self,statement,params):
        self.executed_statements.append(statement)
        return QueryResult(self.rows,statement)


def ask(monkeypatch,store,model,question):
    monkeypatch.setattr('medkg.qa.pipeline.request_trace',trace)
    monkeypatch.setattr('medkg.qa.pipeline.span',span)
    return Pipeline(Settings(phase=3,cache=False),store=store,llm=model,entities=ENTITIES).ask(question)


def test_a_recorded_pairwise_interaction_is_stated_in_code(monkeypatch):
    store = InteractionStore([{'uid':'fiction:brinex','name':'Brinex','source':'fictional'}])
    model = Model(text='There is no recorded interaction between Asterol and Brinex.')
    result = ask(monkeypatch,store,model,'Is there a recorded interaction between Asterol and Brinex?')
    assert result['answer'].startswith('Yes. The knowledge graph records an interaction between Asterol and Brinex.')
    assert model.usage['calls']==0


class Recording(Model):
    def __init__(self):
        super().__init__()
        self.prompts = []

    def chat(self,messages,*args):
        self.prompts.append(messages)
        return super().chat(messages,*args)


def test_target_synonyms_are_kept_in_contexts_but_not_shown_to_the_answer_model(monkeypatch):
    store = InteractionStore([{'uid':'fiction:orion','name':'Orion fever','synonyms':['Orion pyrexia'],'source':'fictional'}])
    model = Recording()
    model.plan = both('indications',['fiction:asterol','fiction:brinex'])
    result = ask(monkeypatch,store,model,'What are Asterol and Brinex used for?')
    shown = json.loads(model.prompts[0][1]['content'].split('<evidence>')[1].split('</evidence>')[0])['rows']
    assert 'synonyms' not in shown[0] and result['contexts'][0]['synonyms']==['Orion pyrexia']


def test_same_label_duplicates_get_a_clarification_listing_the_options(monkeypatch):
    entities = ENTITIES + [{'uid':'fiction:vela-1','label':'Disease','name':'Vela syndrome','synonyms':[]},
                           {'uid':'fiction:vela-2','label':'Disease','name':'Vela syndrome','synonyms':[]}]
    monkeypatch.setattr('medkg.qa.pipeline.request_trace',trace)
    monkeypatch.setattr('medkg.qa.pipeline.span',span)
    model = Model()
    result = Pipeline(Settings(phase=3,cache=False),store=InteractionStore([]),llm=model,entities=entities).ask(
        'Which drugs treat Vela syndrome?')
    assert result['refused'] and result['route']=='linking' and model.usage['calls']==0
    assert sorted(result['clarification'])==['fiction:vela-1','fiction:vela-2'] and 'Which one do you mean?' in result['answer']


def test_generic_class_words_are_not_entity_mentions():
    entities = ENTITIES + [{'uid':'fiction:syndromic','label':'Disease','name':'syndromic disease','synonyms':['syndrome']}]
    candidates,unresolved = Linker(entities).question_mentions('What are the symptoms of Zorvex syndrome?')
    assert not candidates and unresolved


def test_no_evidence_was_found_is_an_unsupported_response():
    from medkg.qa.answer import unsupported_response
    assert unsupported_response('No evidence was found in the provided knowledge base to answer this question.')
    assert unsupported_response('Based on the provided evidence, no information was found about Zorvex.')
    assert not unsupported_response('No interaction is recorded, but Asterol treats Orion fever.')
