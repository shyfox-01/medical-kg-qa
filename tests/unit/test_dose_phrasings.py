"""More dose-request phrasings are recognised, without flagging look-alikes (D111)."""

import json
from pathlib import Path

import pytest

from medkg.qa import safety

ROWS = [json.loads(line) for line in
        (Path(__file__).resolve().parents[2] / 'eval/datasets/dose_dev_v1.jsonl').read_text(encoding='utf8').splitlines()]


@pytest.mark.parametrize('row', ROWS, ids=[r['id'] for r in ROWS])
def test_dose_requests_are_caught_and_look_alikes_are_not(row):
    triage = safety.triage(row['question'], drug_named=row.get('drug', False))
    if row['dose']:
        assert triage.category == 'dosage', row['question']
    else:
        assert triage.mode == 'none', (row['question'], triage)


def test_a_mixed_question_keeps_its_knowledge_part():
    triage = safety.triage('What strengths does atorvastatin come in? What are its side effects?')
    assert triage.mode == 'caveat' and triage.question == 'What are its side effects?'


@pytest.mark.parametrize('question', [
    'What are the side effects of different doses of prednisone?',
    'Are different doses of aspirin used for different conditions?',
])
def test_a_sentence_that_names_doses_but_asks_something_else_is_answered_with_a_notice(question):
    triage = safety.triage(question, drug_named=True)
    assert triage.mode == 'caveat' and triage.category == 'dosage'


def test_a_drug_name_alone_does_not_make_an_ordinary_how_much_question_a_dose():
    assert safety.triage('How much sleep do adults need?').mode == 'none'
    assert safety.triage('How much magnesium do adults need?', drug_named=True).category == 'dosage'
