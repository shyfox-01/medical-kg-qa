"""Summary consumers must not interpret entity coverage as semantic accuracy."""

import pytest

from eval.run import code_fingerprint, summarize
from eval.score import Vocabulary, score


def test_summary_keeps_semantic_support_unmeasured_even_with_entity_match():
    case = {'id': 'synthetic', 'kind': 'text', 'category': 'text_only',
            'answer_phrases': ['Luna']}
    result = {'answer': 'Luna is green.', 'contexts': [{'uid': 'moon', 'text': 'Luna is red.'}]}
    measured = score(case, result, Vocabulary([{'uid': 'moon', 'name': 'Luna', 'label': 'Synthetic'}]))
    row = {'id': case['id'], 'category': case['category'], 'failure_stage': None,
           'score': measured, 'execution_exact': None, 'latency_s': 0.1, 'usage': {}}
    report = summarize([[row]], [case])
    category = report['categories']['text_only']
    assert category['entity_supported'] == 1
    assert category['faithful'] == 1  # Backward-compatible entity-only diagnostic.
    assert category['semantic_support'] is None
    assert report['semantic_support_status'] == 'not_evaluated'
    assert 'not semantic' in report['metric_semantics']['quality_passed']


@pytest.mark.parametrize('changed_file', [
    'src/medkg_data/alias_policy.py', 'src/medkg_data/lexicon.py',
    'frozen/medkg/qa/pipeline.py',
])
def test_frozen_system_checkpoint_includes_current_scorer_dependencies(tmp_path, changed_file):
    files = [
        'eval/client.py', 'eval/score.py', 'eval/run.py',
        'src/medkg_data/alias_policy.py', 'src/medkg_data/lexicon.py',
        'frozen/medkg/qa/pipeline.py', 'frozen/medkg_data/alias_policy.py',
    ]
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('# frozen synthetic implementation\n', encoding='utf8')
    source = tmp_path / 'frozen'
    before = code_fingerprint(source, tmp_path)
    (tmp_path / changed_file).write_text('# changed synthetic implementation\n', encoding='utf8')
    assert code_fingerprint(source, tmp_path) != before
