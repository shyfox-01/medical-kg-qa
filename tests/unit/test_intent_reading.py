"""The model reads which question is meant when no rule fits (D108)."""

import math
from types import SimpleNamespace

import pytest

from eval.score import CLARIFY
from medkg.llm import LLMClient
from medkg.qa import intent
from medkg.qa.linker import Candidate
from medkg.qa.router import has_relation_cue
from tests.unit.test_confirm_names import pipeline
from tests.unit.test_review_regressions import Model

ASTEROL = Candidate('fiction:drug-a', 'Asterol', 'Drug', 100, 'exact', False, 'Asterol', (5, 6))
DRUG_QUESTIONS = [i for i, (label, *_) in intent.SPECS.items() if label == 'Drug']


class Chooser(Model):
    """The fixture model, plus option probabilities keyed by intent ('describe', 0 = none)."""

    def __init__(self, scores=None, fail=False):
        super().__init__()
        self.scores, self.fail = scores or {}, fail

    def choose(self, messages, options):
        self.usage['calls'] += 1
        if self.fail:
            raise RuntimeError('endpoint down')
        number = {name: i for i, name in enumerate(DRUG_QUESTIONS + ['describe'], 1)}
        return {number.get(k, k): p for k, p in self.scores.items()}


def client_with(tokens):
    def chat(messages, max_tokens, top_logprobs, sink):
        assert max_tokens == 1 and top_logprobs >= 3
        sink.extend(SimpleNamespace(token=t, logprob=math.log(p)) for t, p in tokens)
        return tokens[0][0] if tokens else ''
    return SimpleNamespace(chat=chat, no_logprobs=False)


def test_choose_reads_the_option_probabilities_of_the_first_token():
    scores = LLMClient.choose(client_with([('2', 0.6), ('0', 0.2), (' 1', 0.1), ('1', 0.05), ('7', 0.05)]), [], 3)
    assert abs(sum(scores.values()) - 1) < 1e-9 and scores[2] == pytest.approx(0.6)
    assert scores[1] == pytest.approx(0.15)                 # " 1" and "1" are one reply
    assert scores[0] == pytest.approx(0.25)                 # 7 is not an option: something else


def test_a_reply_that_is_not_a_number_counts_as_something_else():
    scores = LLMClient.choose(client_with([('None', 0.9), ('3', 0.09), ('0', 0.01)]), [], 3)
    assert scores[0] == pytest.approx(0.91) and scores[3] == pytest.approx(0.09)


def test_an_endpoint_without_log_probabilities_is_asked_once():
    client = client_with([])
    assert LLMClient.choose(client, [], 3) is None and client.no_logprobs
    client.chat = None                                      # not called again
    assert LLMClient.choose(client, [], 3) is None


@pytest.mark.parametrize('scores,mode', [
    ({'side_effects': 0.95, 0: 0.05}, 'answer'),
    ({'side_effects': 0.6, 'indications': 0.3, 0: 0.1}, 'ask'),
    ({0: 0.3, 'describe': 0.4, 'indications': 0.3}, 'pass'),     # a description is answered as before
])
def test_a_clear_reading_is_answered_a_spread_one_asked(scores, mode):
    reading = intent.read(Chooser(scores), 'What is the purpose of Asterol?', [ASTEROL])
    assert reading.mode == mode
    if mode == 'ask':
        assert [o['intent'] for o in reading.offered()] == ['side_effects', 'indications']
        assert CLARIFY.search(intent.clarification(reading))


def test_no_reading_without_probabilities():
    assert intent.read(Model(), 'What is the purpose of Asterol?', [ASTEROL]) is None
    assert intent.read(Chooser(fail=True), 'What is the purpose of Asterol?', [ASTEROL]) is None


@pytest.mark.parametrize('question,cue', [
    ('What is the purpose of Asterol?', False),
    ('Tell me about Asterol', False),
    ('Which drugs target genes associated with Asterol?', True),
    ('What side effects can drugs used to treat Asterol cause?', True),
])
def test_only_questions_without_relation_words_are_read(question, cue):
    assert has_relation_cue(question, [ASTEROL]) is cue


def test_the_pipeline_answers_a_clear_reading_with_a_note_and_offers_the_rest(monkeypatch):
    model = Chooser({'side_effects': 0.97, 'indications': 0.02, 0: 0.01})
    result = pipeline(monkeypatch, model).ask('What is the purpose of Asterol?')
    assert result['route'] == 'template' and result['intent'] == 'side_effects'
    assert result['answer'].startswith('Note: answered as "What are the side effects of Asterol?".')
    assert result['intent_options'][0]['question'] == 'What is Asterol used to treat?'


def test_the_pipeline_asks_when_the_reading_is_spread(monkeypatch):
    model = Chooser({'side_effects': 0.5, 'indications': 0.4, 0: 0.1})
    result = pipeline(monkeypatch, model).ask('What is the purpose of Asterol?')
    assert result['route'] == 'intent' and result['refused'] and model.usage['calls'] == 1
    assert [o['question'] for o in result['intent_options']][:2] == [
        'What are the side effects of Asterol?', 'What is Asterol used to treat?']


def test_the_pipeline_leaves_other_questions_to_the_planner(monkeypatch):
    for model in (Chooser({0: 0.9, 'indications': 0.1}), Model()):
        result = pipeline(monkeypatch, model).ask('What is the purpose of Asterol?')
        assert result['route'] != 'intent' and 'answered as' not in result['answer']


def test_the_demo_page_renders_the_intent_options():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[2]/'src/medkg/api/static/index.html').read_text(encoding='utf8')
    assert 'intent_options' in page and 'Something else' in page and 'Ask instead' in page


def test_an_option_the_safety_triage_would_block_is_never_answered():
    reading = intent.read(Chooser({'side_effects': 0.95, 0: 0.05}), 'What is the purpose of Asterol?', [ASTEROL],
                          allowed=lambda q: 'side effects' not in q)
    assert reading.mode == 'pass' and reading.other == pytest.approx(1.0)


def test_offered_questions_use_the_name_as_written_and_route_by_rule():
    import copy

    from medkg.qa.linker import Linker
    from medkg.qa.router import route
    from tests.unit.test_review_regressions import ENTITIES
    linker = Linker(copy.deepcopy(ENTITIES))
    brand = Candidate('fiction:drug-a', 'Asterol', 'Drug', 100, 'exact', False, 'asterol', (5, 6))
    assert intent.phrase('indications', brand) == 'What is asterol used to treat?'
    for name, (label, *_rest) in intent.SPECS.items():
        anchor = {'Drug': 'Asterol', 'Disease': 'Orion syndrome', 'Phenotype': 'Amber spots'}.get(label)
        if not anchor:
            continue
        question = intent.QUESTIONS[name].format(a=anchor)
        candidates, unresolved = linker.question_mentions(question)
        assert not unresolved and route(question, candidates) == name, question


def test_count_questions_are_not_read(monkeypatch):
    model = Chooser({'side_effects': 0.97, 0: 0.03})
    result = pipeline(monkeypatch, model).ask('How many for Asterol?')
    assert 'answered as' not in result['answer']
