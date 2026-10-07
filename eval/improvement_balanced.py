"""Balance complete control coverage when the initial full plan is too slow."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from eval.experiment import charged
from eval.improvement import ROOT, digest
from eval.run import choose, redline_regressions, summarize
from eval.score import VERSION

PLAN = ROOT/'eval/runs/improvement_balanced_plan_summary.json'
STATE = ROOT/'eval/runs/improvement_balanced_experiment_summary.json'


def records(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]


def prepare():
    if PLAN.exists():
        raise SystemExit('Balanced plans are immutable')
    original = json.loads((ROOT/'eval/runs/improvement_plan_summary.json').read_text(encoding='utf8'))
    old_state = ROOT/'eval/runs/improvement_experiment_summary.json'
    prior = json.loads(old_state.read_text(encoding='utf8'))
    deadline = old_state.stat().st_mtime+original['maximum_wall_seconds']-prior['wall_seconds']
    if any(digest(ROOT/f)!=value for f,value in original['hashes'].items()):
        raise SystemExit('Original frozen inputs changed')
    rows = records(ROOT/'eval/datasets/structured_v1.jsonl')
    cases = {r['id']:r for r in rows if r['split']=='test'}
    detail = ROOT/'eval/runs/improvement_after_round1.jsonl'
    first = records(detail)
    checkpoint = json.loads((ROOT/'eval/runs/improvement_after_checkpoint.json').read_text(encoding='utf8'))
    if [r['id'] for r in first]!=checkpoint['case_ids'] or len(first)!=240 or checkpoint['evaluator_version']!=VERSION:
        raise SystemExit('A complete unchanged 240-case first round is required')
    selected = choose(rows,'test',5)
    if len(selected)!=70:
        raise SystemExit('Expected 70 stratified repeated cases')
    ids = ROOT/'.cache/improvement-2026-10-06/balanced-repeat-ids.json'
    ids.write_text(json.dumps([r['id'] for r in selected]),encoding='utf8')
    reused = ROOT/'eval/runs/improvement_full_after_round1.jsonl'
    if reused.exists():
        raise SystemExit('Reused details already exist')
    reused.write_bytes(detail.read_bytes())
    if digest(reused)!=digest(detail):
        raise SystemExit('Reused round verification failed')
    summary = summarize([first],[cases[r['id']] for r in first])
    summary.update(evaluator_version=VERSION,accounting='all_conversation_turns',
        dataset_sha256=checkpoint['dataset_sha256'],code_sha256=checkpoint['code_sha256'],
        vocabulary_sha256=checkpoint['vocabulary_sha256'],system='hybrid',phase=3,
        system_source='src',split='test',rounds=1,evaluated_questions=240,
        evaluated_ids=[r['id'] for r in first],total_available=240,cache_enabled=False,
        judge_status='uncalibrated',clinical_validation=False,
        measurement_kind='completed_real_provider_round_reused_without_rescoring',
        source_details=str(detail.relative_to(ROOT)))
    (ROOT/'eval/runs/improvement_full_after_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    hashes = {**original['hashes'],str(ids.relative_to(ROOT)):digest(ids),
              'eval/improvement_balanced.py':digest(Path(__file__).resolve())}
    plan = {'evaluator_version':VERSION,'hashes':hashes,'deadline_epoch':deadline,
        'charged_before':original['charged_before'],
        'token_ceiling':min(15000000,original['charged_before']+original['maximum_additional_charged_tokens']),
        'full_ids':original['case_ids'],'repeat_ids':str(ids.relative_to(ROOT)),
        'full_cases':240,'full_rounds':1,'repeat_cases':70,'repeat_rounds':3,
        'before_source':original['before_source'],'original_plan':'eval/runs/improvement_plan_summary.json',
        'reason':'Measured first-round latency projects the nine full rounds beyond the original '
            'four-hour ceiling. Follow the task timeout sampling instruction: preserve one full '
            'round per system and three rounds of 70 fixed cases, including every safety/adversarial case. '
            'Reuse the completed first round; make two additional subset rounds. No test-answer tuning.',
        'selection':'eval.run.choose(test, cap=5, seed=42), before observing subgroup outcomes'}
    PLAN.write_text(json.dumps(plan,indent=2),encoding='utf8')
    prior.update(complete=False,adapted_to=str(PLAN.relative_to(ROOT)),
        adaptation_reason=plan['reason'],preserved_partial_details=True)
    old_state.write_text(json.dumps(prior,indent=2),encoding='utf8')
    print(json.dumps({'full_cases':240,'full_rounds':1,'repeat_cases':70,'repeat_rounds':3,
                      'remaining_minutes':(deadline-time.time())/60}),flush=True)


def combine(label,selected):
    full_path = ROOT/f'eval/runs/improvement_full_{label}_summary.json'
    repeat_path = ROOT/f'eval/runs/improvement_repeat_{label}_summary.json'
    full = json.loads(full_path.read_text(encoding='utf8'))
    repeated = json.loads(repeat_path.read_text(encoding='utf8'))
    if any(full[k]!=repeated[k] for k in ('evaluator_version','dataset_sha256','vocabulary_sha256','code_sha256')):
        raise RuntimeError('Cannot combine rounds from different frozen inputs')
    first = {r['id']:r for r in records(full_path.with_name(full_path.stem.replace('_summary','')+'_round1.jsonl'))}
    rounds = [[first[c['id']] for c in selected]]
    rounds += [records(repeat_path.with_name(repeat_path.stem.replace('_summary','')+f'_round{i}.jsonl')) for i in (1,2)]
    if any([r['id'] for r in rows]!=[c['id'] for c in selected] for rows in rounds):
        raise RuntimeError('Repeated case identities changed')
    result = summarize(rounds,selected)
    result.update({k:full[k] for k in ('evaluator_version','dataset_sha256','vocabulary_sha256','code_sha256',
        'system','phase','system_source','split','total_available','cache_enabled','judge_status','clinical_validation')})
    result.update(rounds=3,evaluated_questions=70,evaluated_ids=[c['id'] for c in selected],
        accounting='all_conversation_turns',
        measurement_kind='one_full_real_round_subset_plus_two_additional_real_subset_rounds',
        source_summaries=[str(full_path.relative_to(ROOT)),str(repeat_path.relative_to(ROOT))])
    output = ROOT/f'eval/runs/improvement_balanced_{label}_summary.json'
    output.write_text(json.dumps(result,indent=2),encoding='utf8')


def run():
    plan = json.loads(PLAN.read_text(encoding='utf8'))
    if any(digest(ROOT/f)!=expected for f,expected in plan['hashes'].items()):
        raise SystemExit('Frozen inputs changed')
    os.environ.update(TOKEN_BUDGET=str(plan['token_ceiling']),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    states = []
    def save():
        state = {'stages':states,'complete':len(states)==5 and all(s['status'].startswith('completed') for s in states),
            'charged_after':charged(),'additional_charged_tokens':charged()-plan['charged_before'],
            'remaining_wall_seconds':max(0,plan['deadline_epoch']-time.time())}
        for scope in ('full','balanced'):
            measured = {}
            for label in ('after','before','vector'):
                output = ROOT/f'eval/runs/improvement_{scope}_{label}_summary.json'
                if output.exists():
                    measured[label] = json.loads(output.read_text(encoding='utf8'))
            if 'after' in measured and 'before' in measured:
                state[scope+'_after_redline_regressions'] = redline_regressions(measured['after'],measured['before'])
            if 'vector' in measured and 'before' in measured:
                state[scope+'_vector_redline_regressions'] = redline_regressions(measured['vector'],measured['before'])
        temporary = STATE.with_suffix('.pending')
        temporary.write_text(json.dumps(state,indent=2),encoding='utf8')
        temporary.replace(STATE)
        return state
    stages = [('full','before',1),('full','vector',1),
              ('repeat','after',2),('repeat','before',2),('repeat','vector',2)]
    try:
        for scope,label,count in stages:
            output = ROOT/f'eval/runs/improvement_{scope}_{label}_summary.json'
            size = 240 if scope=='full' else 70
            if output.exists():
                summary = json.loads(output.read_text(encoding='utf8'))
                if summary['evaluated_questions']!=size or summary['rounds']!=count or summary['evaluator_version']!=VERSION:
                    raise RuntimeError('Completed summary does not match this stage')
                states.append({'scope':scope,'system':label,'status':'completed_existing'})
                continue
            if time.time()>=plan['deadline_epoch'] or charged()>=plan['token_ceiling']:
                states.append({'scope':scope,'system':label,'status':'budget_deferred'})
                break
            command = [sys.executable,'-m','eval.run','--split','test','--rounds',str(count),'--phase','3',
                '--mode','vector' if label=='vector' else 'hybrid','--case-ids',plan['full_ids'] if scope=='full' else plan['repeat_ids'],
                '--output',str(output)]
            if label=='before':
                command += ['--system-source',plan['before_source']]
            if output.with_name(output.stem.replace('_summary','')+'_checkpoint.json').exists():
                command.append('--resume')
            print(json.dumps({'starting_scope':scope,'system':label,'cases':size,'rounds':count}),flush=True)
            process = subprocess.Popen(command,cwd=ROOT)
            try:
                while process.poll() is None:
                    left = plan['deadline_epoch']-time.time()
                    if left<=0:
                        raise subprocess.TimeoutExpired(command,0)
                    try:
                        process.wait(timeout=min(30,left))
                    except subprocess.TimeoutExpired:
                        save()
                code = process.returncode
            finally:
                if process.poll() is None:
                    if os.name=='nt':
                        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
                    else:
                        process.terminate()
                    process.wait(timeout=10)
            states.append({'scope':scope,'system':label,'status':'completed' if code==0 else 'failed','exit_code':code})
            save()
            if code:
                break
        if len(states)==5 and all(s['status'].startswith('completed') for s in states):
            by_id = {r['id']:r for r in records(ROOT/'eval/datasets/structured_v1.jsonl')}
            selected = [by_id[uid] for uid in json.loads((ROOT/plan['repeat_ids']).read_text(encoding='utf8'))]
            for label in ('after','before','vector'):
                combine(label,selected)
    finally:
        final = save()
        print(json.dumps(final,indent=2),flush=True)
    if not final['complete']:
        raise SystemExit(1)
    if final['full_after_redline_regressions'] or final['balanced_after_redline_regressions']:
        raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare',action='store_true')
    args = parser.parse_args()
    prepare() if args.prepare else run()


if __name__=='__main__':
    main()
