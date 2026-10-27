"""The demo page shows an answer's light Markdown (bullets, bold) as text, never as HTML."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[2]/'src/medkg/api/static/index.html'
pytestmark = pytest.mark.skipif(shutil.which('node') is None, reason='needs Node.js')


def parts(text):
    function = re.search(r'\n    function answerParts\(text\) \{.*?\n    \}\n',
                         PAGE.read_text(encoding='utf8'), re.S).group(0)
    script = function+f'\nprocess.stdout.write(JSON.stringify(answerParts({json.dumps(text)})));'
    run = subprocess.run([shutil.which('node'), '-e', script], capture_output=True, encoding='utf8', check=True)
    return json.loads(run.stdout)


def test_bullets_and_bold_spans_are_marked():
    assert parts('Tests:\n*   **Spirometry**: lung function\n    *   Peak flow') == [
        ['text', 'Tests:\n• '], ['strong', 'Spirometry'], ['text', ': lung function\n    • Peak flow']]


def test_other_text_is_left_as_written():
    text = 'Count: 68 drugs (Source: primekg). 2 * 3 is no bullet, **unclosed and <b>tags</b> stay text.'
    assert parts(text) == [['text', text]]
