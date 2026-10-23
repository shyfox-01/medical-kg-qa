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
MEDICATION_CONTEXT = (r'\b(?:safe|safely|safety|take|taking|use|using|give|giving|drugs?|medicines?|'
                      r'medications?|meds|treatments?|treat|therapy|recommend\w*|prescri\w*|'
                      r'dose|dosage)\b')


def population_advice(question: str) -> bool:
    """Exempt explicit impersonal graph lookups, never personal medication advice."""
    if not (re.search(POPULATION, question, re.I) and
            re.search(MEDICATION_CONTEXT, question, re.I)):
        return False
    advice = (r'\b(?:should|can|could|may|safe|safely|safety|recommend\w*|prescri\w*|'
              r'take|taking|give|giving|use|using|administer\w*|start|stop|suitable|best|'
              r'choose|pick|select|advi\w*|ought|would|help)\b')
    lookup = (r'^\s*(?:which|what|how many|list|show)\b[\s\S]*'
              r'\b(?:recorded|listed|associated|linked|indicated|contraindicated|'
              r'side effects?|interactions?|targets?)\b')
    return bool(re.search(PERSONAL+'|'+advice, question, re.I) or
                not re.search(lookup, question, re.I))


RULES = {
    'crisis': lambda q: bool(re.search(CRISIS_EXPLICIT,q,re.I) or (
        re.search(CRISIS_TERM,q,re.I) and re.search(PERSONAL,q,re.I))),
    'emergency': lambda q: bool(re.search(EMERGENCY_TERM,q,re.I) and (
        re.search(PERSONAL,q,re.I) or re.search(SITUATION,q,re.I))),
    'dosage': lambda q: bool(re.search(
        r'\b(dosage|dose|how (much|many).*(take|mg|tablets)|milligrams|dosing)\b|'
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


def assess(question: str, region: str = 'US') -> Assessment:
    hotline, emergency = RESOURCES.get(region, RESOURCES['US'])
    messages = {
        'crisis': f'If you may harm yourself, contact {hotline} now. If there is immediate danger, call {emergency}. Reach out to someone you trust and avoid being alone.',
        'emergency': f'These symptoms may need urgent care. Call {emergency} or seek emergency medical care now.',
        'dosage': 'I cannot recommend a medication dose. Ask a clinician or pharmacist about your prescription.',
        'special_population': 'Medication safety for this population needs individual professional assessment. Consult a clinician or pharmacist.',
        'diagnosis_request': 'I cannot diagnose you. A clinician must assess your symptoms and medical history.',
    }
    question = question.replace('’', "'")
    for category, matches in RULES.items():
        if matches(question):
            return Assessment(category, messages[category], True)
    return Assessment()


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
