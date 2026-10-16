"""Provider-neutral thinking control and run identity for local models (fictional settings)."""

from types import SimpleNamespace

import pytest

from eval.run import llm_identity
from medkg.config import Settings
from medkg.llm import LLMClient


def settings(**overrides):
    values = dict(llm_api_key='fictional',llm_model='fictional',llm_base_url='http://127.0.0.1:9',
                  llm_cooldown=0,neo4j_password='fictional')
    return Settings(**{**values,**overrides})


def recorded_request(tmp_path,**overrides):
    requests = []
    usage = SimpleNamespace(prompt_tokens=3,completion_tokens=2)
    response = SimpleNamespace(usage=usage,choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))])
    llm = LLMClient(settings(**overrides))
    llm.ledger = tmp_path/'usage_log.jsonl'
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: requests.append(kwargs) or response)))
    assert llm.chat([{'role':'user','content':'hello'}])=='ok'
    return requests[0]


def test_default_disables_thinking_the_glm_way(monkeypatch,tmp_path):
    monkeypatch.delenv('LLM_THINKING_PARAM',raising=False)
    assert recorded_request(tmp_path)['extra_body']=={'thinking':{'type':'disabled'}}


def test_openai_style_providers_get_reasoning_effort_none(tmp_path):
    request = recorded_request(tmp_path,llm_thinking_param='reasoning_effort')
    assert request['extra_body']=={'reasoning_effort':'none'}
    assert request['temperature']==0


def test_unknown_thinking_parameter_is_rejected():
    with pytest.raises(ValueError,match='LLM_THINKING_PARAM'):
        LLMClient(settings(llm_thinking_param='off'))


def test_run_identity_names_model_and_host_but_never_credentials(monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL','http://user:secret@127.0.0.1:11434/v1')
    monkeypatch.setenv('LLM_MODEL','fictional-local')
    monkeypatch.setenv('LLM_THINKING_PARAM','reasoning_effort')
    monkeypatch.setenv('LLM_API_KEY','fictional-key')
    identity = llm_identity(fake=False)
    assert identity=={'model':'fictional-local','endpoint_host':'127.0.0.1:11434',
                      'thinking_param':'reasoning_effort'}
    assert 'secret' not in str(identity) and 'fictional-key' not in str(identity)
    assert llm_identity(fake=True) is None
