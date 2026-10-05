"""External, stratified, repeated evaluation with per-id redline comparison."""

import argparse
import json
import os
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv
from neo4j import READ_ACCESS, GraphDatabase

from eval.client import SystemClient
from eval.score import Vocabulary, query_safe, score

ROOT = Path(__file__).resolve().parents[1]


def canonical_results(rows: list[dict]) -> set[str]:
    values = []
    for row in rows:
        if 'count' in row:
            values.append({'count':row['count']})
        elif 'uid' in row:
            values.append({'uid':row['uid']})
        else:
            return {json.dumps(row,sort_keys=True,default=str) for row in rows}
    return {json.dumps(row,sort_keys=True) for row in values}


class ExecutionScorer:
    def __init__(self):
        load_dotenv(ROOT/'.env')
        load_dotenv(ROOT.parent/'.env')
        self.driver = GraphDatabase.driver(os.getenv('NEO4J_URI','bolt://127.0.0.1:7687'),
            auth=(os.getenv('NEO4J_USER','neo4j'),os.getenv('NEO4J_PASSWORD','')))
        self.database = os.getenv('NEO4J_DATABASE','neo4j')

    def compare(self, case: dict, result: dict) -> bool | None:
        queries = result.get('queries',[])
        if not queries or not case.get('gold_query'):
            return None
        if not query_safe([q['cypher'] for q in queries]):
            return False
        try:
            with self.driver.session(database=self.database,default_access_mode=READ_ACCESS) as session:
                with session.begin_transaction(timeout=10) as tx:
                    gold = tx.run(case['gold_query'],case.get('gold_params',{})).data()
                    predicted = tx.run(queries[-1]['cypher'],queries[-1].get('params',{})).data()
                    tx.commit()
            return canonical_results(gold)==canonical_results(predicted)
        except Exception:
            return False

    def close(self) -> None:
        self.driver.close()


def redline_regressions(current: dict,baseline: dict) -> list[str]:
    old,new = baseline.get('redline_outcomes',{}),current.get('redline_outcomes',{})
    return sorted(key for key,value in old.items() if value and (key not in new or not new[key]))


def choose(rows: list[dict],split: str,cap: int | None,seed: int = 42) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        if row.get('split')==split:
            groups[row['category']].append(row)
    rng = random.Random(seed)
    selected = []
    for category,group in sorted(groups.items()):
        group.sort(key=lambda r:r['id'])
        selected += rng.sample(group,min(cap,len(group))) if cap and category not in ('safety','adversarial') else group
    return selected


def summarize(rounds: list[list[dict]],cases: list[dict]) -> dict:
    categories = {}
    by_id = defaultdict(list)
    failure_stages = Counter()
    for rows in rounds:
        for row in rows:
            by_id[row['id']].append(row['score']['passed'])
            if row['failure_stage']:
                failure_stages[row['failure_stage']] += 1
    for category in sorted({c['category'] for c in cases}):
        rows = [r for round_ in rounds for r in round_ if r['category']==category]
        rates = [statistics.mean(r['score']['passed'] for r in round_ if r['category']==category) for round_ in rounds]
        executed = [r['execution_exact'] for r in rows if r['execution_exact'] is not None]
        values = {'questions':len(rows)//len(rounds),'pass_rate_rounds':rates,
                  'pass_rate_mean':statistics.mean(rates),'pass_rate_std':statistics.pstdev(rates),
                  'execution_accuracy':statistics.mean(executed) if executed else None,
                  'execution_coverage':len(executed),'false_refusal_rate':None,
                  'latency_median_s':statistics.median(r['latency_s'] for r in rows),
                  'latency_p90_s':sorted(r['latency_s'] for r in rows)[max(0,int(len(rows)*0.9)-1)],
                  'llm_calls':sum(r['usage'].get('calls',0) for r in rows),
                  'tokens':sum(r['usage'].get('prompt_tokens',0)+r['usage'].get('completion_tokens',0) for r in rows)}
        for name in ('precision','recall','f1','faithful','query_safe','forbidden_content','count_exact'):
            measured = [r['score'][name] for r in rows if r['score'][name] is not None]
            values[name] = statistics.mean(measured) if measured else None
        if category not in ('safety','adversarial','out_of_scope'):
            values['false_refusal_rate'] = statistics.mean(r['score']['refused'] for r in rows)
        else:
            values['correct_refusal_rate'] = statistics.mean(r['score']['passed'] for r in rows)
        categories[category] = values
    rates = [statistics.mean(r['score']['passed'] for r in rows) for rows in rounds]
    return {'categories':categories,'pass_rate_rounds':rates,'pass_rate_mean':statistics.mean(rates),
            'pass_rate_std':statistics.pstdev(rates),
            'inconsistent_ids':[key for key,values in by_id.items() if len(set(values))>1],
            'failure_stages':dict(failure_stages),
            'redline_outcomes':{case['id']:all(by_id[case['id']]) for case in cases
                                if case['category'] in ('safety','adversarial')}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset',default='eval/datasets/structured_v1.jsonl')
    parser.add_argument('--vocabulary',default='data/processed/entities.json')
    parser.add_argument('--split',choices=['dev','test'],default='dev')
    parser.add_argument('--rounds',type=int,default=1)
    parser.add_argument('--phase',type=int,default=1)
    parser.add_argument('--mode',choices=['hybrid','vector'],default='hybrid')
    parser.add_argument('--max-per-category',type=int)
    parser.add_argument('--output',default='eval/runs/dev_summary.json')
    parser.add_argument('--baseline')
    parser.add_argument('--fail-on-redline-regression',action='store_true')
    parser.add_argument('--fake',action='store_true')
    args = parser.parse_args()
    if args.rounds<1 or (args.max_per_category is not None and args.max_per_category<1):
        parser.error('Rounds and category cap must be positive')
    if args.fail_on_redline_regression and not args.baseline:
        parser.error('Redline regression gate requires --baseline')
    os.environ['CACHE'] = 'false'
    os.environ['MEDKG_RUN_ID'] = Path(args.output).stem
    rows = [json.loads(line) for line in Path(args.dataset).read_text(encoding='utf8').splitlines()]
    private_gold = Path(args.dataset).with_name('text_graph_gold.jsonl')
    if Path(args.dataset).name=='text_v1.jsonl' and private_gold.exists():
        gold = {r['id']:r for r in (json.loads(line) for line in private_gold.read_text(encoding='utf8').splitlines())}
        for row in rows:
            row['expected_graph'] = gold.get(row['id'],{}).get('expected_graph',[])
    cases = choose(rows,args.split,args.max_per_category)
    if not cases:
        raise SystemExit('No cases in requested split')
    vocabulary = Vocabulary(json.loads(Path(args.vocabulary).read_text(encoding='utf8')))
    execution = ExecutionScorer()
    rounds = []
    try:
        for repetition in range(args.rounds):
            client = SystemClient(args.phase,args.mode,args.fake)
            records = []
            try:
                for index,case in enumerate(cases):
                    history = []
                    for q in case.get('history_questions',[]):
                        previous = client.ask(q,history)
                        history.append({'question':q,'focus':previous.get('focus',[]),'intent':previous.get('intent')})
                    result = client.ask(case['question'],history)
                    measured = score(case,result,vocabulary)
                    records.append({'id':case['id'],'category':case['category'],'score':measured,
                                    'execution_exact':execution.compare(case,result),'trace_id':result['trace_id'],
                                    'failure_stage':result.get('failure_stage'),'latency_s':result['latency_s'],
                                    'usage':result['usage'],'result':result})
                    print(json.dumps({'round':repetition+1,'completed':index+1,'total':len(cases),
                                      'id':case['id'],'passed':measured['passed']}),flush=True)
            finally:
                client.close()
            rounds.append(records)
            detail = Path(args.output).with_name(Path(args.output).stem.replace('_summary','')+f'_round{repetition+1}.jsonl')
            detail.parent.mkdir(parents=True,exist_ok=True)
            detail.write_text(''.join(json.dumps(r)+'\n' for r in records),encoding='utf8')
    finally:
        execution.close()
    summary = summarize(rounds,cases)
    summary.update(system='FakeLLM synthetic CI' if args.fake else args.mode,phase=args.phase,
                   split=args.split,rounds=args.rounds,dataset=args.dataset,
                   total_available=sum(r.get('split')==args.split for r in rows),
                   evaluated_questions=len(cases),sampling_cap=args.max_per_category,
                   evaluated_ids=[c['id'] for c in cases],cache_enabled=False,
                   judge_status='uncalibrated',clinical_validation=False)
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding='utf8'))
        summary['redline_regressions'] = redline_regressions(summary,baseline)
    Path(args.output).write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('categories','redline_outcomes','evaluated_ids')},indent=2))
    if args.fail_on_redline_regression and summary.get('redline_regressions'):
        raise SystemExit(1)


if __name__=='__main__':
    main()
