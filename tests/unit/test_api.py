import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from medkg.api.app import create_app
from medkg.config import Settings


def test_demo_page_is_available():
    with TestClient(create_app(Pipeline())) as client:
        response = client.get('/')
        assert response.status_code==200
        assert response.headers['content-type'].startswith('text/html')
        assert 'Research demo, not medical advice' in response.text


def test_demo_page_has_no_external_resources_or_html_injection_sinks():
    with TestClient(create_app(Pipeline())) as client:
        source = client.get('/').text
    for forbidden in ('src="http','href="http','innerHTML','outerHTML',
                      'insertAdjacentHTML','document.write'):
        assert forbidden not in source


def test_demo_page_survives_pipeline_initialization_failure(monkeypatch):
    def fail():
        raise RuntimeError('fixture initialization failure')

    monkeypatch.setattr('medkg.api.app.local_pipeline',fail)
    with TestClient(create_app()) as client:
        assert client.app.state.initialization_error=='RuntimeError'
        assert client.get('/').status_code==200
        assert client.post('/ask',json={'question':'What is recorded?'}).status_code==503


def test_demo_page_is_included_in_package_data():
    project = Path(__file__).resolve().parents[2] / 'pyproject.toml'
    config = tomllib.loads(project.read_text(encoding='utf8'))
    assert 'api/static/*.html' in config['tool']['setuptools']['package-data']['medkg']


class Store:
    def verify(self):
        return None


class Pipeline:
    settings = Settings(neo4j_password='fixture',llm_api_key='fixture',llm_model='fake',
                        llm_base_url='https://example.test')
    store = Store()
    closed = False

    def ask(self,question,history):
        return {'answer':'Fictional supported answer.','contexts':[],'route':'fixture',
                'cypher':[],'trace_id':'1'*32,'question':question,'history':history}

    def close(self):
        self.closed = True


def test_api_health_ready_ask_and_stream():
    pipeline = Pipeline()
    with TestClient(create_app(pipeline)) as client:
        assert client.get('/health').status_code==200
        assert client.get('/ready').json()['status']=='ready'
        result = client.post('/ask',json={'question':'What is recorded?','history':[]})
        assert result.status_code==200 and len(result.json()['trace_id'])==32
        streamed = client.post('/ask/stream',json={'question':'What is recorded?'})
        assert streamed.headers['content-type'].startswith('text/event-stream')
        assert 'event: status' in streamed.text and 'event: result' in streamed.text
        assert 'Fictional supported answer.' in streamed.text
        assert client.post('/ask',json={'question':' '*5}).status_code==422
        assert client.post('/ask',json={'question':'q','history':[{}]*5}).status_code==422
        assert client.post('/ask',json={'question':'q','unexpected':True}).status_code==422
        assert client.post('/ask',json={'question':'q','history':[{'focus':['x'*257]}]}).status_code==422
    assert pipeline.closed


def test_ready_does_not_claim_llm_connectivity():
    pipeline = Pipeline()
    pipeline.settings = Settings(neo4j_password='fixture',llm_api_key='')
    with TestClient(create_app(pipeline)) as client:
        result = client.get('/ready')
        assert result.status_code==503 and not result.json()['llm_configured']
        assert 'password' not in result.text and 'api_key' not in result.text


def test_readiness_reports_failed_graph_connection_without_exception_text():
    class BrokenStore:
        def verify(self):
            raise RuntimeError('secret connection string')
    pipeline = Pipeline()
    pipeline.store = BrokenStore()
    with TestClient(create_app(pipeline)) as client:
        result = client.get('/ready')
        assert result.status_code==503 and not result.json()['neo4j']
        assert 'secret' not in result.text
