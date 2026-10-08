"""Post-measurement regression probes: fictional inputs, no provider calls."""

import json
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError, AuthenticationError, InternalServerError, RateLimitError
from pydantic import ValidationError

from medkg.config import Settings
from medkg.llm import LLMClient, provider_backoff
from medkg.qa.planner import Step, plan
from medkg.qa.safety import assess
from tests.unit.test_review_regressions import Model, app


@pytest.mark.parametrize('question',[
    'Which medicines are indicated for fictional infant Orion syndrome?',
    'What drugs are listed as contraindicated for fictional newborn Orion syndrome?',
    'How many drugs are associated with fictional elderly Orion syndrome?',
    'List the recorded side effects of medicines in children.',
])
def test_impersonal_population_graph_lookups_are_not_medication_advice(question):
    assert not assess(question).blocked


@pytest.mark.parametrize('question',[
    'Which listed medicines should my infant take for Orion syndrome?',
    'Which drugs are safe for infants?',
    'What medicine is best for a newborn?',
    'Can children use the listed medicine?',
    'List the recorded medicines and recommend one for my baby.',
    'Which drugs are indicated for Orion syndrome? Give one to the infant.',
    'Show the recorded medicine suitable for a pregnant patient.',
    'Which listed medicines would help a newborn?',
    'List the recorded medicines for infants and choose one.',
    'Medicines for a newborn?',
])
def test_population_advice_still_stops_before_model_or_graph(monkeypatch,question):
    model = Model()
    pipeline = app(monkeypatch,model)
    result = pipeline.ask(question)
    assert result['refused'] and result['safety']=='special_population'
    assert model.usage['calls']==0 and pipeline.store.executed_statements==[]


@pytest.mark.parametrize('value,expected',[
    (True,True),(False,False),(1,True),(0,False),('true',True),(' FALSE ',False),(None,False),
])
def test_template_count_has_unambiguous_boolean_semantics(value,expected):
    step = Step(tool='template',args={'intent':'targets','uids':['fiction:drug'],'count':value})
    assert step.args.get('count',False) is expected


@pytest.mark.parametrize('value',[2,-1,0.5,1.0,'1','yes','25',[],{}])
def test_template_count_rejects_ambiguous_values(value):
    with pytest.raises(ValidationError):
        Step(tool='template',args={'intent':'targets','uids':['fiction:drug'],'count':value})


def test_normalized_plan_does_not_spend_an_extra_repair_call():
    model = Model(plan={'steps':[{'tool':'template',
        'args':{'intent':'targets','uids':['fiction:drug'],'count':1}}]})
    result = plan(model,'How many targets are recorded for Asterol?',[],3)
    assert result.steps[0].args['count'] is True and model.usage['calls']==1
    with pytest.raises(ValidationError):
        Step(tool='template',args={'intent':'targets','uids':['fiction:drug'],'limit':999})


def api_error(kind=RateLimitError,header=''):
    code = {RateLimitError:429,InternalServerError:503,AuthenticationError:401}[kind]
    response = httpx.Response(code,headers={'retry-after':header},
                             request=httpx.Request('POST','https://fiction.invalid'))
    return kind('private provider body must not be logged',response=response,body=None)


@pytest.mark.parametrize('error,expected',[
    (api_error(header='45'),45),(api_error(header='999999'),60),
    (api_error(header='bad'),10),(api_error(header='NaN'),10),
    (api_error(header='-20'),10),(api_error(InternalServerError),10),
    (api_error(AuthenticationError,header='60'),0),
    (APITimeoutError(request=httpx.Request('POST','https://fiction.invalid')),10),
    (ValueError('schema failure'),0),
])
def test_transient_pacing_uses_bounded_provider_hints(error,expected):
    assert provider_backoff(error,1)==expected


def test_retry_after_http_date(monkeypatch):
    monkeypatch.setattr('medkg.llm.time.time',lambda:0.0)
    assert provider_backoff(api_error(header='Thu, 01 Jan 1970 00:00:35 GMT'),1)==35


def test_backoff_is_shared_without_retries_and_usage_is_preserved(monkeypatch,tmp_path):
    clock, sleeps, calls = [1000.0], [], []
    monkeypatch.setattr('medkg.llm.time.time',lambda:clock[0])
    def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay
    monkeypatch.setattr('medkg.llm.time.sleep',sleep)
    settings = Settings(neo4j_password='fictional',llm_api_key='fictional',
                        llm_model='fictional',llm_base_url='http://127.0.0.1:9',llm_cooldown=2)
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=3,completion_tokens=2),
        choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))])
    outcomes = [api_error(),api_error(),response,response]
    def create(**kwargs):
        calls.append(clock[0])
        outcome = outcomes.pop(0)
        if isinstance(outcome,Exception):
            raise outcome
        return outcome
    def client():
        llm = LLMClient(settings)
        llm.ledger = tmp_path/'usage.jsonl'
        llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        return llm
    messages = [{'role':'user','content':'fictional input'}]
    for _ in range(2):
        with pytest.raises(RateLimitError):
            client().chat(messages,max_tokens=20)
    assert client().chat(messages)=='ok'
    assert client().chat(messages)=='ok'
    assert calls==[1000.0,1010.0,1030.0,1032.0]  # No hidden repeated provider requests.
    assert sleeps==[2,8,2,18,2,2]
    records = [json.loads(line) for line in (tmp_path/'usage.jsonl').read_text().splitlines()]
    settled = [r for r in records if r['status']!='reserved']
    assert len(settled)==4 and sum(r['status']=='failed' for r in settled)==2
    assert [r['charged_tokens'] for r in settled]==[135,135,5,5]
    assert [r.get('backoff_seconds') for r in settled]==[10,20,None,None]
    assert 'private provider body' not in (tmp_path/'usage.jsonl').read_text()
    assert json.loads((tmp_path/'llm_backoff.json').read_text())['failures']==0


def test_repeated_failure_pacing_is_capped():
    assert [provider_backoff(api_error(),n) for n in (1,2,3,4,100)]==[10,20,40,60,60]
