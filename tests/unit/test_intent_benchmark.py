"""The MedicationQA intent benchmark scores outcomes as fixed in advance (D110)."""

from eval.build_medicationqa import TYPE_TO_INTENT
from eval.intent_benchmark import summarise


def row(gold, outcome, **extra):
    return {'gold': gold, 'outcome': outcome, 'question_types': extra.pop('types', ['Usage']), **extra}


def test_rules_only_treats_every_reading_as_the_planner():
    rows = [row('side_effects', 'rule', intent='side_effects'), row('side_effects', 'read', intent='side_effects'),
            row('indications', 'read', intent='targets'), row('interactions', 'ask', offered=['interactions']),
            row(None, 'read', intent='indications'), row(None, 'blocked', types=['Dose'])]
    summary = summarise(rows)
    assert summary['mapped_rules_only'] == {'planner': 3, 'right_intent': 1}
    assert summary['mapped_with_d108'] == {'asked_with_right_option': 1, 'right_intent': 2, 'wrong_intent': 1}
    assert summary['unmapped_with_d108'] == {'blocked': 1, 'template_for_unmapped': 1}
    assert summary['dose_outcomes'] == {'blocked': 1}


def test_the_mapping_covers_only_template_intents():
    from medkg.retrieval.templates import SPECS
    assert set(TYPE_TO_INTENT.values()) <= set(SPECS) and 'Dose' not in TYPE_TO_INTENT
