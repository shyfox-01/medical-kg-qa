"""Ask the model which question the user means when the rules cannot tell (D108).

When the router finds no template intent for a question about one entity, the answer
model scores the questions the graph can answer about that entity, as a decision model
would: it replies with one number, and the log-probabilities of that number are read
as probabilities over the options. A clear winner is answered with a visible note and
the other questions are offered; spread probabilities become a choice for the user;
"something else" leaves the question to the planner, as before.
"""

from dataclasses import dataclass, field

from medkg.retrieval.templates import SPECS

QUESTIONS = {
    'indications': 'What is {a} used to treat?',
    'side_effects': 'What are the side effects of {a}?',
    'contraindications': 'In which conditions should {a} not be used?',
    'interactions': 'Which drugs interact with {a}?',
    'targets': 'Which genes or proteins does {a} target?',
    'off_label': 'What is {a} used off-label for?',
    'drugs_for': 'Which drugs treat {a}?',
    'phenotypes': 'What are the symptoms of {a}?',
    'contraindicated_drugs': 'Which drugs should be avoided in {a}?',
    'genes': 'Which genes are linked to {a}?',
    'parents': 'Which broader disease class does {a} belong to?',
    'subtypes': 'What are the subtypes of {a}?',
    'off_label_drugs': 'Which drugs are used off-label for {a}?',
    'drugs_with_side_effect': 'Which drugs can cause {a} as a side effect?',
    'diseases_for': 'Which diseases have {a} as a symptom?',
    'targeting_drugs': 'Which drugs target {a}?',
    'associated_diseases': 'Which diseases are linked to {a}?',
    'describe': 'What is {a}? (a general description)',
}
DESCRIBE = 'describe'
# Set on development questions only (b1, b2, v2 dev); see docs/decisions.md D108.
ANSWER_AT = 0.85      # the best question is answered, with a note and the others offered
PASS_AT = 0.5         # "something else" this likely: the planner answers, as before
OFFER = 3             # questions offered when the reading is spread
MAX_OPTIONS = 9       # one digit per option

PROMPT = ('A user asked a question about a medical entity. Which of the listed questions is the '
          'user asking? Choose the one that the user wants answered. If the user asks something '
          'that none of them covers, answer 0. Reply with the number only.')


@dataclass
class Reading:
    mode: str                                      # 'answer', 'ask' or 'pass'
    ranked: list = field(default_factory=list)     # (intent, candidate, probability), best first
    other: float = 0.0                             # probability of "something else"

    def offered(self, limit: int = OFFER) -> list[dict]:
        return [{'intent': intent, 'uid': c.uid, 'question': phrase(intent, c), 'probability': round(p, 3)}
                for intent, c, p in self.ranked[:limit]]


def written(candidate) -> str:
    """The user's own name for the entity when it was matched exactly ("Lynparza"), so that
    asking an offered question links the same entity; else the catalog name."""
    return candidate.mention if candidate.method == 'exact' and candidate.mention else candidate.name


def phrase(intent: str, candidate) -> str:
    return QUESTIONS[intent].format(a=written(candidate))


def options(group: list) -> list[tuple[str, object]]:
    """The template questions about one mention, for each of its readings (a Disease and
    a Phenotype called "gout" have different questions), then a general description,
    which the planner and the text search answer."""
    listed = [(intent, c) for c in group for intent, spec in SPECS.items() if spec[0] == c.label]
    return listed[:MAX_OPTIONS - 1] + [(DESCRIBE, group[0])]


def read(llm, question: str, group: list, allowed=None) -> Reading | None:
    """The model's reading of an unrouted question about one mention; None when the model
    gives no probabilities (a fixture, or an endpoint without log-probabilities). An option
    that `allowed` rejects (the safety triage would block it) is never answered or offered;
    its probability counts as "something else"."""
    choose = getattr(llm, 'choose', None)
    listed = options(group)
    if choose is None or not listed:
        return None
    lines = '\n'.join(f'{i}. {phrase(intent, c)}' for i, (intent, c) in enumerate(listed, 1))
    try:
        scores = choose([{'role': 'system', 'content': PROMPT},
                         {'role': 'user', 'content': f'Question: {question}\nOptions:\n{lines}\n0. something else'}],
                        len(listed))
    except Exception:
        return None
    if not scores:
        return None
    # A description is answered as before, like a question none of the options covers.
    usable = {k for k in scores if k and listed[k - 1][0] != DESCRIBE
              and (allowed is None or allowed(phrase(*listed[k - 1])))}
    ranked = sorted(((*listed[k - 1], scores[k]) for k in usable), key=lambda r: -r[2])
    other = sum(p for k, p in scores.items() if k not in usable)
    if ranked and ranked[0][2] >= ANSWER_AT:
        mode = 'answer'
    elif other >= PASS_AT or not ranked:
        mode = 'pass'
    else:
        mode = 'ask'
    return Reading(mode, ranked, other)


def note(reading: Reading) -> str:
    intent, c, _ = reading.ranked[0]
    return f'Note: answered as "{phrase(intent, c)}".'


def clarification(reading: Reading) -> str:
    name = written(reading.ranked[0][1])
    lines = '\n'.join(f'- {o["question"]}' for o in reading.offered())
    return f'Please specify what you would like to know about {name}:\n{lines}'
