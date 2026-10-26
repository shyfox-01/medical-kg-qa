import re
from dataclasses import replace

from medkg.qa.linker import Candidate, label_choices, normalize
from medkg.retrieval.templates import SPECS

DRUG_WORDS = r'\b(?:drugs?|medications?|medicines?)\b'
# Contraindication wording, including "when should it not be used" (D088).
CONTRA = (r'contraindicat|should.*avoid|must.*avoid|\b(?:should|must)\b.*\bnot be used\b|\bnot to be used\b|'
          # Negated use is never an indication question ("must not be given", D092).
          r'\bnot be (?:used|given|taken)\b|\bmust not\b|\bunsafe\b|\bshould not (?:be )?(?:used|given|taken)\b')
# Relation wordings, matched on the normalized question (plural "s" stripped; D092).
SIDE = r'side effect|adverse (?:effect|reaction|event)|unwanted effect|undesirable effect'
INTERACT = r'interact|\bcombin(?:e|ed|ing) with\b|\btaken together\b'
# "Can I take A with B?" asks about an interaction only when both A and B are drugs (D104).
PAIR_TAKE = r'\b(?:take|taking|use|using|mix|mixing)\b[^.?!\n]{0,40}\b(?:with|together|alongside|along with)\b'
TARGET = r'target|protein|gene|\bact(?:s)? on\b|\bmolecular\b|\bbind(?:s|ing)?\b'
PARENT = r'\b(?:parent|supertype|belong(?:s)? to|categor\w*|broader|classified (?:as|under))\b'
SUBTYPE = r'\b(?:subtype|subclass\w*|children|a (?:form|type|kind) of|(?:specific |different )?form of)\b'
# Explicit relation cues that settle a same-name Disease/Phenotype tie.
EXPLICIT = {'subtypes': SUBTYPE, 'parents': PARENT, 'genes': r'\bgenes?\b', 'targets': TARGET}
SHARED = r'\b(?:both|in common|share|shared|common)\b'
TARGET_WORDS = (('Drug', r'drugs?|medications?|medicines?'),
                ('Disease', r'diseases?|conditions?|disorders?'),
                ('Phenotype', r'symptoms?|phenotypes?|features?|signs?|side'),
                ('Gene', r'genes?|proteins?'))


# Yes/no questions about one drug and one disease or phenotype (D112): "Is X used to
# treat Y?", "Is X contraindicated in Y?", "Can X cause Y?". The relation word decides.
YES_NO = r'\s*(?:is|are|does|do|can|could|will|would|may|might|has|have|should)\b(?!\s+there\b)'
PAIRS = {
    frozenset({'Drug', 'Disease'}): [(CONTRA, 'contraindications'), (r'off label', 'off_label'),
                                     (r'(?<!contra)indicat|used (?:to treat|for|in)|\btreat\w*|\bhelp\w*',
                                      'indications')],
    frozenset({'Drug', 'Phenotype'}): [(SIDE+r'|\bcaus\w*|\btrigger\w*|\binduc\w*', 'side_effects')],
}


# Not a check of one pair: a negation, a comparison, other drugs, a second name or clause.
PAIR_EXCLUDE = (r'\b(?:not|no|never|longer|best|better|worse|worst|safer|safest|more|less|most|least|than|'
                r'instead|compared|versus|vs|any|other|others|besides|anything|else|only|and|or|but)\b')


def pair_intent(question: str, q: str, candidates: list[Candidate]) -> str | None:
    """The relation asked about between a drug and a disease or phenotype, for one yes/no question."""
    labels = frozenset(c.label for c in candidates)
    if len(candidates) != 2 or len(labels) != 2 or labels not in PAIRS or not re.match(YES_NO, question, re.I):
        return None
    # One question only ("Is X used to treat Y? Is it safe?" asks two), and one pair.
    if re.search(r'[.?!;]\s+\S', question.strip()) or re.search(PAIR_EXCLUDE, q):
        return None
    found = [intent for pattern, intent in PAIRS[labels] if re.search(pattern, q)]
    return found[0] if len(found) == 1 else None


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
    if len(options)>1:
        q = normalize(question)
        explicit = {i for i in options if i in EXPLICIT and re.search(EXPLICIT[i],q)}
        options = {i:options[i] for i in explicit} if len(explicit)==1 else options
    return next(iter(options)) if len(options)==1 else None


def _without_anchors(question: str, candidates: list[Candidate]) -> str:
    """The question with anchor names removed. An entity name containing "drug",
    "gene" or "common" (common cold) is not itself a requested relation or cue."""
    tokens = re.findall(r'\w+',question)
    masked = set()
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
    return normalize(q)


def wants_shared(question: str, anchors: list[Candidate]) -> bool:
    """Two anchors of one label plus an intersection cue ("both", "in common")."""
    return (len(anchors)==2 and len({c.label for c in anchors})==1
            and bool(re.search(SHARED, _without_anchors(question, anchors))))


def _route(question: str, candidates: list[Candidate], previous: str | None = None) -> str | None:
    if not candidates or any(c.ambiguous for c in candidates):
        return None
    labels = {c.label for c in candidates}
    q = _without_anchors(question, candidates)
    interact = INTERACT+('|'+PAIR_TAKE if labels=={'Drug'} and len(candidates)==2 else '')
    shared = bool(re.search(SHARED, q))
    if shared and not (len(candidates)==2 and len(labels)==1):
        return None
    if re.search(r'\b(and also|but not|that target|through|explain|why|warning|summary|according to|compare)\b', q):
        return None
    # A single-hop template cannot preserve two requested relation families.
    # Entity-type words alone are not relations ("drugs for a disease" is simple).
    families = (
        interact, SIDE+r'|phenotype|symptom|feature',
        CONTRA, TARGET,
        r'(?<!contra)indicat|used for|treat',
    )
    if sum(bool(re.search(pattern,q)) for pattern in families)>1:
        return None
    # Reverse side-effect lookup: one phenotype anchor, drugs requested.
    if (labels=={'Phenotype'} and len(candidates)==1 and re.search(DRUG_WORDS,q)
            and re.search(SIDE+r'|\bcause|\btrigger|\binduc',q)):
        return 'drugs_with_side_effect'
    if re.search(SIDE+r'|phenotype|symptom|feature',q) and re.search(r'\bdrugs?|medications?|medicines?\b',q):
        return None
    if re.search(r'\b(?:genes?|proteins?)\b',q) and re.search(
            r'\b(?:drugs?|medications?|medicines?|diseases?|conditions?)\b',q):
        return None
    if len(labels)>1:
        return pair_intent(question, q, candidates)
    if previous in SPECS and re.match(r'\s*what about\b', q):
        return previous if SPECS[previous][0] in labels else None
    # Multiple explicit anchors may express an intersection or comparison. Only a
    # two-anchor intersection ("both", "in common") or the pairwise interaction
    # question has an unambiguous template meaning; the pipeline sets shared=True.
    # Interactions between two drugs, or among up to six (every pair is checked, D113).
    if len(candidates)>1 and not shared and not ('Drug' in labels and len(candidates)<=6 and re.search(interact,q)):
        return None
    if 'Drug' in labels:
        for pattern, intent in [(interact,'interactions'), (SIDE,'side_effects'),
            (CONTRA,'contraindications'),
            ('off label','off_label'),
            # "What is X prescribed for?"; not "how is X prescribed" (D113).
            (TARGET,'targets'), (r'indicat|used for|treat|condition|disease|prescri\w* for','indications')]:
            if re.search(pattern,q):
                return intent
    if 'Disease' in labels:
        # "Which drugs cause X?" asks about adverse effects, never treatments; no
        # Drug->Disease causation template exists (D088).
        if re.search(DRUG_WORDS,q) and re.search(r'\b(?:caus|induc|trigger)\w*\b',q):
            return None
        if (re.search(SUBTYPE,q) or re.search(PARENT,q)) and not re.search(DRUG_WORDS,q):
            if re.search(PARENT,q):
                return 'parents'
            # "subtypes of X" / "diseases that are a form of X" ask for subtypes; "X is
            # a form of what?" asks for the parent. The marker's position decides.
            original_words = re.findall(r'\w+',question.casefold())
            marker = next((i for i,w in enumerate(original_words[:-1]) if
                w in ('subtype','subtypes','subclass','subclasses','form','forms','type','kind') and original_words[i+1]=='of'),None)
            if marker is not None and candidates[0].span:
                return 'subtypes' if candidates[0].span[0]>marker else 'parents'
            return 'subtypes' if re.search(r'\b(?:subtypes|subclasses|children)\b',question,re.I) else 'parents'
        for pattern, intent in [(CONTRA+'|drug.*avoid|medication.*avoid','contraindicated_drugs'),
            ('off label','off_label_drugs'),
            ('drug|medication|medicine|treatment|prescri|therap','drugs_for'), ('gene|protein','genes'),
            (r'phenotype|symptom|feature|\bpresent(?:s|ation)?\b|\bsign\b','phenotypes')]:
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


RELATION_CUES = (INTERACT, SIDE+r'|phenotype|symptom|feature', CONTRA, TARGET,
                 r'(?<!contra)indicat|used for|treat|therap|prescri', SUBTYPE, PARENT, DRUG_WORDS,
                 r'\b(?:genes?|proteins?|diseases?|conditions?)\b', r'off label', r'\bcaus|\btrigger|\binduc',
                 r'\b(?:and also|but not|through|compare|versus|vs)\b',
                 # Text questions the router leaves to the planner.
                 r'\b(?:warnings?|summary|explain|according to)\b')


def has_relation_cue(question: str, candidates: list[Candidate]) -> bool:
    """Any relation or entity-type word besides the anchors. An unrouted question with
    one is a compound or unsupported relation and goes to the planner; only a question
    without one ("What is the purpose of X?") is read by the model (D108)."""
    q = _without_anchors(question, candidates)
    return any(re.search(pattern, q) for pattern in RELATION_CUES)


def is_count(question: str, candidates: list[Candidate] | None = None) -> bool:
    """A count question; anchor names are removed first ("low platelet count" is a phenotype)."""
    text = _without_anchors(question, candidates) if candidates else question
    return bool(re.search(r'\b(how many|count|number of)\b',text,re.I))
