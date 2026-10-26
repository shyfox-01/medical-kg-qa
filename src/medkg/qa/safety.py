"""Deterministic safety gates precede every LLM and retrieval call."""

import re
from dataclasses import dataclass

RESOURCES = {
    'US': ('988', '911'),
    'UK': ('Samaritans 116 123', '999'),
    'SG': ('Samaritans of Singapore 1767', '995'),
}
QUANTITY = (r'(?:\d+(?:[.,]\d+)?|(?:one|two|three|four|five|six|seven|eight|nine|ten|'
            r'eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|'
            r'twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)'
            r'(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?(?: and a half)?|'
            r'(?:half|quarter)(?: (?:of )?an?)?)')
# A non-word lookahead also bounds units ending in punctuation, such as "i.u.".
DOSE_AMOUNT = (r'\b'+QUANTITY+r'\s*(?:mg|mcg|micrograms?|milligrams?|grams?|ml|'
               r'milliliters?|tablets?|capsules?|pills?|drops?|'
               r'iu|ius|i\.u\.|international units?|units?)(?!\w)')
# A bare article is a quantity only inside an instruction ("take a tablet"), not in
# descriptions such as "a drop in blood pressure" or "supplied as a tablet".
DOSE_ARTICLE = (r'\b(?:take|use|swallow|give|administer|inject)\s+(?:an?|one)\s+'
                r'(?:tablets?|capsules?|pills?|drops?|injections?|doses?)\b')
DOSE_SCHEDULE = (r'\b(?:take|use|inject|swallow|administer|apply)\b[^\n.!?]{0,120}'
                 r'\b(?:daily|nightly|at bedtime|once a day|twice a day|three times a day|'
                 r'(?:once|twice|thrice) (?:daily|weekly)|'
                 +QUANTITY+r'\s+times?\s+(?:(?:a|per|each)\s+)?(?:day|week|month)|'
                 r'(?:every|each)\s+(?:morning|afternoon|evening|night|day|week)|'
                 r'every (?:\d+|one|two|four|six|eight|twelve) hours?)\b')
# Which strengths a product comes in, an infusion rate or a bare "X mg?" asks for a dose
# (D111). Found missing on the human-labelled MedicationQA dose questions; written from
# separate examples.
STRENGTH = r'(?:mgs?|milligrams?|strengths?(?!\s+(?:training|exercises?|of evidence))|dosages?|doses?)'
DOSE_PRODUCT = (r'\b(?:what|which|different|available)\s+'+STRENGTH+r'\b|'
                r'\b'+STRENGTH+r'\b[^.?!\n]{0,40}\b(?:comes? in|available|are there)\b|'
                r'\bsize doses?\b|'
                r'\b(?:daily|recommended|right|correct|safe|usual)\s+amount\b|'
                r'\b(?:infusion|injection|administration)\s+rate\b|\brate of (?:infusion|injection|administration)\b|'
                r'(?-i:\b(?:mg|mgs|milligrams?)\s*\?)')
# "How many people take X" counts people, not doses.
NOT_A_DOSE_COUNT = (r'(?!\s+(?:people|patients|persons|users|americans|adults|women|men|children|kids|babies|'
                    r'deaths|cases|times|types|kinds)\b)')
# How much is needed, how many a day, how often a booster is due: a dose request only
# when a medicine is named ("How much sleep do adults need?" is not one), never about cost.
DOSE_AMOUNT_ASK = (r'\bhow much\b[^.?!\n]{0,60}\b(?:need|needs|needed|required|recommended|should|a day|per|daily|'
                   r'a week|at once|at a time|to treat|is (?:ok|okay|safe)|too much|'
                   r'for (?:an? |my |the )?(?:adults?|child|children|kids?|bab(?:y|ies)|infants?|toddlers?|'
                   r'teen(?:ager)?s?|\d+[- ](?:years?|months?)[- ]old))\b|'
                   r'\bhow many\b'+NOT_A_DOSE_COUNT+r'[^.?!\n]{0,40}\b(?:a|per|each|in)\s+'
                   r'(?:day|24 hours|week|night|dose|serving)\b|'
                   r'\bhow many\s+(?:mgs?|milligrams?|grams?|tablets?|pills?|capsules?|puffs?|drops?|units?)\b|'
                   r'\b(?:what|which)\s+amount\b|'
                   r'\bamount of\b[^.?!\n]{0,40}\b(?:to take|to use|to give|should|needed)\b|'
                   r'\bhow (?:often|frequently)\b[^.?!\n]{0,60}\b(?:need|needed|due|repeated|boosters?)\b|'
                   r'\b(?:max|maximum|min|minimum)\b[^.?!\n]{0,40}\b(?:per|a|each)\s+(?:day|dose|week)\b')
MEDICINE_WORDS = (r'\b(?:drugs?|medicines?|medications?|meds|pills?|tablets?|capsules?|doses?|dosages?|shots?|'
                  r'vaccines?|boosters?|injections?|supplements?|vitamins?|antibiotics?|puffs?|drops?|inhalers?|'
                  r'syrups?|powders?|creams?|ointments?|patch(?:es)?)\b')
COST = r'\b(?:cost|costs|price|prices|pay|paying|insurance|afford|spend)\b'


def amount_ask(text: str, medicine: bool = False) -> bool:
    """How much, how many or how often of a medicine (D111). `medicine` says that the
    question names a drug; a medicine word ("tablets", "booster") also counts."""
    return bool((medicine or re.search(MEDICINE_WORDS, text, re.I)) and not re.search(COST, text, re.I)
                and re.search(DOSE_AMOUNT_ASK, text, re.I))


# Entity names alone ("chest pain", "heart attack", "suicidal ideation", "ectopic
# pregnancy") are ordinary knowledge-graph questions. Emergency and crisis rules
# need a personal or situational cue; population rules need a medication context.
PERSONAL = (r"\b(?:i|i'm|im|i've|i'd|me|my|myself|we|we're|our|us|he|she|he's|she's|his|her|"
            r"him|someone|somebody)\b")
SITUATION = r"\b(?:there is|there's|right now|now|currently|happening)\b"
CRISIS_EXPLICIT = (r"\b(?:kill(?:ing)? myself|end(?:ing)? my life|take my own life|"
                   r"(?:hurt|harm)(?:ing)? myself|want to die|wanna die|overdose myself|"
                   r"commit(?:ting)? suicide|suicide (?:method|plan|note)s?|"
                   r"how (?:to|do i|can i) (?:die|kill)|lethal (?:dose|amount))\b")
CRISIS_TERM = r'\b(?:suicid\w*|self[- ]?harm\w*)'
EMERGENCY_TERM = (r"\b(?:chest pain|cannot breathe|can't breathe|can not breathe|trouble breathing|"
                  r"(?:is|was|isn't|is not|not|stopped|stop) breathing|collapsed|passed out|fainted|"
                  r"stroke symptoms|severe bleeding|bleeding heavily|unconscious|unresponsive|"
                  r"heart attack|having a seizure|overdosed)\b")
POPULATION = (r'\b(?:pregnant|(?:during|in|while in|throughout) pregnancy|breast-?feed\w*|'
              r'nursing (?:mother|baby|infant)s?|infants?|newborns?|bab(?:y|ies)|child|children|'
              r'kids?|toddlers?|elderly|older adults?|seniors?|'
              r'\d+[- ](?:years?|months?|weeks?)[- ]old)\b')
MEDICATION_CONTEXT = (r'\b(?:safe|safely|safety|take|taking|use|using|used|give|giving|drugs?|medicines?|'
                      r'medications?|meds|treatments?|treat|therapy|recommend\w*|prescri\w*|'
                      r'dose|dosage)\b')


ADVICE = (r'\b(?:should|can|could|may|safe|safely|safety|recommend\w*|prescri\w*|'
          r'take|taking|give|giving|use|using|administer\w*|start|stop|suitable|best|'
          r'choose|pick|select|advi\w*|ought|would|help)\b')


def population_advice(question: str) -> bool:
    """Exempt explicit impersonal graph lookups, never personal medication advice."""
    if not (re.search(POPULATION, question, re.I) and
            re.search(MEDICATION_CONTEXT, question, re.I)):
        return False
    lookup = (r'^\s*(?:which|what|how many|list|show)\b[\s\S]*'
              r'\b(?:recorded|listed|associated|linked|indicated|contraindicated|'
              r'side effects?|interactions?|targets?)\b')
    return bool(re.search(PERSONAL+'|'+ADVICE, question, re.I) or
                not re.search(lookup, question, re.I))


RULES = {
    'crisis': lambda q: bool(re.search(CRISIS_EXPLICIT,q,re.I) or (
        re.search(CRISIS_TERM,q,re.I) and re.search(PERSONAL,q,re.I))),
    'emergency': lambda q: bool(re.search(EMERGENCY_TERM,q,re.I) and (
        re.search(PERSONAL,q,re.I) or re.search(SITUATION,q,re.I))),
    'dosage': lambda q: bool(re.search(
        r'\b(dosage|dose|how (much|many)'+NOT_A_DOSE_COUNT+r'.*(take|mg|tablets)|milligrams|dosing)\b|'
        +DOSE_PRODUCT+'|'
        # Frequency and duration of use are dosing questions too (D092).
        r'\bhow (?:often|frequently|long)\b[^.?!]{0,60}\b(?:take|taken|use|used|give|given|inject\w*)\b|'
        +DOSE_AMOUNT+'|'+DOSE_ARTICLE+'|'+DOSE_SCHEDULE,q,re.I)),
    'special_population': population_advice,
    'diagnosis_request': lambda q: bool(re.search(
        r'\b(diagnos\w* me|what (disease|illness) do i have|do i have|am i suffering|'
        r'tell me my diagnosis)\b',q,re.I)),
}
# "If you have hypertension" or "you have asked" are not diagnoses.
OUTPUT_DIAGNOSIS = (r'(?<!\bif )(?<!\bwhen )(?<!\bwhether )(?<!\bunless )(?<!\bdo )'
                    r'\byou (?:have|are suffering from)\b'
                    r'(?!\s+(?:asked|requested|mentioned|provided|listed|selected|to)\b)|'
                    r'\byou (?:have been|are) diagnosed with\b|\byour diagnosis is\b|'
                    r'\bi diagnose you with\b')


@dataclass
class Assessment:
    category: str = 'none'
    message: str = ''
    blocked: bool = False


def messages(region: str = 'US') -> dict[str, str]:
    hotline, emergency = RESOURCES.get(region, RESOURCES['US'])
    return {
        'crisis': f'If you may harm yourself, contact {hotline} now. If there is immediate danger, call {emergency}. Reach out to someone you trust and avoid being alone.',
        'emergency': f'These symptoms may need urgent care. Call {emergency} or seek emergency medical care now.',
        'dosage': 'I cannot recommend a medication dose. Ask a clinician or pharmacist about your prescription.',
        'special_population': 'Medication safety for this population needs individual professional assessment. Consult a clinician or pharmacist.',
        'diagnosis_request': 'I cannot diagnose you. A clinician must assess your symptoms and medical history.',
        'medication_decision': 'Starting, stopping, switching or combining your medicines needs individual '
                               'advice. Ask your clinician or pharmacist.',
    }


def assess(question: str, region: str = 'US') -> Assessment:
    """Whole-question gate: the first matching rule blocks the question."""
    text = messages(region)
    question = question.replace('’', "'")
    for category, matches in RULES.items():
        if matches(question):
            return Assessment(category, text[category], True)
    return Assessment()


# --- Partial answers (D103) ---------------------------------------------------
# A question that only mentions a dose, or asks for a dose in one sentence and for
# knowledge in another, is answered from the graph with a fixed notice; the dose is
# never given (the answer model is told so and output_violation still blocks any
# dose or diagnosis in the answer). Crisis, emergency, diagnosis requests, personal
# population advice and questions that are only a dose request stay blocked.
NOTICES = {
    'dosage': 'Note: dosing and decisions about your own medicines need a clinician or pharmacist; '
              'this answer covers only what the knowledge graph records.',
    'special_population': 'Note: these records are general, not specific to this population; '
                          'ask a clinician or pharmacist whether they apply.',
    'medication_decision': 'Note: whether to take or combine your medicines is a decision for your '
                           'clinician or pharmacist; this answer covers only what the knowledge graph records.',
}
# "Can I take A with B?" also asks whether A and B interact, which the graph records.
COMBINE_ASK = re.compile(r'\b(?:take|taking|use|using|mix|mixing|combine|combining)\b[^.?!]{1,60}'
                         r'\b(?:with|together with|alongside|along with|and)\b', re.I)
CAUTION = ('The question also touches dosing or care for a particular person or population: '
           'report only what the evidence records, and never state doses, dosing schedules, '
           'diagnoses or personal recommendations.')
_ANY_AMOUNT = DOSE_AMOUNT+r'|\b(?:high|higher|large|larger|low|lower|this|that|such an?(?: high| low)?|my|his|her|the|a)\s+doses?\b'
DOSE_REQUEST = re.compile(
    # How much or how many to take or give, and how often or how long.
    r'\bhow (?:much|many)\b'+NOT_A_DOSE_COUNT+r'[^.?!]{0,60}\b(?:take|taken|taking|give|given|use|used|mg|'
    r'tablets?|pills?|capsules?|units?|iu|doses?)\b|'
    r'\bhow (?:often|frequently|long)\b[^.?!]{0,60}\b(?:take|taken|taking|use|used|give|given|inject\w*)\b|'
    r'\bwhen (?:should|do|can|must) (?:i|we|he|she|they|you)\b[^.?!]{0,20}\b(?:take|give|use)\b|'
    # Which dose: "the correct dosage", "maximum daily dose", "dosage of X", "what dose".
    r'\b(?:correct|right|proper|recommended|usual|normal|standard|typical|maximum|max|minimum|min|safe|'
    r'daily|starting|initial|maintenance)\s+(?:daily\s+)?(?:dose|doses|dosage|dosing|amount)\b|'
    # "What is the dosage of X" asks for a dose; "high doses of X cause Y" only mentions one.
    r'\bwhat\b[^.?!]{0,30}\b(?:dose|dosage|dosing)\b|'
    # Whether an amount is safe: "is 50,000 IU safe", "such a high dose safe", "safe to take 20 mg".
    r'(?:'+_ANY_AMOUNT+r')[^.?!]{0,60}\b(?:safe|safely|too (?:much|high|many)|ok|okay|enough|dangerous|'
    r'fine|toxic|overdose)\b|'
    r'\b(?:safe|ok|okay)\b[^.?!]{0,40}\b(?:to take|taking|to give|giving)\b[^.?!]{0,40}(?:'+_ANY_AMOUNT+r')|'
    # Whether to take an amount or change a dose.
    r'\b(?:can|should|may|could|must)\s+(?:i|we|he|she|they|you|my \w+)\s+(?:take|give|use|have)\b[^.?!]{0,40}'
    r'(?:'+DOSE_AMOUNT+'|'+DOSE_SCHEDULE+r')|'
    r'\b(?:increase|decrease|double|reduce|lower|raise|skip|split|cut|halve|stop)\s+(?:my|the|his|her|their|a|this)\s+'
    r'(?:dose|doses|dosage|tablets?|pills?)\b', re.I)
# A sentence naming a dose ("Recommend a dosage.", "Give me a drug dose.") asks for one,
# unless it asks about something else: "high doses of X cause Y", "low dose X used for Y".
DOSE_WORD = re.compile(r'\b(?:dose|doses|dosage|dosages|dosing)\b', re.I)
OTHER_ASK = re.compile(r'\b(?:cause[sd]?|causing|side effects?|adverse|interact\w*|together|combin\w*|'
                       r'mix\w*|contain\w*|gluten|ingredients?|used (?:to|for|in)|treat\w*|indicated|'
                       r'reactions?)\b', re.I)
# Whether someone should take, stop, switch or taper their medicine is a personal decision;
# the output guard catches doses and diagnoses but not "it is safe for you", so such a
# question that mentions a dose stays blocked.
_DECIDE = r'(?:take|taking|use|using|stop|stopping|start|starting|switch\w*|continue|quit|give|giving|try|keep)'
PERSONAL_DECISION = re.compile(
    # The person deciding is the asker or someone they care for: "should I stop", "can my son use".
    r"\b(?:should|can|could|may|must|shall)\s+(?:i|we|my\s+\w+|he|she|they)\s+(?:\w+\s+){0,2}?"+_DECIDE+r"\b|"
    r"\bis\s+(?:it|this|that)\s+(?:ok|okay|safe|alright|fine)\s+(?:for\s+(?:me|us|him|her|them|my\s+\w+)\s+)?"
    r"to\s+"+_DECIDE+r"\b|"
    r"\b(?:ok|okay|safe|alright)\s+for\s+(?:me|us|him|her|them|my\s+\w+)\s+to\s+"+_DECIDE+r"\b|"
    r"\bwhat\s+(?:i|we)\s+(?:can|should)\s+(?:take|use|try|get)\b|"
    r"\bwhat\s+(?:can|should)\s+(?:i|we)\s+(?:take|use|try|get)\b|"
    # Present-tense requests only: "I stopped taking X last week" narrates, it does not ask.
    r"\b(?:wean|weaning|taper|tapering|stop taking|come off|coming off|get off)\b", re.I)
QUESTION_START = re.compile(r'^\s*(?:what|which|who|whom|whose|how|why|when|where|is|are|was|were|can|could|'
                            r'does|do|did|should|will|would|may|might|has|have|any)\b', re.I)


@dataclass
class Triage:
    mode: str = 'none'          # 'none', 'caveat' (answer with a notice) or 'block'
    category: str = 'none'
    message: str = ''           # the block message; also the reply when a caveat answer is empty
    notice: str = ''            # prefixed to a caveat answer
    question: str = ''          # text the pipeline answers (dose-request sentences removed)


def sentences(question: str) -> list[str]:
    """Sentences and lines: the unit in which a dose request is removed."""
    parts = re.split(r'(?<=[.?!])\s+|\n+|\.{2,}\s*', question)
    return [part.strip() for part in parts if part and part.strip()]


def dose_request(sentence: str, medicine: bool = False) -> bool:
    # A sentence that only names doses or strengths may ask something else ("side effects
    # of different doses of X"); an amount of a medicine is always a request (D111).
    return bool(DOSE_REQUEST.search(sentence) or amount_ask(sentence, medicine) or
                ((DOSE_WORD.search(sentence) or re.search(DOSE_PRODUCT, sentence, re.I))
                 and not OTHER_ASK.search(sentence)))


def is_question(text: str) -> bool:
    return '?' in text or bool(QUESTION_START.search(text))


def triage(question: str, region: str = 'US', drug_named: bool = False) -> Triage:
    """Block, answer with a notice, or pass: the policy of D103. `drug_named` says that the
    question names a drug (the pipeline checks exact catalog names first), which makes
    "how much X a day" a dose request (D111)."""
    text = messages(region)
    question = question.replace('’', "'")
    for category in ('crisis', 'emergency', 'diagnosis_request'):
        if RULES[category](question):
            return Triage('block', category, text[category], question=question)
    # Population advice is blocked when it is personal, asks what to do, or names no
    # condition ("Medicines for a newborn?"). An impersonal lookup about a condition in a
    # population ("treatments for children with X", "drugs that treat X in children") is
    # answered with a notice.
    population = population_advice(question)
    if population and (re.search(PERSONAL+'|'+ADVICE, question, re.I) or not re.search(
            POPULATION+r'\s+(?:with|who (?:have|has)|having|diagnosed with|suffering from)\b|'
            r'\btreat\w*\b[^.?!]{1,60}\b(?:in|for|among)\s+(?:\w+\s+)?'+POPULATION, question, re.I)):
        return Triage('block', 'special_population', text['special_population'], question=question)
    answer_text, categories = question, (['special_population'] if population else [])
    medicine = drug_named or bool(re.search(MEDICINE_WORDS, question, re.I))
    if RULES['dosage'](question) or amount_ask(question, medicine):
        parts = sentences(question)
        rest = [part for part in parts if not dose_request(part, medicine)]
        if len(rest) < len(parts):
            residual = ' '.join(rest)
            if len(re.findall(r'[A-Za-z]+', residual)) < 3 or not is_question(residual):
                return Triage('block', 'dosage', text['dosage'], question=question)
            answer_text = residual
        if re.search(PERSONAL, answer_text, re.I) and PERSONAL_DECISION.search(answer_text):
            return Triage('block', 'dosage', text['dosage'], question=question)
        categories.insert(0, 'dosage')
    elif re.search(PERSONAL, question, re.I) and PERSONAL_DECISION.search(question):
        # A personal decision without a dose (D104): "Can I take A with B?" is answered as
        # an interaction question behind a notice; "Should I stop taking X?" is blocked.
        if not COMBINE_ASK.search(question):
            return Triage('block', 'medication_decision', text['medication_decision'], question=question)
        categories.insert(0, 'medication_decision')
    if not categories:
        return Triage(question=question)
    return Triage('caveat', categories[0], text[categories[0]],
                  '\n'.join(NOTICES[c] for c in categories), answer_text)


# Function words of the questions' language. Entity names (Sjögren, de Quervain) carry
# diacritics or isolated foreign words, so a question counts as foreign only when such
# words outnumber the English ones (D092).
ENGLISH_WORDS = frozenset('the what which who is are of for with does do can could should how many '
                          'much in to and a an used use treat drugs drug side effects symptoms genes '
                          'there any recorded associated interact'.split())
FOREIGN_WORDS = frozenset('qué que para se usa usan cuáles cuales son es los las el la del efectos '
                          'secundarios sirve tratar medicamentos quels quelles sont les des de du est '
                          'une pour effets secondaires médicaments traiter wofür wofur wird werden '
                          'verwendet was ist welche die der das und für nebenwirkungen medikamente '
                          'quais são servem os um uma'.split())


def english(question: str) -> bool:
    foreign = r'\b(cu[aá]les|qu[eé] medicamentos|quel(?:s|les)? m[eé]dicaments|quels sont|welche medikamente|was ist|quais medicamentos)\b'
    if not re.search('[A-Za-z]', question) or re.search(
            r'[\u0400-\u052f\u0600-\u06ff\u0900-\u097f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af¿¡]', question):
        return False
    words = re.findall(r'[^\W\d_]+', question.casefold())
    native, other = sum(w in ENGLISH_WORDS for w in words), sum(w in FOREIGN_WORDS for w in words)
    return not re.search(foreign,question,re.I) and not (other >= 2 and other > native)


def output_violation(text: str) -> Assessment | None:
    """Conservative final guard; this is not a clinical safety classifier."""
    if re.search(DOSE_AMOUNT+'|'+DOSE_ARTICLE+'|'+DOSE_SCHEDULE,text,re.I):
        return Assessment('dosage','I cannot provide medication doses. Consult a clinician or pharmacist.',True)
    if re.search(OUTPUT_DIAGNOSIS,text,re.I):
        return Assessment('diagnosis_request','I cannot diagnose you. A clinician must assess your symptoms and medical history.',True)
    return None
