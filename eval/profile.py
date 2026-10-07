"""Trace-id-scoped metadata profiling; no question or answer text in outputs."""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def summarize(values: list[float]) -> dict:
    ordered = sorted(values)
    return {'count':len(values),'total_seconds':sum(values),
            'median_seconds':statistics.median(values),
            'p90_seconds':ordered[max(0,int(len(ordered)*0.9)-1)]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--details',nargs='+',required=True)
    parser.add_argument('--output',default='eval/runs/followup_profile_summary.json')
    args = parser.parse_args()
    ids = set()
    for relative in args.details:
        for line in Path(relative).read_text(encoding='utf8').splitlines():
            record = json.loads(line)
            ids.add(record['trace_id'])
            ids.update(t['result']['trace_id'] for t in record.get('turns',[]))
    stages = defaultdict(list)
    matched = set()
    for file in (ROOT/'runs/traces').glob('*.jsonl'):
        for line in file.read_text(encoding='utf8').splitlines():
            span = json.loads(line)
            if span['trace_id'] in ids:
                stages[span['name']].append(span['seconds'])
                matched.add(span['trace_id'])
    measured = {'requested_traces':len(ids),'matched_traces':len(matched),
        'stages':{name:summarize(values) for name,values in sorted(stages.items())},
        'interpretation':'Nested span totals overlap. Medians are observed local/provider timings; '
            'no standalone capacity or concurrency claim is supported.'}
    Path(args.output).write_text(json.dumps(measured,indent=2),encoding='utf8')
    print(json.dumps(measured,indent=2))


if __name__=='__main__':
    main()
