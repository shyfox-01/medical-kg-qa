"""Empty verified answers become the standard decline, disclaimer kept (D102)."""

import pytest

from tests.unit.test_review_regressions import Model, app


def is_standard_decline(answer: str) -> bool:
    """The no-evidence decline with its disclaimer, and no sources or removal notice."""
    return (answer.startswith('No supporting evidence was retrieved.')
            and 'Research demo; not medical advice.' in answer
            and 'Sources:' not in answer and 'Some entries were removed' not in answer)


@pytest.mark.parametrize('suffix', ['', '\n\n---\n***', '\n\nSources: fictional'])
def test_all_unsupported_entries_removed_become_a_decline(monkeypatch, suffix):
    model = Model(text='- Indigo spots' + suffix)
    pipeline = app(monkeypatch, model)
    result = pipeline.ask('What are the side effects of Asterol?')

    assert model.usage['calls'] == 2
    assert is_standard_decline(result['answer'])
    assert result['refused'] is True
    assert result['response_status'] == 'unsupported'
    assert result['failure_stage'] is None
    assert 'answer_completed' not in result
    assert any(row.get('name') == 'Amber spots' for row in result['contexts'])


@pytest.mark.parametrize('text', ['', ' \n---\n***', 'Sources: fictional'])
def test_empty_or_punctuation_only_generation_declines(monkeypatch, text):
    model = Model(text=text)
    result = app(monkeypatch, model).ask('What are the side effects of Asterol?')

    assert model.usage['calls'] == 1
    assert is_standard_decline(result['answer'])
    assert result['refused'] is True
    assert result['response_status'] == 'unsupported'
    assert 'answer_completed' not in result


def test_supported_body_survives_partial_removal(monkeypatch):
    model = Model(text='- Amber spots\n- Indigo spots')
    result = app(monkeypatch, model).ask('What are the side effects of Asterol?')

    assert model.usage['calls'] == 2
    assert result['answer'].startswith('- Amber spots')
    assert 'Indigo spots' not in result['answer']
    assert 'Some entries were removed' in result['answer']
    assert 'Sources: fictional' in result['answer']
    assert result['refused'] is False
    assert result['response_status'] == 'answered'


def test_empty_decline_keeps_the_existing_cache_flow(monkeypatch):
    model = Model(text='- Indigo spots')
    pipeline = app(monkeypatch, model)
    pipeline.settings.cache = True
    first = pipeline.ask('What are the side effects of Asterol?')
    cached = pipeline.ask('What are the side effects of Asterol?')

    assert model.usage['calls'] == 2
    assert cached['cache_hit'] is True
    assert cached['answer'] == first['answer'] and is_standard_decline(first['answer'])
    assert cached['refused'] is True
    assert cached['response_status'] == 'unsupported'
