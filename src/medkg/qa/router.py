import re
from dataclasses import replace

from medkg.qa.linker import Candidate, label_choices, normalize
from medkg.retrieval.templates import SPECS

DRUG_WORDS = r'\b(?:drugs?|medications?|medicines?)\b'
TARGET_WORDS = (('Drug', r'drugs?|medications?|medicines?'),
                ('Disease', r'diseases?|conditions?|disorders?'),
                ('Phenotype', r'symptoms?|phenotypes?|features?|signs?|side'),
                ('Gene', r'genes?|proteins?'))


def requested_target(question: str) -> str | None:
    """Label of the entity type the question asks for ("Which diseases ...")."""
    match = re.search(r'\b(?:which|what)\b((?:\s+\w+){1,4})', question, re.I)
    for word in (match[1].split() if match else []):
        for label, pattern in TARGET_WORDS:
            if re.fullmatch(pattern, word, re.I):
                return label
    return None


def route(question: str, candidates: list[Candidate], previous: str | None = None) -> str | None:
    """Deterministic template intent, resolving same-name Disease/Phenotype readings."""
    if not candidates:
        return None
    choices = label_choices(candidates)
    if choices is None or len(choices)>1:
        return None
    if not choices:
        return _route(question,candidates,previous)
    group = choices[0]
    others = [c for c in candidates if c not in group]
    options = {}
    for chosen in group:
        intent = _route(question,[*others,replace(chosen,ambiguous=False)],previous)
        if intent:
            options.setdefault(intent,chosen.label)
    if len(options)>1:
        target = requested_target(question)
        options = {intent:label for intent,label in options.items() if SPECS[intent][1]==target}
    return next(iter(options)) if len(options)==1 else None


def _route(question: str, candidates: list[Candidate], previous: str | None = None) -> str | None:
    if not candidates or any(c.ambiguous for c in candidates):
        return None
    labels = {c.label for c in candidates}
    tokens = re.findall(r'\w+',question)
    masked = set()
    # Match intent against the question with anchor names removed. An entity name
    # containing "drug" or "gene" is not itself a requested relation.
    for candidate in sorted(candidates,key=lambda c:len(c.mention or c.name),reverse=True):
        if candidate.span and normalize(' '.join(tokens[slice(*candidate.span)]))==normalize(
                candidate.mention or candidate.name):
            start,end = candidate.span
            tokens[start:end] = ['']*(end-start)
            masked.add(candidate.uid)
    q = ' '.join(tokens)
    for candidate in candidates:
        if candidate.uid not in masked:
            q = re.sub(r'(?<!\w)'+re.escape(candidate.name)+r'(?!\w)',' ',q,flags=re.I)
    q = normalize(q)
    if re.search(r'\b(both|shared|common|and also|but not|that target|through|explain|why|warning|summary|according to|compare)\b', q):
        return None
    # A single-hop template cannot preserve two requested relation families.
    # Entity-type words alone are not relations ("drugs for a disease" is simple).
    families = (
        r'interact', r'side effect|adverse effect|phenotype|symptom|feature',
        r'contraindicat|should.*avoid|must.*avoid', r'target|protein|gene',
        r'(?<!contra)indicat|used for|treat',
    )
    if sum(bool(re.search(pattern,q)) for pattern in families)>1:
        return None
    # Reverse side-effect lookup: one phenotype anchor, drugs requested.
    if (labels=={'Phenotype'} and len(candidates)==1 and re.search(DRUG_WORDS,q)
            and re.search(r'side effect|adverse (?:effect|reaction)|\bcause',q)):
        return 'drugs_with_side_effect'
    if re.search(r'side effect|adverse effect|phenotype|symptom|feature',q) and re.search(r'\bdrugs?|medications?|medicines?\b',q):
        return None
    if re.search(r'\b(?:genes?|proteins?)\b',q) and re.search(
            r'\b(?:drugs?|medications?|medicines?|diseases?|conditions?)\b',q):
        return None
    if len(labels)>1:
        return None
    if previous in SPECS and re.match(r'\s*what about\b', q):
        return previous if SPECS[previous][0] in labels else None
    # Multiple explicit anchors may express an intersection or comparison. Only
    # the pairwise interaction question has an unambiguous template meaning.
    if len(candidates)>1 and not ('Drug' in labels and re.search('interact',q)):
        return None
    if 'Drug' in labels:
        for pattern, intent in [('interact','interactions'), ('side effect|adverse effect','side_effects'),
            ('contraindicat|should.*avoid|must.*avoid','contraindications'),
            ('off label','off_label'),
            ('target|protein|gene','targets'), ('indicat|used for|treat|condition|disease','indications')]:
            if re.search(pattern,q):
                return intent
    if 'Disease' in labels:
        if re.search(r'\b(?:subtype|subclass|parent|supertype|children)\b',q):
            if re.search(r'\b(?:parent|supertype)\b',q):
                return 'parents'
            original_words = re.findall(r'\w+',question.casefold())
            marker = next((i for i,w in enumerate(original_words[:-1]) if
                w in ('subtype','subtypes','subclass','subclasses') and original_words[i+1]=='of'),None)
            if marker is not None and candidates[0].span and candidates[0].span[0]>marker:
                return 'subtypes'
            return 'subtypes' if re.search(r'\b(?:subtypes|subclasses|children)\b',question,re.I) else 'parents'
        for pattern, intent in [('contraindicat|drug.*avoid|medication.*avoid','contraindicated_drugs'),
            ('off label','off_label_drugs'),
            ('drug|medication|medicine|treatment','drugs_for'), ('gene|protein','genes'),
            ('phenotype|symptom|feature','phenotypes')]:
            if re.search(pattern,q):
                return intent
    if 'Phenotype' in labels and re.search(r'disease|condition',q):
        return 'diseases_for'
    if 'Gene' in labels:
        if re.search(r'drug|medication|medicine',q):
            return 'targeting_drugs'
        if re.search(r'disease|condition',q):
            return 'associated_diseases'
    return None


def is_count(question: str) -> bool:
    return bool(re.search(r'\b(how many|count|number of)\b',question,re.I))
