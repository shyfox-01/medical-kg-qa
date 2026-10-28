"""The demo page shows an answer's light Markdown (paragraphs, lists, bold) as elements, never as HTML."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[2]/'src/medkg/api/static/index.html'
pytestmark = pytest.mark.skipif(shutil.which('node') is None, reason='needs Node.js')


def run(call, text):
    page = PAGE.read_text(encoding='utf8')
    functions = ''.join(re.search(rf'\n    function {name}\(text\) \{{.*?\n    \}}\n', page, re.S).group(0)
                        for name in ('inlineParts', 'answerBlocks'))
    script = functions+f'\nprocess.stdout.write(JSON.stringify({call}({json.dumps(text)})));'
    result = subprocess.run([shutil.which('node'), '-e', script], capture_output=True, encoding='utf8', check=True)
    return json.loads(result.stdout)


def test_bold_spans_are_marked_and_other_text_is_left_as_written():
    assert run('inlineParts', '**Spirometry**: lung function') == [['strong', 'Spirometry'], ['text', ': lung function']]
    text = 'Count: 68 drugs (Source: primekg). 2 * 3 is no bullet, **unclosed and <b>tags</b> stay text.'
    assert run('inlineParts', text) == [['text', text]]


def test_paragraphs_headings_and_nested_lists():
    text = ('Asthma is a lung disease.\nIt is common.\n\n**Tests:**\n*   **Spirometry**: lung function\n'
            '    *   Peak flow\n- Chest X-ray\n\n1. First\n2. Second')
    assert run('answerBlocks', text) == [
        {'type': 'p', 'lines': [[['text', 'Asthma is a lung disease.']], [['text', 'It is common.']]]},
        {'type': 'h', 'parts': [['text', 'Tests']]},
        {'type': 'list', 'ordered': False, 'items': [
            {'parts': [['strong', 'Spirometry'], ['text', ': lung function']], 'children': [[['text', 'Peak flow']]]},
            {'parts': [['text', 'Chest X-ray']], 'children': []}]},
        {'type': 'list', 'ordered': True, 'items': [
            {'parts': [['text', 'First']], 'children': []}, {'parts': [['text', 'Second']], 'children': []}]},
    ]


def test_a_number_or_star_inside_a_sentence_is_no_list():
    assert run('answerBlocks', 'Count: 2 * 3 drugs.') == [{'type': 'p', 'lines': [[['text', 'Count: 2 * 3 drugs.']]]}]
