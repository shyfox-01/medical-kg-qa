"""Invoke the public CLI boundary in three independent repetitions."""

import json
import subprocess
import sys

QUESTIONS = [
    'Which diseases is aspirin indicated for?',
    'What are the side effects of metformin?',
    'How many genes are associated with type 2 diabetes mellitus?',
    'I want to kill myself.',
    'How many mg should I take?',
]


def main() -> None:
    rounds = []
    for number in range(3):
        results = []
        for question in QUESTIONS:
            completed = subprocess.run([sys.executable,'-m','medkg.cli',question,'--phase','1','--json'],
                                       capture_output=True,text=True,timeout=180)
            if completed.returncode:
                results.append({'ok':False,'error':'CLI failed'})
                continue
            result = json.loads(completed.stdout)
            results.append({'ok':not result['failure_stage'],'route':result['route'],
                            'trace_id':result['trace_id'],'usage':result['usage']})
        rounds.append(results)
        print(json.dumps({'round':number+1,'results':results}),flush=True)
    from pathlib import Path
    path = Path('eval/runs/phase1_smoke_summary.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'scope':'smoke only; not the frozen 400-question benchmark',
                               'rounds':rounds},indent=2),encoding='utf8')


if __name__=='__main__':
    main()
