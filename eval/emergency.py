"""The emergency second reading (D117) on a question set.

On eval/datasets/emergency_dev_v1.jsonl (Claude-written, labelled) it reports caught and
missed emergencies; on any other set it lists the questions it would escalate, which are
false alarms unless a reviewer finds an emergency among them.

    python -m eval.emergency --dataset eval/datasets/emergency_dev_v1.jsonl
    python -m eval.emergency --dataset eval/datasets/liveqa_v2.jsonl --output eval/runs/d117_liveqa.json
"""

import argparse
import json
import time
from pathlib import Path

from medkg.config import Settings
from medkg.llm import LLMClient
from medkg.qa import safety


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    llm = LLMClient(Settings())
    rows = []
    for line in Path(args.dataset).read_text(encoding='utf8').splitlines():
        case = json.loads(line)
        question = case['question']
        rules = safety.triage(question).category
        start = time.perf_counter()
        urgent = None if rules in ('crisis', 'emergency') else safety.emergency_reading(llm, question)
        rows.append({'id': case['id'], 'question': question, 'rules': rules, 'reading': urgent,
                     'seconds': round(time.perf_counter()-start, 3), 'label': case.get('emergency'),
                     'escalated': urgent is not None and urgent >= safety.ESCALATE_AT})
    read = [r for r in rows if r['reading'] is not None]
    report = {'dataset': args.dataset, 'escalate_at': safety.ESCALATE_AT, 'questions': len(rows),
              'read': len(read), 'escalated': sum(r['escalated'] for r in rows),
              'rule_emergencies': sum(r['rules'] in ('crisis', 'emergency') for r in rows),
              'median_seconds': sorted(r['seconds'] for r in read)[len(read)//2] if read else None}
    if any(r['label'] is not None for r in rows):
        caught = lambda r: r['rules'] in ('crisis', 'emergency') or r['escalated']  # noqa: E731
        report['emergencies_caught'] = sum(caught(r) for r in rows if r['label'])
        report['emergencies'] = sum(1 for r in rows if r['label'])
        report['false_alarms'] = sum(caught(r) for r in rows if r['label'] is False)
        report['non_emergencies'] = sum(1 for r in rows if r['label'] is False)
    print(json.dumps(report, indent=1))
    for r in sorted(read, key=lambda r: -r['reading']):
        if r['escalated'] or r['label']:
            print(f"{r['reading']:.3f} {'ESC' if r['escalated'] else '   '} label={r['label']} {r['id']}: {r['question'][:110]}")
    if args.output:
        with args.output.open('x', encoding='utf8') as stream:
            json.dump({**report, 'rows': rows}, stream, indent=1)


if __name__ == '__main__':
    main()
