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
            r'(?:half|quarter)(?: (?:of )?an?)?|an?)')
DOSE_AMOUNT = (r'\b'+QUANTITY+r'\s*(?:mg|mcg|micrograms?|milligrams?|grams?|ml|'
               r'milliliters?|tablets?|capsules?|pills?|drops?)\b')
DOSE_SCHEDULE = (r'\b(?:take|use|inject|swallow|administer|apply)\b[^\n.!?]{0,120}'
                 r'\b(?:daily|nightly|at bedtime|once a day|twice a day|three times a day|'
                 r'(?:once|twice|thrice) (?:daily|weekly)|'
                 +QUANTITY+r'\s+times?\s+(?:(?:a|per|each)\s+)?(?:day|week|month)|'
                 r'(?:every|each)\s+(?:morning|afternoon|evening|night|day|week)|'
                 r'every (?:\d+|one|two|four|six|eight|twelve) hours?)\b')
RULES = {
    'crisis': r'\b(kill myself|suicid\w*|end my life|hurt myself|self.harm|want to die|overdose myself)\b',
    'emergency': r'\b(chest pain|cannot breathe|can.t breathe|stroke symptoms|severe bleeding|unconscious|heart attack)\b',
    'dosage': (r'\b(dosage|dose|how (much|many).*(take|mg|tablets)|milligrams|dosing)\b|'
               +DOSE_AMOUNT+'|'+DOSE_SCHEDULE),
    'special_population': r'\b(pregnan\w*|breastfeed\w*|infant|newborn|child|children|elderly)\b',
    'diagnosis_request': r'\b(diagnos\w* me|what (disease|illness) do i have|do i have|am i suffering|tell me my diagnosis)\b',
}


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
    for category, pattern in RULES.items():
        if re.search(pattern, question, re.I):
            return Assessment(category, messages[category], True)
    return Assessment()


def english(question: str) -> bool:
    foreign = r'\b(cu[aá]les|qu[eé] medicamentos|quel(?:s|les)? m[eé]dicaments|quels sont|welche medikamente|was ist|quais medicamentos)\b'
    return bool(re.search('[A-Za-z]', question)) and not re.search(
        r'[\u0400-\u052f\u0600-\u06ff\u0900-\u097f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', question
    ) and not re.search(foreign,question,re.I)


def output_violation(text: str) -> Assessment | None:
    """Conservative final guard; this is not a clinical safety classifier."""
    if re.search(DOSE_AMOUNT+'|'+DOSE_SCHEDULE,text,re.I):
        return Assessment('dosage','I cannot provide medication doses. Consult a clinician or pharmacist.',True)
    if re.search(r'\b(?:you (?:have|are suffering from)|your diagnosis is|i diagnose you with)\b',text,re.I):
        return Assessment('diagnosis_request','I cannot diagnose you. A clinician must assess your symptoms and medical history.',True)
    return None
