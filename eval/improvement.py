"""Frozen full-test before/after comparison, external CLI only, bounded resources."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from eval.experiment import charged
from eval.run import redline_regressions
from eval.score import VERSION

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--plan',default='eval/runs/improvement_plan_summary.json')
    parser.add_argument('--before-source',default='.cache/improvement-2026-10-06/baseline-source')
    args = parser.parse_args()
    path = ROOT/args.plan
    state_path = path.with_name(path.stem.replace('_plan_summary','')+'_experiment_summary.json')
    if args.prepare:
        if path.exists():
            parser.error('Frozen plans cannot be overwritten')
        dataset = ROOT/'eval/datasets/structured_v1.jsonl'
        rows = [json.loads(line) for line in dataset.read_text(encoding='utf8').splitlines()]
        cases = [r for r in rows if r['split']=='test']
        if len(cases)!=240:
            parser.error('This comparison requires all 240 frozen test cases')
        before = ROOT/args.before_source
        if not (before/'medkg/qa/pipeline.py').is_file():
            parser.error('Before source snapshot is absent')
        ids = ROOT/'.cache/improvement-2026-10-06/full-test-ids.json'
        ids.write_text(json.dumps([c['id'] for c in cases]),encoding='utf8')
        files = [dataset,ids,ROOT/'data/processed/entities.json',ROOT/'data/processed/vector_progress.json',
            *sorted((ROOT/'src').rglob('*.py')),*sorted(before.rglob('*.py')),
            ROOT/'eval/run.py',ROOT/'eval/score.py',ROOT/'eval/client.py',ROOT/'eval/improvement.py']
        prepared = {'evaluator_version':VERSION,'cases':len(cases),'rounds':3,
            'category_counts':dict(Counter(c['category'] for c in cases)),'cache_enabled':False,
            'case_ids':str(ids.relative_to(ROOT)),'before_source':args.before_source,
            'maximum_additional_charged_tokens':10000000,'maximum_wall_seconds':14400,
            'charged_before':charged(),'hashes':{str(f.relative_to(ROOT)):digest(f) for f in files},
            'systems':[
                {'label':'after','phase':3,'mode':'hybrid'},
                {'label':'before','phase':3,'mode':'hybrid','source':args.before_source},
                {'label':'vector','phase':3,'mode':'vector'}],
            'interpretation':'Same repaired data, provider/model and evaluator. Before uses the exact '
                'pre-improvement phase-3 source, not historical v0. All 240 test IDs, including 38 '
                'previously reported pilot cases. No test-answer tuning during the frozen run.'}
        path.write_text(json.dumps(prepared,indent=2),encoding='utf8')
        print(json.dumps({'prepared':str(path),'cases':240,'rounds':3,'systems':3}),flush=True)
        return
    plan = json.loads(path.read_text(encoding='utf8'))
    if any(digest(ROOT/f)!=expected for f,expected in plan['hashes'].items()):
        raise SystemExit('Frozen source/data changed; do not continue this comparison')
    previous = json.loads(state_path.read_text(encoding='utf8')) if state_path.exists() else {}
    used_seconds = previous.get('wall_seconds',0)
    os.environ['TOKEN_BUDGET'] = str(min(15000000,plan['charged_before']+plan['maximum_additional_charged_tokens']))
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    started = time.monotonic()
    statuses = []
    def save():
        state = {'systems':statuses,'wall_seconds':used_seconds+time.monotonic()-started,
            'charged_after':charged(),'additional_charged_tokens':charged()-plan['charged_before'],
            'complete':len(statuses)==3 and all(s['status'].startswith('completed') for s in statuses)}
        measured = {}
        for system in plan['systems']:
            output = ROOT/f"eval/runs/improvement_{system['label']}_summary.json"
            if output.exists():
                summary = json.loads(output.read_text(encoding='utf8'))
                measured[system['label']] = summary
                state[system['label']] = {k:summary[k] for k in ('evaluated_questions','rounds',
                    'pass_rate_mean','pass_rate_std','quality_pass_rate_mean','failure_stages')}
        if 'before' in measured and 'after' in measured:
            state['after_redline_regressions'] = redline_regressions(measured['after'],measured['before'])
            state['after_redline_gate_passed'] = not state['after_redline_regressions']
        if 'before' in measured and 'vector' in measured:
            state['vector_redline_regressions'] = redline_regressions(measured['vector'],measured['before'])
        temporary = state_path.with_suffix('.pending')
        temporary.write_text(json.dumps(state,indent=2),encoding='utf8')
        temporary.replace(state_path)
        return state
    for system in plan['systems']:
        output = ROOT/f"eval/runs/improvement_{system['label']}_summary.json"
        if output.exists():
            summary = json.loads(output.read_text(encoding='utf8'))
            if summary['evaluated_questions']!=240 or summary['rounds']!=3 or summary['evaluator_version']!=plan['evaluator_version']:
                raise SystemExit('Existing summary does not match the full comparison')
            statuses.append({'system':system['label'],'status':'completed_existing'})
            continue
        remaining = plan['maximum_wall_seconds']-used_seconds-(time.monotonic()-started)
        if remaining<=0 or charged()>=int(os.environ['TOKEN_BUDGET']):
            statuses.append({'system':system['label'],'status':'budget_deferred'})
            break
        command = [sys.executable,'-m','eval.run','--split','test','--rounds','3','--phase','3',
            '--mode',system['mode'],'--case-ids',plan['case_ids'],'--output',str(output)]
        if system.get('source'):
            command += ['--system-source',system['source']]
        if output.with_name(output.stem.replace('_summary','')+'_checkpoint.json').exists():
            command.append('--resume')
        print(json.dumps({'starting_system':system['label'],'cases_per_round':240}),flush=True)
        process = subprocess.Popen(command,cwd=ROOT)
        try:
            deadline = time.monotonic()+remaining
            while True:
                left = deadline-time.monotonic()
                if left<=0:
                    raise subprocess.TimeoutExpired(command,remaining)
                try:
                    code = process.wait(timeout=min(30,left))
                    break
                except subprocess.TimeoutExpired:
                    save()  # Preserve elapsed budget during long runs and resumptions.
        except subprocess.TimeoutExpired:
            if os.name=='nt' and process.poll() is None:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            else:
                process.terminate()
            process.wait(timeout=10)
            statuses.append({'system':system['label'],'status':'wall_budget_deferred'})
            break
        statuses.append({'system':system['label'],'status':'completed' if code==0 else 'failed','exit_code':code})
        save()
        if code:
            break
    final = save()
    print(json.dumps(final,indent=2),flush=True)
    if final.get('after_redline_gate_passed') is False:
        raise SystemExit(2)
    if not final['complete']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
