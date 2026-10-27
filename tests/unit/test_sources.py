"""Sources listed one per document, label links for people, and the page layout (D123)."""

from pathlib import Path

from medkg.graph.store import QueryResult
from medkg.ingest.openfda import label_url
from medkg.qa import answer
from tests.unit.test_recall_fixes import generated, pipeline

PAGE = Path(__file__).resolve().parents[2]/'src/medkg/api/static/index.html'
LABEL = 'https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=set-1'


def chunk(section, url=LABEL, title='ASTEROL; ASTEROL', source='openfda'):
    return {'uid': f'chunk:{section}', 'name': title, 'text': 'Asterol may cause low blood pressure.', 'section': section,
            'url': url, 'title': title, 'source': source}


def test_sections_of_one_document_are_one_source():
    rows = [chunk('adverse_reactions'), chunk('boxed_warning'), chunk('adverse_reactions'),
            chunk('summary', 'https://medlineplus.gov/orionfever.html', 'Orion Fever', 'medlineplus'),
            {'uid': 'fiction:disease', 'name': 'Orion fever', 'source': 'primekg'},
            {'uid': 'fiction:other', 'name': 'Vela syndrome', 'sources': ['openfda_extracted', 'primekg']}]
    assert answer.sources(rows) == [
        {'source': 'openfda', 'url': LABEL, 'title': 'Asterol', 'sections': ['adverse reactions', 'boxed warning']},
        {'source': 'medlineplus', 'url': 'https://medlineplus.gov/orionfever.html', 'title': 'Orion Fever',
         'sections': []},
        {'source': 'openfda_extracted'}, {'source': 'primekg'}]


def test_label_titles_are_shown_in_title_case_without_repeats():
    assert answer.document_title('DIAZEPAM; DIAZEPAM') == 'Diazepam'
    assert answer.document_title('ACETAMINOPHEN AND CODEINE PHOSPHATE') == 'Acetaminophen and Codeine Phosphate'
    assert answer.document_title('A; B; C; D') == 'A / B / C …'
    assert answer.document_title('Orion Fever') == 'Orion Fever'


def test_a_label_links_to_its_dailymed_page_when_it_has_a_set_id():
    assert label_url({'set_id': 'abc-1', 'id': 'v9'}, 'v9') == 'https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=abc-1'
    assert label_url({'id': 'v9'}, 'v9').startswith('https://api.fda.gov/drug/label.json?search=id')


def test_the_pipeline_returns_the_sources_with_the_answer(monkeypatch):
    question = 'Can Asterol lower blood pressure?'
    p, _ = pipeline(monkeypatch, generated(question))
    monkeypatch.setattr(p, '_hybrid_tool', lambda name, args: QueryResult([chunk('adverse_reactions')], ''))
    result = p.ask(question)
    assert result['sources'] == [{'source': 'openfda', 'url': LABEL, 'title': 'Asterol',
                                  'sections': ['adverse reactions']}]
    assert 'Sources: openfda' in result['answer']   # the text footer stays for the CLI and the API


def test_the_page_folds_the_technical_details_and_lists_sources_as_links():
    page = PAGE.read_text(encoding='utf8')
    assert 'How this was answered' in page and 'details(card, "Graph queries", true)' not in page
    assert 'function sourcesBlock' in page and 'link.rel = "noopener noreferrer"' in page
    assert 'class="composer"' in page and 'position: sticky' in page
