"""Build the MedicationQA intent benchmark (D110) from the published spreadsheet.

MedicationQA (Ben Abacha et al., MEDINFO 2019; CC BY 4.0) holds real consumer
questions about medicines, each annotated by its authors with the drug in focus and a
question type. The type is used here as a human label of what the user asks. The
mapping from type to template intent was fixed before any system ran on the data;
every other type has no template, and the right behaviour is not to answer it from
one. All questions are test: none is used to set rules or thresholds.

Input: data/raw/medicationqa/MedInfo2019-QA-Medications.xlsx (not committed).
Output: eval/datasets/medicationqa_v1.jsonl (not committed) and MANIFEST_medicationqa.json.
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eval'))
import xlsx  # noqa: E402

SOURCE = ROOT / 'data/raw/medicationqa/MedInfo2019-QA-Medications.xlsx'
OUTPUT = ROOT / 'eval/datasets/medicationqa_v1.jsonl'
MANIFEST = ROOT / 'eval/datasets/MANIFEST_medicationqa.json'

# Fixed before the first run (D110). "Action" (how a medicine works) maps to targets,
# the nearest template; it is reported separately because the match is approximate.
TYPE_TO_INTENT = {
    'Indication': 'indications',
    'Side effects': 'side_effects',
    'Interaction': 'interactions',
    'Contraindication': 'contraindications',
    'Action': 'targets',
}


def build() -> dict:
    table = xlsx.rows(SOURCE)
    header, body = table[0], [r for r in table[1:] if r and r[0].strip()]
    column = {name: header.index(name) for name in ('Question', 'Focus (Drug)', 'Question Type')}
    cases: dict[str, dict] = {}
    for row in body:
        cell = lambda name: (row[column[name]] if column[name] < len(row) else '').strip()  # noqa: E731
        question = ' '.join(cell('Question').split())
        case = cases.setdefault(question.casefold(), {'question': question, 'focus': cell('Focus (Drug)'),
                                                       'types': []})
        if cell('Question Type') and cell('Question Type') not in case['types']:
            case['types'].append(cell('Question Type'))
    rows = []
    for number, case in enumerate(cases.values(), 1):
        intents = {TYPE_TO_INTENT.get(t) for t in case['types']}
        # A question with several types maps only when all of them map to one intent.
        intent = intents.pop() if len(intents) == 1 else None
        rows.append({'id': f'medqa-{number:04d}', 'split': 'test', 'question': case['question'],
                     'focus': case['focus'], 'question_types': case['types'], 'intent': intent})
    OUTPUT.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf8')
    data = SOURCE.read_bytes()
    manifest = {
        'source': 'https://github.com/abachaa/Medication_QA_MedInfo2019',
        'license': 'CC BY 4.0',
        'citation': ('Ben Abacha A, Mrabet Y, Sharp M, Goodwin T, Shooshan SE, Demner-Fushman D. Bridging '
                     "the Gap between Consumers' Medication Questions and Trusted Answers. MEDINFO 2019."),
        'source_sha256': hashlib.sha256(data).hexdigest(),
        'spreadsheet_rows': len(body),
        'questions': len(rows),
        'mapped': sum(r['intent'] is not None for r in rows),
        'by_intent': {i: sum(r['intent'] == i for r in rows) for i in TYPE_TO_INTENT.values()},
        'type_to_intent': TYPE_TO_INTENT,
        'output_sha256': hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    return manifest


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
