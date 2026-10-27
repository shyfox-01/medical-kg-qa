"""Several spellings of an asked-back name are ordered by the question (D118)."""

from medkg.qa import confirm
from medkg.qa.linker import Candidate

HYPO = Candidate('x:hypo', 'hypotensive disorder', 'Disease', 90, 'suggestion', True)
HYPER = Candidate('x:hyper', 'hypertension', 'Disease', 90, 'suggestion', True)
TYPE1 = Candidate('x:t1', 'type 1 diabetes mellitus', 'Disease', 80, 'suggestion', True)


def ranked(scores, group=(HYPER, HYPO, TYPE1)):
    seen = []

    def judge(question, mention, options):
        seen.append([c.name for c in options])
        return scores
    checked = confirm.Review(suggestions=[('hyptotension', list(group)), ('zeltaramyn', [HYPER])])
    result = confirm.rank_suggestions('Can hyptotension make me dizzy?', checked, judge)
    return [[c.name for c in g] for _, g in result.suggestions], seen


def test_a_clear_reading_leaves_one_confirmation():
    order, seen = ranked({2: 0.9, 1: 0.08, 3: 0.02})
    assert order == [['hypotensive disorder'], ['hypertension']]
    assert seen == [['hypertension', 'hypotensive disorder', 'type 1 diabetes mellitus']]   # one option: no call


def test_a_spread_reading_offers_the_likely_spellings_likeliest_first():
    order, _ = ranked({2: 0.55, 1: 0.4, 3: 0.05})
    assert order[0] == ['hypotensive disorder', 'hypertension']


def test_none_of_these_as_the_likeliest_answer_and_a_failed_reply_keep_the_spelling_order():
    order, _ = ranked({0: 0.9, 3: 0.06, 1: 0.04})
    assert order[0] == ['hypertension', 'hypotensive disorder', 'type 1 diabetes mellitus']
    order, _ = ranked(None)
    assert order[0] == ['hypertension', 'hypotensive disorder', 'type 1 diabetes mellitus']
