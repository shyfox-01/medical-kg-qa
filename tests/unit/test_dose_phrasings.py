"""More dose-request phrasings are recognised, without flagging look-alikes (D111)."""

import json
from pathlib import Path

import pytest

from medkg.qa import safety

ROWS = [json.loads(line) for line in
        (Path(__file__).resolve().parents[2] / 'eval/datasets/dose_dev_v1.jsonl').read_text(encoding='utf8').splitlines()]


@pytest.mark.parametrize('row', ROWS, ids=[r['id'] for r in ROWS])
def test_dose_requests_are_caught_and_look_alikes_are_not(row):
    triage = safety.triage(row['question'])
    if row['dose']:
        assert triage.category == 'dosage', row['question']
    else:
        assert triage.mode == 'none', (row['question'], triage)


def test_a_mixed_question_keeps_its_knowledge_part():
    triage = safety.triage('What strengths does atorvastatin come in? What are its side effects?')
    assert triage.mode == 'caveat' and triage.question == 'What are its side effects?'
