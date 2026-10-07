"""Read-only delivery audit: private-artifact boundaries, frozen counts and runtime."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from importlib.metadata import version

import yaml
from dotenv import dotenv_values

from medkg.config import ROOT
from medkg.graph.store import GraphStore


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',default='eval/runs/delivery_summary.json')
    args = parser.parse_args()
    tracked = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],
                                      cwd=ROOT,text=True).splitlines()
    forbidden = [p for p in tracked if p.startswith(('data/raw/','data/processed/','.cache/','runs/'))
        or p.endswith('.env') or p=='CODEX_TASK.md'
        or p=='eval/datasets/text_graph_gold.jsonl'
        or (p.startswith('eval/human_labels/') and p.endswith('.jsonl'))
        or (p.startswith('eval/datasets/structured') and p.endswith('.jsonl'))
        or (p.startswith('eval/runs/') and not p.endswith('_summary.json'))]
    checks = {'private_data_not_tracked':not forbidden}
    secrets = {v for path in (ROOT/'.env',ROOT.parent/'.env') for k,v in dotenv_values(path).items()
               if v and len(v)>=8 and any(word in k for word in ('PASSWORD','API_KEY','TOKEN'))}
    leaked = []
    chinese = []
    for path in tracked:
        file = ROOT/path
        if not file.is_file():
            continue
        content = file.read_text(encoding='utf8',errors='replace')
        if any(value in content for value in secrets):
            leaked.append(path)
        if re.search(r'[\u3400-\u9fff]',content):
            chinese.append(path)
    checks['tracked_files_no_env_secret_values'] = not leaked
    checks['tracked_files_no_chinese_content'] = not chinese
    checks['eval_no_internal_qa_imports'] = not any(re.search(
        r'^\s*(?:from|import) medkg(?:\.|\s)',f.read_text(),re.M) for f in (ROOT/'eval').glob('*.py'))
    structured = lines(ROOT/'eval/datasets/structured_v1.jsonl')
    text = lines(ROOT/'eval/datasets/text_v1.jsonl')
    judge = lines(ROOT/'eval/human_labels/judge_calibration_todo.jsonl')
    extraction = lines(ROOT/'eval/human_labels/extraction_review_todo.jsonl')
    checks['frozen_400_structured_80_drafts'] = len(structured)==400 and len(text)==80 and all(
        row['review_status']=='draft' for row in text)
    checks['human_100_claims_30_assertions'] = len(judge)==100 and len(extraction)==30
    checks['split_160_240'] = sum(r['split']=='dev' for r in structured)==160 and sum(
        r['split']=='test' for r in structured)==240
    progress = json.loads((ROOT/'data/processed/vector_progress.json').read_text())
    checks['vector_corpus_complete'] = progress['completed']==progress['total']==47668
    compose = yaml.safe_load((ROOT/'docker-compose.yml').read_text())
    checks['compose_two_services_loopback'] = set(compose['services'])=={'app','neo4j'} and all(
        p.startswith('127.0.0.1:') for s in compose['services'].values() for p in s.get('ports',[]))
    checks['neo4j_image_version'] = compose['services']['neo4j']['image']=='neo4j:5.26-community'
    balances = {}
    for row in lines(ROOT/'eval/runs/usage_log.jsonl'):
        balances[row['call_id']] = row.get('charged_tokens',row.get('reserved_tokens',0))
    checks['task_budget_below_15m'] = sum(balances.values())<15000000
    store = GraphStore()
    try:
        checks['temporary_fixture_removed'] = store.read('MATCH (n) WHERE n.uid STARTS WITH "synthetic:" '
            'RETURN count(n) AS count')[0]['count']==0
        checkpoint = store.read('SHOW PROCEDURES YIELD name WHERE name CONTAINS "checkpoint" RETURN name')
        graph = store.counts()
    finally:
        store.close()
    summary = {'checks':checks,'passed':all(checks.values()),
        'violating_paths':{'private':forbidden,'secrets':leaked,'non_english':chinese},
        'conservative_charged_or_reserved_tokens':sum(balances.values()),'token_cap':15000000,
        'python':sys.version.split()[0],'environment_prefix':sys.prefix,
        'versions':{n:version(n) for n in ['neo4j','openai','fastapi','opentelemetry-sdk','fastembed','pytest','ruff']},
        'graph_counts':graph,'checkpoint_procedures':[r['name'] for r in checkpoint],
        'structured_sha256':hashlib.sha256((ROOT/'eval/datasets/structured_v1.jsonl').read_bytes()).hexdigest(),
        'docker_runtime_verified':False,'remote_ci_verified':False,'phoenix_verified':False}
    (ROOT/args.output).write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(summary,indent=2))
    if not summary['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
