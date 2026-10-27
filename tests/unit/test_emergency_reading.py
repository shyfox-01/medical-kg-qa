"""A personal message the rules pass is read once more for a possible emergency (D117)."""

import pytest

from medkg.qa import safety


class Chooser:
    def __init__(self, scores=None, error=None):
        self.scores, self.error, self.asked = scores, error, []

    def choose(self, messages, options):
        self.asked.append((messages[0]['content'], messages[1]['content'], options))
        if self.error:
            raise self.error
        return self.scores


def test_only_personal_or_present_wording_is_read():
    model = Chooser({1: 0.9, 2: 0.1})
    assert safety.emergency_reading(model, 'Which drugs treat gout?') is None and not model.asked
    assert safety.emergency_reading(model, 'I took 20 Asterol pills an hour ago.') == pytest.approx(0.9)
    prompt, message, options = model.asked[0]
    assert prompt == safety.EMERGENCY_PROMPT and message == 'Message: I took 20 Asterol pills an hour ago.'
    assert options == 2


def test_the_reading_is_the_share_of_the_first_answer_among_the_two():
    assert safety.emergency_reading(Chooser({1: 0.3, 2: 0.3, 0: 0.4}), 'My son ate my pills.') == pytest.approx(0.5)


@pytest.mark.parametrize('model', [
    object(),                                   # no token probabilities: no chooser
    Chooser(None),                              # the endpoint gave none
    Chooser({0: 0.9, 1: 0.05, 2: 0.05}),        # no digit was replied
    Chooser(error=TimeoutError('slow')),        # the call failed
])
def test_no_reading_leaves_the_rules_alone(model):
    assert safety.emergency_reading(model, 'My son ate my pills.') is None


def test_escalation_replaces_any_rule_decision_with_the_emergency_reply():
    blocked = safety.triage('How many Asterol tablets can I take a day?', 'SG', drug_named=True)
    assert blocked.category == 'dosage'
    escalated = safety.escalated(blocked, 'SG')
    assert (escalated.mode, escalated.category) == ('block', 'possible_emergency')
    assert '995' in escalated.message and 'poison control' in escalated.message


def pipeline(monkeypatch, scores):
    from tests.unit.test_confirm_names import pipeline as build
    from tests.unit.test_review_regressions import Model

    class Reader(Model):
        def choose(self, messages, options):
            return scores if messages[0]['content'] == safety.EMERGENCY_PROMPT else None
    return build(monkeypatch, Reader())


def test_the_pipeline_escalates_a_message_read_as_an_emergency(monkeypatch):
    result = pipeline(monkeypatch, {1: 0.97, 2: 0.03}).ask('I took 20 Asterol pills an hour ago and feel sick.')
    assert result['route'] == 'safety' and result['refused'] and result['safety'] == 'possible_emergency'
    assert result['emergency_reading'] == 0.97 and 'medical emergency' in result['answer']


def test_a_low_reading_is_recorded_and_the_question_answered_as_before(monkeypatch):
    result = pipeline(monkeypatch, {1: 0.02, 2: 0.98}).ask('I take Asterol. What are its side effects?')
    assert result['route'] != 'safety' and result['emergency_reading'] == 0.02


def test_rule_emergencies_are_not_read_again(monkeypatch):
    result = pipeline(monkeypatch, {1: 0.0, 2: 1.0}).ask('I have chest pain after taking Asterol, what should I do?')
    assert result['safety'] == 'emergency' and 'emergency_reading' not in result
