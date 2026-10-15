"""Summary consumers must not interpret entity coverage as semantic accuracy."""

from eval.run import summarize
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
