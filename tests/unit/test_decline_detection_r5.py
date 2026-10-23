"""R5 decline wording and first-sentence boundaries."""

import pytest

from medkg.qa.answer import unsupported_response


@pytest.mark.parametrize('body', [
    'Based on the provided evidence, there is no information available to determine the answer.',
    'No information regarding the requested relationship was found in the provided evidence.',
    'No information regarding the requested relationship is available in the provided evidence.',
    'No information regarding the requested relationship is provided in the evidence.',
    'I am sorry, but the provided evidence does not contain information about the relationship.',
    "I'm sorry, the provided evidence does not contain information about the relationship.",
    'I\u2019m sorry but there is insufficient evidence to determine the answer.',
    'There is no information.',
    'There is insufficient information to answer this question.',
    'There is no evidence available to answer this question.',
    'No information is provided in the evidence.',
    'No relevant evidence was provided in the context.',
    'No relevant information about the relationship was retrieved in the evidence.',
    'No relevant evidence on the relationship were found in the evidence.',
    'No evidence concerning the relationship are available in the evidence.',
    'No evidence regarding the relationship is provided in the context.',
    "I'm sorry, but based on the provided evidence, there is no information available.",
    "Based on the provided evidence, I'm sorry, but no information is provided.",
    '  **I am sorry, but no information regarding the relationship is provided.**',
])
def test_r5_decline_paraphrases(body):
    assert unsupported_response(body)


@pytest.mark.parametrize('body', [
    'No interaction is recorded between A and B.',
    'Aspirin treats pain. No information regarding dosing is provided.',
    'There is no known cure, but the following drugs are used: Asterol.',
    'I am sorry, but I cannot provide doses. The graph records Asterol as an association.',
    'Based on the provided evidence, Asterol treats pain. No information is provided about dosing.',
    'There is no informationfulness about the relationship.',
    'There is insufficient evidences about the relationship.',
    'No information regarding the relationship. Additional context is provided below.',
    'No information regarding the relationship? Additional context is provided below.',
    'No information regarding the relationship! Additional context is provided below.',
    'No information regarding  was found in the evidence.',
    'I am sorry. No information regarding the relationship is provided.',
])
def test_r5_answer_and_sentence_boundaries(body):
    assert not unsupported_response(body)


@pytest.mark.parametrize('topic_length, expected', [(1, True), (200, True), (201, False)])
def test_r5_decline_topic_length_limit(topic_length, expected):
    body = 'No information regarding ' + 'x' * topic_length + ' was found in the evidence.'
    assert unsupported_response(body) is expected
