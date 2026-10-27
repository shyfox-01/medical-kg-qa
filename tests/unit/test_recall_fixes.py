"""Text recall fixes found on the text questions (D119-D121), fictional data only."""

import pytest

from medkg.config import Settings
from medkg.graph.store import QueryResult
from medkg.qa import confirm
from medkg.qa.linker import Candidate, Linker
from medkg.qa.pipeline import Pipeline, topic_titles
from tests.unit.test_label_resolution import EmptyGraphStore
from tests.unit.test_review_regressions import Model, span, trace

ENTITIES = [
    {'uid': 'fiction:drug-a', 'label': 'Drug', 'name': 'Asterol', 'synonyms': []},
    {'uid': 'fiction:hypo', 'label': 'Phenotype', 'name': 'Hypofictension', 'synonyms': []},
    {'uid': 'fiction:anal', 'label': 'Disease', 'name': 'anus fiction neoplasm', 'synonyms': []},
    {'uid': 'fiction:cancer', 'label': 'Disease', 'name': 'cancer', 'synonyms': []},
    {'uid': 'fiction:kap-1', 'label': 'Disease', 'name': 'Kaposi fiction', 'synonyms': []},
    {'uid': 'fiction:kap-2', 'label': 'Disease', 'name': "Kaposi's fiction (disease)",
     'synonyms': ['Kaposi fiction']},
    {'uid': 'fiction:cornual', 'label': 'Disease', 'name': 'pregnancy, cornual', 'synonyms': []},
]
TITLES = {'anal cancer': {'fiction:anal'}, 'kaposi fiction': {'fiction:kap-2'}, 'pregnancy': set(),
          'pregnancy and nutrition': set(), 'opioid fiction': {'fiction:elsewhere'}}
TEXT = QueryResult([{'uid': 'chunk:a', 'name': 'Asterol label', 'source': 'openfda',
                     'text': 'Asterol may cause low blood pressure.'}], '')


def pipeline(monkeypatch, plan=None):
    monkeypatch.setattr('medkg.qa.pipeline.request_trace', trace)
    monkeypatch.setattr('medkg.qa.pipeline.span', span)
    monkeypatch.setattr('medkg.qa.pipeline.text2cypher.retrieve',
                        lambda store, llm, question, candidates: QueryResult([], 'MATCH (n) RETURN n'))
    found = Pipeline(Settings(phase=3, cache=False), store=EmptyGraphStore(), llm=Model(plan=plan),
                     entities=ENTITIES)
    calls = []

    def text_tool(name, args):
        calls.append((name, args))
        return TEXT
    monkeypatch.setattr(found, '_hybrid_tool', text_tool)
    return found, calls


def generated(question):
    return {'steps': [{'tool': 'text2cypher', 'args': {'question': question}}]}


def test_an_empty_generated_query_is_followed_by_the_documents_about_the_named_entity(monkeypatch):
    question = 'Can Asterol lower blood pressure?'
    p, calls = pipeline(monkeypatch, generated(question))
    result = p.ask(question)
    assert calls == [('vector_search', {'query': question, 'uids': ['fiction:drug-a']})]
    assert result['retrieval_fallback'] == 'vector_search' and result['response_status'] == 'answered'


def test_no_text_fallback_without_a_named_entity_or_after_several_steps(monkeypatch):
    question = 'Can blorptastic lower blood pressure?'
    p, calls = pipeline(monkeypatch, generated(question))
    assert p.ask(question)['response_status'] == 'unsupported' and calls == []
    question = 'Can Asterol lower blood pressure?'
    p, calls = pipeline(monkeypatch, {'steps': [generated(question)['steps'][0],
                                                {'tool': 'vector_search', 'args': {'query': question}}]})
    p.ask(question)
    assert calls == [('vector_search', {'query': question})]


def test_a_misspelt_name_run_into_other_words_is_linked_alone():
    candidates, unresolved = Linker(ENTITIES).question_mentions('Can hypofictention make me dizzy?')
    assert [(c.mention, c.name, c.method) for c in candidates] == [('hypofictention', 'Hypofictension', 'fuzzy')]
    assert unresolved == ['dizzy']
    # Without an unknown long word that a spelling match links, the span stays whole.
    assert Linker(ENTITIES).question_mentions('Can blorptastic make me dizzy?') == (
        [], ['blorptastic make me dizzy'])


def candidate(uid, mention=None, method='fuzzy'):
    entity = next(e for e in ENTITIES if e['uid'] == uid)
    return Candidate(uid, entity['name'], entity['label'], 90, method, False, mention)


def test_an_asked_back_name_inside_a_title_is_resolved_to_the_page_entry():
    checked = confirm.Review(suggestions=[('Anal Cancer', [candidate('fiction:anal'), candidate('fiction:cancer')])])
    checked = confirm.by_title('What does the summary of Anal Cancer say?', checked, TITLES)
    assert [(c.uid, c.method, c.mention) for c in checked.kept] == [('fiction:anal', 'title', 'Anal Cancer')]
    assert not checked.suggestions and [m for m, _ in checked.corrections] == ['Anal Cancer']


@pytest.mark.parametrize('question', ['What does the summary of Pregnancy and Nutrition say?',
                                      'What does the summary of HIV and Pregnancy say?'])
def test_a_name_under_a_page_about_no_entity_is_left_to_the_text(question):
    # "Pregnancy" is a topic of its own, even inside a longer title.
    titles = {**TITLES, 'hiv and pregnancy': {'fiction:hiv'}}
    checked = confirm.Review(suggestions=[('Pregnancy', [candidate('fiction:cornual')])])
    checked = confirm.by_title(question, checked, titles)
    assert checked.unresolved == ['pregnancy'] and not checked.suggestions and not checked.kept


def test_a_page_about_another_entry_or_no_title_leaves_the_question():
    for question in ('Is opioid fiction dangerous?', 'Is Anal Fiction dangerous?'):
        group = [candidate('fiction:anal')]
        mention = 'opioid fiction' if 'opioid' in question else 'Anal Fiction'
        checked = confirm.by_title(question, confirm.Review(suggestions=[(mention, group)]), TITLES)
        assert checked.suggestions == [(mention, group)] and not checked.kept


def test_several_exact_entries_are_narrowed_to_the_page_entry():
    linker = Linker(ENTITIES)
    checked = confirm.review(linker, *linker.question_mentions('How does MedlinePlus describe Kaposi Fiction?'))
    assert len(checked.kept) == 2
    checked = confirm.by_title('How does MedlinePlus describe Kaposi Fiction?', checked, TITLES)
    assert [(c.uid, c.ambiguous) for c in checked.kept] == [('fiction:kap-2', False)]
    assert [(m, [c.uid for c in g]) for m, g in checked.corrections] == [('Kaposi Fiction', ['fiction:kap-2'])]


def test_the_pipeline_reads_the_titles_and_answers_instead_of_asking(monkeypatch):
    p, calls = pipeline(monkeypatch)
    p.store.read = lambda statement, params=None, **kwargs: (
        [{'title': 'Kaposi Fiction', 'about': ['fiction:kap-2']}] if 'medlineplus' in statement else [])
    result = p.ask('What are the symptoms of Kaposi Fiction?')
    assert 'clarification' not in result and result['response_status'] == 'answered'
    assert calls == [('vector_search', {'query': 'What are the symptoms of Kaposi Fiction?',
                                        'uids': ['fiction:kap-2']})]
    assert result['answer'].startswith('Note: read "Kaposi Fiction" as')


def test_a_phrase_the_model_check_asks_back_is_settled_by_its_title(monkeypatch):
    p, calls = pipeline(monkeypatch)
    p.titles = TITLES

    def asked_back(linker, question, checked, judge, typed=None):
        checked.kept = [c for c in checked.kept if c.uid != 'fiction:cancer']
        checked.suggestions.append(('Anal Cancer', [candidate('fiction:anal')]))
        return checked
    monkeypatch.setattr('medkg.qa.pipeline.confirm.check_phrases', asked_back)
    result = p.ask('What are the symptoms of Anal Cancer?')
    assert 'suggestions' not in result and result['response_status'] == 'answered'
    assert [(c['uid'], c['method']) for c in result['candidates']] == [('fiction:anal', 'title')]


def test_topic_titles_are_normalized_and_keep_pages_about_no_entity():
    class Store:
        def read(self, statement, params=None):
            return [{'title': 'Anal Cancer', 'about': ['fiction:anal']},
                    {'title': 'Pregnancy and Nutrition', 'about': []}, {'title': '', 'about': []}]
    assert topic_titles(Store()) == {'anal cancer': {'fiction:anal'}, 'pregnancy and nutrition': set()}
