"""Stage-wise diagnosis of a completed run: where did each failing question first fail?

End-to-end pass rates say how often the answer is right, not why it is wrong. The
v2 dataset carries gold for each stage, so a recorded run can be scored per stage
without new model calls:

- linking: every gold anchor uid is among the linked candidates;
- routing: the template intent equals the gold intent (questions that have one);
- retrieval: the evidence given to the answer model contains the gold entities
  (all of them when the scorer requires full recall, otherwise at least one; for
  counts, a row with the gold count or the full gold set);
- generation: the evidence was sufficient but the scored answer still failed.

Each failing question is attributed to generation when its evidence sufficed, and
otherwise to the first of linking, routing and retrieval that failed (recorded
exceptions come first). Given a baseline run of the same questions, the per-question ledger
(fixed / still failing / regressed) is printed with those stages. Diagnostic only:
it reuses the scorer's entity extraction and is not clinical validation.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from eval.score import Vocabulary, score

REFUSAL_KINDS = {'refusal', 'safety'}
REFUSED = re.compile(r'\b(?:no (?:evidence|information|supporting|drugs|medications|genes|shared|symptoms|results)'
                     r'|there (?:are|is) no|not (?:found|available|listed|present)|does not (?:contain|include|list)'
                     r'|cannot (?:answer|determine|identify))\b', re.I)


def _evidence(record: dict, vocabulary: Vocabulary) -> tuple[set[str], set[int]]:
    contexts = record['result'].get('contexts', [])
    uids = vocabulary.extract(json.dumps(contexts)) | {r['uid'] for r in contexts if r.get('uid')}
    counts = {r['count'] for r in contexts if isinstance(r.get('count'), int)}
    return uids, counts


def verdict(case: dict, record: dict, vocabulary: Vocabulary) -> dict:
    """Per-stage outcome and the first failing stage for one recorded question."""
    result, score = record['result'], record['score']
    out = {'id': case['id'], 'category': case['category'], 'passed': score['passed']}
    if case['kind'] in REFUSAL_KINDS:
        out.update(stage=None if score['passed'] else 'refusal_policy')
        return out
    candidates = {c['uid'] for c in result.get('candidates', []) if c.get('uid')}
    gold_anchors = set(case.get('anchor_uids', []))
    expected = set(case.get('expected', []))
    evidence, counts = _evidence(record, vocabulary)
    out['linking_ok'] = gold_anchors <= candidates
    out['routing_ok'] = result.get('intent') == case['intent'] if case.get('intent') else None
    if case['kind'] == 'count':
        out['retrieval_ok'] = case['expected_count'] in counts or bool(expected) and expected <= evidence
    elif case.get('recall_applicable', True):
        out['retrieval_ok'] = bool(expected) and expected <= evidence
    else:
        out['retrieval_ok'] = bool(expected & evidence)
    out['context_recall'] = len(expected & evidence) / len(expected) if expected else None
    out['execution_exact'] = record.get('execution_exact')
    if score['passed']:
        out['stage'] = None
    elif result.get('failure_stage'):
        out['stage'] = 'error:' + result['failure_stage']
    elif out['retrieval_ok']:
        # Sufficient evidence: an earlier miss (e.g. a linking gap the planner
        # worked around) did not cause this failure.
        out['stage'] = 'generation:' + _generation_reason(case, record)
    elif not out['linking_ok']:
        out['stage'] = 'linking'
    elif out['routing_ok'] is False:
        out['stage'] = 'routing'
    else:
        out['stage'] = 'retrieval:' + (result.get('route') or 'none')
    return out


def _generation_reason(case: dict, record: dict) -> str:
    result, score = record['result'], record['score']
    body = (result.get('answer') or '').split('\n\nSources:')[0]
    if result.get('response_status') == 'unsupported' or result.get('refused') or REFUSED.search(body):
        return 'denied_evidence'
    if case['kind'] == 'count':
        return 'wrong_count'
    if score.get('precision') is not None and score['precision'] < 1:
        return 'extra_entities'
    if score.get('recall') is not None and score['recall'] < 1:
        return 'incomplete'
    return 'other'


def summarize(verdicts: list[dict]) -> dict:
    answerable = [v for v in verdicts if 'linking_ok' in v]
    routed = [v for v in answerable if v['routing_ok'] is not None]
    retrieved = [v for v in answerable if v['retrieval_ok']]
    executed = [v['execution_exact'] for v in answerable if v.get('execution_exact') is not None]

    def rate(values):
        return round(sum(values) / len(values), 4) if values else None
    return {
        'questions': len(verdicts), 'passed': sum(v['passed'] for v in verdicts),
        'first_failing_stage': dict(Counter(v['stage'] for v in verdicts if v['stage']).most_common()),
        'linking_accuracy': rate([v['linking_ok'] for v in answerable]),
        'routing_accuracy': rate([v['routing_ok'] for v in routed]), 'routing_questions': len(routed),
        'retrieval_sufficient': rate([v['retrieval_ok'] for v in answerable]),
        'generation_accuracy_given_sufficient_evidence': rate([v['passed'] for v in retrieved]),
        'execution_accuracy': rate(executed), 'execution_questions': len(executed),
        'refusal_accuracy': rate([v['passed'] for v in verdicts if 'linking_ok' not in v]),
    }


def ledger(before: dict[str, dict], after: dict[str, dict]) -> dict[str, list[tuple[str, str | None, str | None]]]:
    """Per question: fixed, still failing or regressed, with first failing stage before -> after."""
    groups = {'fixed': [], 'still_failing': [], 'regressed': []}
    for key in sorted(after.keys() & before.keys()):
        b, a = before[key], after[key]
        if not b['passed'] and a['passed']:
            groups['fixed'].append((key, b['stage'], None))
        elif not b['passed'] and not a['passed']:
            groups['still_failing'].append((key, b['stage'], a['stage']))
        elif b['passed'] and not a['passed']:
            groups['regressed'].append((key, None, a['stage']))
    return groups


def load(dataset: Path, run: Path, vocabulary: Vocabulary, rescore: bool = False) -> dict[str, dict]:
    cases = {c['id']: c for c in (json.loads(line) for line in dataset.read_text(encoding='utf8').splitlines())}
    records = [json.loads(line) for line in run.read_text(encoding='utf8').splitlines()]
    if rescore:
        # Saved outputs scored by the current evaluator version (no model calls).
        for r in records:
            executed = [s for t in r.get('turns', []) for s in t['result'].get('executed_statements',
                        t['result'].get('cypher', []))]
            r['score'] = score(cases[r['id']], {**r['result'], 'failure_stage': r.get('failure_stage'),
                                               **({'executed_statements': executed} if executed else {})}, vocabulary)
    return {r['id']: verdict(cases[r['id']], r, vocabulary) for r in records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('run', help='Round records (*_round1.jsonl) of a completed run')
    parser.add_argument('--baseline', help='Round records of an earlier run of the same questions')
    parser.add_argument('--dataset', default='eval/datasets/structured_v2.jsonl')
    parser.add_argument('--vocabulary', default='data/processed/entities.json')
    parser.add_argument('--output', help='Write per-question verdicts and the summary as JSON')
    parser.add_argument('--rescore', action='store_true', help='Score saved outputs with the current evaluator')
    args = parser.parse_args()
    vocabulary = Vocabulary(json.loads(Path(args.vocabulary).read_text(encoding='utf8')))
    after = load(Path(args.dataset), Path(args.run), vocabulary, args.rescore)
    report = {'run': args.run, 'summary': summarize(list(after.values()))}
    print(json.dumps(report['summary'], indent=2))
    if args.baseline:
        before = load(Path(args.dataset), Path(args.baseline), vocabulary, args.rescore)
        report['baseline'] = args.baseline
        report['ledger'] = ledger(before, after)
        for name, rows in report['ledger'].items():
            print(f'\n{name} ({len(rows)})')
            for key, old, new in rows:
                print(f'  {key} [{after[key]["category"]}] {old or "pass"} -> {new or "pass"}')
    if args.output:
        report['verdicts'] = list(after.values())
        Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf8')


if __name__ == '__main__':
    main()
