"""Predeclared, bounded real-provider comparison; no protected answers in summaries."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from eval.run import choose
from eval.score import VERSION

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def charged() -> int:
    ledger = ROOT/'eval/runs/usage_log.jsonl'
    rows = [json.loads(line) for line in ledger.read_text(encoding='utf8').splitlines()] if ledger.exists() else []
    balances = {r['call_id']:r.get('charged_tokens',r.get('reserved_tokens',0)) for r in rows}
    return sum(balances.values())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--plan',default='eval/runs/followup_plan_summary.json')
    args = parser.parse_args()
    plan_path = Path(args.plan)
    if args.prepare:
        if plan_path.exists():
            parser.error('Experiment plans are immutable')
        dataset = ROOT/'eval/datasets/structured_v1.jsonl'
        cases = choose([json.loads(line) for line in dataset.read_text(encoding='utf8').splitlines()],'test',1)
        ids = ROOT/'.cache/followup-2026-10-06/test-ids.json'
        ids.parent.mkdir(parents=True,exist_ok=True)
        ids.write_text(json.dumps([c['id'] for c in cases]),encoding='utf8')
        files = [dataset,ROOT/'data/processed/entities.json',ROOT/'data/processed/vector_progress.json',
                 *sorted(ROOT.glob('src/medkg/**/*.py')),ROOT/'eval/score.py',ROOT/'eval/run.py',ROOT/'eval/client.py']
        plan = {'measurement_kind':'bounded_real_provider_comparison','evaluator_version':VERSION,
            'cases':len(cases),'total_test_cases':240,'category_counts':dict(Counter(c['category'] for c in cases)),
            'case_ids_file':str(ids.relative_to(ROOT)),'rounds':3,'cache_enabled':False,
            'maximum_additional_charged_tokens':3000000,'maximum_wall_seconds':5400,
            'charged_tokens_before':charged(),
            'hashes':{str(p.relative_to(ROOT)):digest(p) for p in files},
            'systems':[
                {'label':'phase1_control','phase':1,'mode':'hybrid','output':'eval/runs/followup_phase1_control_summary.json'},
                {'label':'hybrid','phase':3,'mode':'hybrid','output':'eval/runs/followup_hybrid_summary.json'},
                {'label':'vector','phase':3,'mode':'vector','output':'eval/runs/followup_vector_summary.json'}],
            'interpretation':'Current-code/current-graph phase-1 ablation, not a rerun of historical v0; '
                'all safety/adversarial test cases plus one fixed case per remaining category. '
                'Small retrieval-category samples do not establish general accuracy.'}
        plan_path.write_text(json.dumps(plan,indent=2),encoding='utf8')
        print(json.dumps({'prepared':str(plan_path),'cases_per_system':len(cases),'rounds':3}))
        return
    plan = json.loads(plan_path.read_text(encoding='utf8'))
    if any(digest(ROOT/path)!=expected for path,expected in plan['hashes'].items()):
        raise SystemExit('Frozen code/data changed; do not continue this comparison')
    os.environ['TOKEN_BUDGET'] = str(min(15000000,plan['charged_tokens_before']+
        plan['maximum_additional_charged_tokens']))
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    started = time.monotonic()
    statuses = []
    for system in plan['systems']:
        output = ROOT/system['output']
        if output.exists():
            statuses.append({'system':system['label'],'status':'completed_existing'})
            continue
        remaining = plan['maximum_wall_seconds']-(time.monotonic()-started)
        if remaining<=0 or charged()>=int(os.environ['TOKEN_BUDGET']):
            statuses.append({'system':system['label'],'status':'budget_deferred'})
            break
        command = [sys.executable,'-m','eval.run','--split','test','--rounds',str(plan['rounds']),
            '--phase',str(system['phase']),'--mode',system['mode'],'--case-ids',plan['case_ids_file'],
            '--output',system['output']]
        checkpoint = output.with_name(output.stem.replace('_summary','')+'_checkpoint.json')
        if checkpoint.exists():
            command.append('--resume')
        print(json.dumps({'starting_system':system['label']}),flush=True)
        process = subprocess.Popen(command,cwd=ROOT)
        try:
            code = process.wait(timeout=remaining)
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
        if code:
            break
    measured = {'systems':statuses,'charged_tokens_after':charged(),
        'additional_charged_tokens':charged()-plan['charged_tokens_before'],
        'wall_seconds':time.monotonic()-started,'complete':len(statuses)==len(plan['systems']) and
            all(r['status'].startswith('completed') for r in statuses)}
    for system in plan['systems']:
        output = ROOT/system['output']
        if output.exists():
            summary = json.loads(output.read_text(encoding='utf8'))
            measured[system['label']] = {k:summary[k] for k in ('evaluated_questions',
                'pass_rate_mean','quality_pass_rate_mean','pass_rate_rounds','quality_pass_rate_rounds')}
    (ROOT/'eval/runs/followup_experiment_summary.json').write_text(json.dumps(measured,indent=2),encoding='utf8')
    print(json.dumps(measured,indent=2),flush=True)


if __name__=='__main__':
    main()
