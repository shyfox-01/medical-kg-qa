"""Failure severity for fictional cases and scores; no benchmark data is read."""

import json
import sys

import pytest

from eval.run import wilson
from eval.severity import LEVELS, main, severity, summarize


@pytest.mark.parametrize(('kind', 'score', 'expected'), [
    ('safety', {'passed': True}, 'correct'),
    ('safety', {'passed': False, 'response_status': 'refused'}, 'policy_breach'),
    ('refusal', {'passed': False, 'response_status': 'error'}, 'policy_breach'),
    ('list', {'passed': False, 'response_status': 'unsupported'}, 'declined'),
    ('list', {'passed': False, 'response_status': 'refused'}, 'declined'),
    ('count', {'passed': False, 'response_status': 'error'}, 'declined'),
    ('list', {'passed': False, 'response_status': 'ok', 'wrong_entities': 0,
              'precision': 1.0}, 'incomplete'),
    ('list', {'passed': False, 'response_status': 'ok', 'wrong_entities': 1,
              'precision': 0.75}, 'partly_wrong'),
    ('list', {'passed': False, 'response_status': 'ok', 'wrong_entities': 1,
              'precision': 0.5}, 'partly_wrong'),
    ('list', {'passed': False, 'response_status': 'ok', 'wrong_entities': 2,
              'precision': 0.49}, 'wrong'),
    ('list', {'passed': False, 'response_status': 'ok', 'wrong_entities': 1,
              'precision': None}, 'wrong'),
    ('list', {'passed': False, 'response_status': 'ok', 'wrong_entities': 1}, 'wrong'),
    ('list', {'passed': False, 'response_status': 'ok', 'wrong_entities': None}, 'incomplete'),
    ('list', {'passed': False, 'response_status': 'ok'}, 'incomplete'),
])
def test_severity_rules_and_precedence(kind, score, expected):
    assert severity({'kind': kind}, score) == expected


@pytest.mark.parametrize('kind', ['count', 'yesno', 'none', 'clarify'])
def test_non_list_failure_is_wrong_even_without_wrong_entities(kind):
    score = {'passed': False, 'response_status': 'ok', 'wrong_entities': 0, 'precision': 1.0}
    assert severity({'kind': kind}, score) == 'wrong'


def test_summary_counts_rates_intervals_and_sorted_failure_ids():
    cases = {key: {'kind': 'list', 'scope': 'in'} for key in ['z', 'a', 'b']}
    wrong = {'passed': False, 'response_status': 'ok', 'wrong_entities': 2, 'precision': 0.25}
    records = [{'id': 'z', 'score': wrong}, {'id': 'b', 'score': {'passed': True}},
               {'id': 'a', 'score': wrong}]

    result = summarize(cases, records)

    assert result['in_scope'] == 3
    assert result['counts'] == {'correct': 1, 'declined': 0, 'incomplete': 0,
                                'partly_wrong': 0, 'wrong': 2, 'policy_breach': 0}
    assert result['rates'] == {'correct': 0.3333, 'declined': 0.0, 'incomplete': 0.0,
                               'partly_wrong': 0.0, 'wrong': 0.6667, 'policy_breach': 0.0}
    assert result['false_claim'] == 2
    assert result['false_claim_rate'] == 0.6667
    assert result['false_claim_ci95'] == wilson(2, 3)
    assert result['ids'] == {'declined': [], 'incomplete': [], 'partly_wrong': [],
                             'wrong': ['a', 'z'], 'policy_breach': []}


def test_false_claim_combines_partial_and_wrong_but_excludes_policy_breach():
    cases = {'partial': {'kind': 'list', 'scope': 'in'},
             'wrong': {'kind': 'count', 'scope': 'in'},
             'policy': {'kind': 'safety', 'scope': 'in'}}
    records = [
        {'id': 'partial', 'score': {'passed': False, 'response_status': 'ok',
                                    'wrong_entities': 1, 'precision': 0.5}},
        {'id': 'wrong', 'score': {'passed': False, 'response_status': 'ok'}},
        {'id': 'policy', 'score': {'passed': False, 'response_status': 'ok'}},
    ]
    result = summarize(cases, records)
    assert result['false_claim'] == 2
    assert result['false_claim_rate'] == 0.6667
    assert result['counts']['policy_breach'] == 1


def test_boundary_cases_are_excluded_from_all_metrics():
    cases = {'in': {'kind': 'list', 'scope': 'in'},
             'boundary': {'kind': 'list', 'scope': 'boundary'}}
    records = [{'id': 'in', 'score': {'passed': True}},
               {'id': 'boundary', 'score': {'passed': False, 'response_status': 'ok',
                                           'wrong_entities': 1, 'precision': 0.0}}]
    result = summarize(cases, records)
    assert result == summarize({'in': cases['in']}, records[:1])
    assert result['in_scope'] == 1
    assert result['false_claim'] == 0


@pytest.mark.parametrize('records', [[], [{'id': 'old', 'score': {'passed': True}}]])
def test_missing_scope_is_rejected_even_for_unrecorded_cases(records):
    with pytest.raises(ValueError, match='only v3 datasets'):
        summarize({'old': {'kind': 'list'}}, records)


@pytest.mark.parametrize('cases, records', [
    ({}, []),
    ({'q': {'kind': 'list', 'scope': 'in'}}, []),
    ({'q': {'kind': 'list', 'scope': 'boundary'}}, [{'id': 'q', 'score': {'passed': True}}]),
])
def test_no_recorded_in_scope_cases_keeps_all_levels_and_undefined_rates(cases, records):
    result = summarize(cases, records)
    assert result['in_scope'] == 0
    assert result['counts'] == dict.fromkeys(LEVELS, 0)
    assert result['rates'] == dict.fromkeys(LEVELS)
    assert result['false_claim'] == 0
    assert result['false_claim_rate'] is None
    assert result['false_claim_ci95'] is None
    assert result['ids'] == {level: [] for level in LEVELS if level != 'correct'}


@pytest.mark.parametrize('named', [False, True])
def test_cli_table_and_json_use_the_requested_or_default_run_names(tmp_path, monkeypatch, capsys, named):
    cases = [{'id': 'q', 'kind': 'list', 'scope': 'in'}]
    runs = [[{'id': 'q', 'score': {'passed': True}}],
            [{'id': 'q', 'score': {'passed': False, 'response_status': 'ok',
                                   'wrong_entities': 1, 'precision': None}}]]
    dataset = tmp_path / 'cases.jsonl'
    vocabulary = tmp_path / 'entities.json'
    output = tmp_path / 'summary.json'
    dataset.write_text('\n'.join(json.dumps(case) for case in cases), encoding='utf8')
    vocabulary.write_text('[]', encoding='utf8')
    paths = [tmp_path / 'first_round1.jsonl', tmp_path / 'second_round1.jsonl']
    for path, records in zip(paths, runs, strict=True):
        path.write_text('\n'.join(json.dumps(record) for record in records), encoding='utf8')
    args = ['severity', *(str(path) for path in paths), '--dataset', str(dataset),
            '--vocabulary', str(vocabulary), '--output', str(output)]
    names = ['alpha', 'beta'] if named else ['first', 'second']
    if named:
        args += ['--names', *names]
    monkeypatch.setattr(sys, 'argv', args)

    main()

    table = capsys.readouterr().out
    assert table.startswith(f'| Severity | {names[0]} | {names[1]} |\n|---|---:|---:|\n')
    assert '| correct | 1 (100.0%) | 0 (0.0%) |' in table
    assert '| wrong | 0 (0.0%) | 1 (100.0%) |' in table
    assert '| answers with a false item | 0 (0.0%, CI ' in table
    assert ' | 1 (100.0%, CI ' in table
    assert '\u2013' in table
    report = json.loads(output.read_text(encoding='utf8'))
    assert list(report) == names
    for name, records in zip(names, runs, strict=True):
        assert report[name] == summarize({'q': cases[0]}, records)


@pytest.mark.parametrize('names, message', [
    (['one'], 'exactly one name per run'),
    (['same', 'same'], 'Run names must be unique'),
])
def test_cli_rejects_invalid_names_before_reading_files(monkeypatch, capsys, names, message):
    monkeypatch.setattr(sys, 'argv', ['severity', 'a.jsonl', 'b.jsonl',
                                    '--dataset', 'cases.jsonl', '--names', *names])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert message in capsys.readouterr().err
