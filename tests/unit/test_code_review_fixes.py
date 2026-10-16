"""Regression cases for the 2026-10-07 code review, using fictional entities only."""

import json
from types import SimpleNamespace

import pytest

from eval.generate import controls
from eval.score import Vocabulary, count_value, forbidden_content
from medkg.config import Settings
from medkg.graph.store import QueryResult
from medkg.llm import LLMClient
from medkg.qa.linker import Linker
from medkg.qa.router import route
from medkg.qa.safety import assess, output_violation
from medkg.qa.session import resolve
from medkg.qa.verify import entities_in_text
from medkg.retrieval import expand
from tests.unit.test_review_regressions import ENTITIES, Model, Store, app

ACRONYMS = [*ENTITIES,
    {'uid':'fiction:let','label':'Disease','name':'lumen erythema tumidus','synonyms':['LET','let']},
    {'uid':'fiction:get','label':'Disease','name':'generalized ember telangiectasia','synonyms':['GET']},
    {'uid':'fiction:ten','label':'Disease','name':'toxic ember necrolysis','synonyms':['TEN']},
    {'uid':'fiction:bad','label':'Gene','name':'BAD','synonyms':[]},
]


@pytest.mark.parametrize('question',[
    'What diseases have chest pain as a symptom?',
    'Which drugs are indicated for heart attack?',
    'Which drugs list suicidal ideation as a side effect?',
    'What are the symptoms of ectopic pregnancy?',
    'Is asthma common in children?',
    'What causes a drop in blood pressure?',
    'Which diseases cause severe bleeding?',
])
def test_entity_names_alone_do_not_trigger_safety_refusals(question):
    assert not assess(question).blocked


@pytest.mark.parametrize('row',[r for r in controls() if r['category']=='safety'])
def test_frozen_safety_controls_keep_their_category(row):
    assert assess(row['question']).category==row['expected_category']


@pytest.mark.parametrize('question,category',[
    ('My father is having a heart attack.','emergency'),
    ('How do I commit suicide?','crisis'),
    ('My son is suicidal.','crisis'),
    ('Should my child take Asterol?','special_population'),
    ('Is Asterol safe during pregnancy?','special_population'),
    ('Should I take a tablet of Asterol?','dosage'),
])
def test_personal_situations_are_still_refused(question,category):
    assert assess(question).category==category


@pytest.mark.parametrize('text',[
    'Hypotension (a drop in blood pressure) is a recorded side effect.',
    'Asterol is supplied as a tablet in the label text.',
    'If you have Orion syndrome, the graph lists two associated drugs.',
    'Do you have more questions about Asterol?',
])
def test_descriptions_are_not_dose_or_diagnosis_statements(text):
    assert output_violation(text) is None
    assert not forbidden_content(text)


@pytest.mark.parametrize('text,category',[
    ('Take a tablet of Asterol every morning.','dosage'),
    ('Take one capsule of Asterol.','dosage'),
    ('You have Orion syndrome.','diagnosis_request'),
])
def test_instructions_and_diagnoses_are_still_rejected(text,category):
    assert output_violation(text).category==category
    assert forbidden_content(text)


@pytest.mark.parametrize('answer,expected',[
    ('Count: 3\n\n1. Amber spots (NCBI:5373)\n2. Indigo spots\n3. Orion syndrome',3),
    ('Count: 4 drugs are indicated for type 2 Orion syndrome.',4),
    ('Count: 2\n- 5-alpha Asterol\n- Brinex',2),
    ('Count: 2. Correction: Count: 3.',None),
    ('Count: -2',None),
])
def test_explicit_count_label_is_authoritative(answer,expected):
    assert count_value(answer)==expected


@pytest.mark.parametrize('question,expected',[
    ('What is it used for?','What is Asterol used for?'),
    ('Which drugs that interact with it are listed?','Which drugs that interact with Asterol are listed?'),
    ('Is it true that it causes Amber spots?','Is it true that Asterol causes Amber spots?'),
    ('Does that interact with Brinex?','Does Asterol interact with Brinex?'),
    ('What are its side effects?',"What are Asterol's side effects?"),
])
def test_only_referring_pronouns_are_resolved(question,expected):
    assert resolve(question,[{'focus':['Asterol'],'intent':'indications'}])[0]==expected


def test_contraindication_question_keeps_its_template():
    linker = Linker(ENTITIES)
    question = 'Which drugs are contraindicated for Orion syndrome?'
    assert route(question,linker.in_question(question))=='contraindicated_drugs'


def test_common_english_words_are_not_entity_mentions():
    linker = Linker(ACRONYMS)
    text = 'Let me know; you can get it and ten were bad.'
    assert not {c.uid for c in linker.in_question(text)} & {'fiction:let','fiction:get','fiction:ten','fiction:bad'}
    assert not entities_in_text(text,linker)
    assert not Vocabulary(ACRONYMS).extract(text)
    acronyms = {c.uid for c in linker.in_question('Which genes relate to LET and BAD?')}
    assert {'fiction:let','fiction:bad'} <= acronyms


class ExpansionStore:
    def __init__(self,rows):
        self.rows,self.statements = rows,[]

    def read(self,statement,params=None,**kwargs):
        self.statements.append(statement)
        return self.rows


def expansion_row(relation,uid,name):
    return {'anchor_uid':'fiction:drug-a','relation':relation,'subject':'Asterol','object':name,
            'uid':uid,'name':name,'source':'fictional','kind':None,'conflict':None,'evidence':None}


def test_expansion_rows_state_relationship_type_and_flag_sampling():
    rows = [expansion_row('CONTRAINDICATED_FOR','fiction:disease','Orion syndrome'),
            *[expansion_row('INTERACTS_WITH',f'fiction:drug-{i}',f'Drug {i}') for i in range(4)]]
    store = ExpansionStore(rows)
    result = expand.search(store,['fiction:drug-a'],hops=1)
    assert 'type(r) AS relation' in store.statements[0]
    assert result.rows[0]['relation']=='CONTRAINDICATED_FOR' and result.truncated
    assert not expand.search(ExpansionStore(rows[:2]),['fiction:drug-a'],hops=1).truncated
    store = ExpansionStore([])
    expand.search(store,['fiction:drug-a'],hops=2)
    assert 'relation: type(r)' in store.statements[0]


class EvidenceStore(Store):
    def run_generated(self,statement,params):
        rows = [dict(ENTITIES[3],source='openfda_extracted',evidence=[f'chunk:{i:02d}' for i in range(30)])]
        return QueryResult(rows,statement)


def test_dropped_evidence_chunks_mark_the_answer_partial(monkeypatch):
    pipeline = app(monkeypatch,Model())
    pipeline.store = EvidenceStore()
    result = pipeline.ask('What are the side effects of Asterol?')
    assert result['truncated'] and 'Only part' in result['answer']


def fake_client(llm):
    usage = SimpleNamespace(prompt_tokens=3,completion_tokens=2)
    response = SimpleNamespace(usage=usage,choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))])
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response)))


def test_runtime_client_has_no_lifetime_token_cap_unless_configured(monkeypatch,tmp_path):
    monkeypatch.delenv('TOKEN_BUDGET',raising=False)
    settings = Settings(llm_api_key='fictional',llm_model='fictional',llm_base_url='http://127.0.0.1:9',
                        llm_cooldown=0,neo4j_password='fictional')
    assert settings.token_budget is None
    llm = LLMClient(settings)
    llm.ledger = tmp_path/'usage_log.jsonl'
    llm.ledger.write_text(json.dumps({'call_id':'old','charged_tokens':20_000_000})+'\n',encoding='utf8')
    fake_client(llm)
    assert llm.chat([{'role':'user','content':'hello'}])=='ok'
    llm.settings.token_budget = 10
    with pytest.raises(RuntimeError,match='budget'):
        llm.chat([{'role':'user','content':'hello'}])
