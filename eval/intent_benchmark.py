"""Intent benchmark on human-labelled consumer questions (D110).

Runs the deterministic stages of the pipeline (safety triage, language and scope
gates, linking with the D105 review, the D106 phrase check, the D093 ambiguity check,
the router) and the D108 reading, without retrieval or answer generation, and records
what the system would do with each MedicationQA question:

  blocked / language / scope        a gate answers
  clarify                           a name is asked back
  rule:<intent>                     the router's template
  read:<intent>                     a D108 reading answered from a template
  ask                               a D108 reading asked back (offered intents kept)
  planner                           the LLM planner (no template)

The rules-only outcome (before D108) is the same with every D108 reading treated as
"planner". Metrics were fixed before the first run: for questions whose type maps to
a template intent, the share answered with that intent, answered with another one
(the harmful case) and asked with it offered; for the other questions, the share
answered from any template. Usage: python -m eval.intent_benchmark --output PATH.
"""

import argparse
import collections
import json
import time
from pathlib import Path

import numpy as np

from medkg.config import ROOT, Settings
from medkg.embeddings import Embeddings
from medkg.llm import LLMClient
from medkg.qa import confirm, intent, safety, scope
from medkg.qa.linker import Linker, label_choices
from medkg.qa.router import has_relation_cue, is_count, route

DATASET = ROOT / 'eval/datasets/medicationqa_v1.jsonl'


def outcome(linker, llm, region, question: str) -> dict:
    triage = safety.triage(question, region)
    if triage.mode == 'block':
        return {'outcome': 'blocked', 'safety': triage.category}
    if not safety.english(question):
        return {'outcome': 'language'}
    if scope.blocked(question):
        return {'outcome': 'scope'}
    asked = triage.question if triage.mode == 'caveat' else question
    candidates, unresolved = linker.question_mentions(asked)
    if linker.quarantined_mentions(unresolved):
        return {'outcome': 'clarify', 'why': 'quarantine'}
    checked = confirm.review(linker, candidates, unresolved)
    if not checked.suggestions:
        checked = confirm.check_phrases(linker, asked, checked, confirm.model_judge(llm), typed=question)
    if checked.suggestions:
        return {'outcome': 'clarify', 'why': 'name'}
    candidates, unresolved = checked.kept, checked.unresolved
    base = {'caveat': triage.mode == 'caveat', 'uids': sorted(c.uid for c in candidates)}
    if candidates and label_choices(candidates) is None:
        return {**base, 'outcome': 'clarify', 'why': 'ambiguous'}
    chosen = None if unresolved else route(asked, candidates, None)
    if chosen:
        return {**base, 'outcome': 'rule', 'intent': chosen}
    if (not unresolved and candidates and len({c.span for c in candidates}) == 1 and not is_count(asked)
            and not has_relation_cue(asked, candidates)):
        started = time.perf_counter()
        reading = intent.read(llm, asked, candidates, allowed=lambda q: safety.triage(q, region).mode != 'block')
        seconds = round(time.perf_counter() - started, 3)
        if reading and reading.mode == 'answer':
            return {**base, 'outcome': 'read', 'intent': reading.ranked[0][0], 'seconds': seconds,
                    'probability': round(reading.ranked[0][2], 3)}
        if reading and reading.mode == 'ask':
            return {**base, 'outcome': 'ask', 'offered': [o['intent'] for o in reading.offered()],
                    'seconds': seconds}
        if reading:
            return {**base, 'outcome': 'planner', 'read': 'pass', 'seconds': seconds}
    return {**base, 'outcome': 'planner'}


def summarise(rows: list[dict]) -> dict:
    def tally(group, rules_only):
        counts = collections.Counter()
        for r in group:
            o = r['outcome']
            if rules_only and o in ('read', 'ask'):
                o = 'planner'
            if o in ('rule', 'read'):
                counts['right_intent' if r['intent'] == r['gold'] else
                       ('template_for_unmapped' if r['gold'] is None else 'wrong_intent')] += 1
            elif o == 'ask':
                counts['asked_with_right_option' if r['gold'] in r['offered'] else 'asked_without_it'] += 1
            else:
                counts[o] += 1
        return dict(sorted(counts.items()))
    mapped = [r for r in rows if r['gold']]
    unmapped = [r for r in rows if not r['gold']]
    dose = [r for r in rows if 'Dose' in r['question_types']]
    return {
        'questions': len(rows), 'mapped': len(mapped), 'unmapped': len(unmapped),
        'mapped_rules_only': tally(mapped, True), 'mapped_with_d108': tally(mapped, False),
        'mapped_by_intent_with_d108': {g: tally([r for r in mapped if r['gold'] == g], False)
                                       for g in sorted({r['gold'] for r in mapped})},
        'unmapped_rules_only': tally(unmapped, True), 'unmapped_with_d108': tally(unmapped, False),
        'dose_questions': len(dose),
        'dose_outcomes': dict(collections.Counter(
            'blocked' if r['outcome'] == 'blocked' else ('caveat' if r.get('caveat') else r['outcome'])
            for r in dose)),
        'reading_seconds_median': float(np.median([r['seconds'] for r in rows if 'seconds' in r] or [0])),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='eval/runs/medicationqa_intent_summary.json')
    args = parser.parse_args()
    settings = Settings()
    processed = ROOT / 'data/processed'
    linker = Linker(json.loads((processed / 'entities.json').read_text(encoding='utf8')), Embeddings(),
                    np.load(processed / 'alias_vectors.npy', mmap_mode='r'),
                    json.loads((processed / 'vector_aliases.json').read_text(encoding='utf8')))
    llm = LLMClient(settings)
    rows = []
    output = Path(args.output)
    with output.with_name(output.stem.replace('_summary', '') + '_rows.jsonl').open('w', encoding='utf8') as stream:
        for line in DATASET.read_text(encoding='utf8').splitlines():
            case = json.loads(line)
            row = {'id': case['id'], 'gold': case['intent'], 'question_types': case['question_types'],
                   'focus': case['focus'], **outcome(linker, llm, settings.safety_region, case['question'])}
            rows.append(row)
            stream.write(json.dumps(row) + '\n')
    summary = {'dataset': str(DATASET.relative_to(ROOT)), 'model': settings.llm_model, **summarise(rows)}
    output.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
