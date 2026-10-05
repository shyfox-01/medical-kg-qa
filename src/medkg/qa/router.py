import re

from medkg.qa.linker import Candidate
from medkg.retrieval.templates import SPECS


def route(question: str, candidates: list[Candidate], previous: str | None = None) -> str | None:
    if not candidates or any(c.ambiguous for c in candidates):
        return None
    labels, q = {c.label for c in candidates}, question.casefold()
    if re.search(r'\b(both|shared|common|and also|but not|that target|through|explain|why|warning|summary|according to|compare)\b', q):
        return None
    if previous in SPECS and re.match(r'\s*what about\b', q):
        return previous
    if 'Drug' in labels:
        for pattern, intent in [('interact','interactions'), ('side effect|adverse effect','side_effects'),
            ('contraindicat|should.*avoid|must.*avoid','contraindications'),
            ('target|protein|gene','targets'), ('indicat|used for|treat|condition|disease','indications')]:
            if re.search(pattern,q):
                return intent
    if 'Disease' in labels:
        for pattern, intent in [('contraindicat|drug.*avoid|medication.*avoid','contraindicated_drugs'),
            ('drug|medication|medicine|treatment','drugs_for'), ('gene|protein','genes'),
            ('phenotype|symptom|feature','phenotypes')]:
            if re.search(pattern,q):
                return intent
    if 'Phenotype' in labels and re.search(r'disease|condition',q):
        return 'diseases_for'
    return None


def is_count(question: str) -> bool:
    return bool(re.search(r'\b(how many|count|number of)\b',question,re.I))
