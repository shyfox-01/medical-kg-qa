"""The star map's payload and the streamed progress events (D128), fictional entities only."""

import gzip
import json

from fastapi.testclient import TestClient

from medkg.api.app import StarMap, create_app
from tests.unit.test_api import Pipeline


class Progressing(Pipeline):
    def ask(self, question, history, events=None):
        events('linked', {'route': 'template', 'entities': [{'uid': 'fiction:drug-a', 'name': 'Asterol', 'label': 'Drug'}]})
        events('step', {'kind': 'graph', 'sources': ['fiction:drug-a'], 'within': [], 'expected': [],
                        'results': [{'uid': 'fiction:phenotype-a', 'name': 'Amber spots'}, {'uid': 'fiction:x', 'name': 'X'}]})
        return super().ask(question, history)


def built(tmp_path):
    payload = {'count': 2, 'types': ['Drug'], 'regions': [], 'areas': []}
    (tmp_path / 'starmap.json.gz').write_bytes(gzip.compress(json.dumps(payload).encode()))
    (tmp_path / 'starmap_uids.json').write_text(json.dumps(['fiction:drug-a', 'fiction:phenotype-a']))
    return StarMap(tmp_path / 'starmap.json.gz')


def test_the_map_is_404_until_it_is_built(tmp_path):
    with TestClient(create_app(Pipeline())) as client:
        client.app.state.starmap = StarMap(tmp_path / 'starmap.json.gz')
        assert client.get('/starmap').status_code == 404
        client.app.state.starmap = built(tmp_path)
        response = client.get('/starmap')
        assert response.status_code == 200 and response.headers['content-encoding'] == 'gzip'
        assert response.json()['count'] == 2


def test_progress_is_streamed_before_the_answer_with_each_entity_placed(tmp_path):
    with TestClient(create_app(Progressing())) as client:
        client.app.state.starmap = built(tmp_path)
        text = client.post('/ask/stream', json={'question': 'What does Asterol cause?'}).text
    kinds = [line[7:] for line in text.splitlines() if line.startswith('event: ')]
    assert kinds == ['status', 'linked', 'step', 'answer', 'result']
    data = [json.loads(line[6:]) for line in text.splitlines() if line.startswith('data: ')]
    assert data[1]['entities'][0]['i'] == 0
    assert data[2]['sources'] == [{'uid': 'fiction:drug-a', 'i': 0}]
    assert [r['i'] for r in data[2]['results']] == [1, None]


def test_a_pipeline_without_events_still_streams_its_answer():
    with TestClient(create_app(Pipeline())) as client:
        text = client.post('/ask/stream', json={'question': 'What is recorded?'}).text
    assert [line[7:] for line in text.splitlines() if line.startswith('event: ')] == ['status', 'answer', 'result']


def test_the_page_script_is_served():
    with TestClient(create_app(Pipeline())) as client:
        response = client.get('/static/starmap.js')
    assert response.status_code == 200 and 'StarMap' in response.text
    for forbidden in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', '"http', "'http"):
        assert forbidden not in response.text
