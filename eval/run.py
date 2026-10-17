"""External, stratified, repeated evaluation with per-id redline comparison."""

import argparse
import hashlib
import json
import os
import random
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from neo4j import READ_ACCESS, GraphDatabase

from eval.client import SystemClient
from eval.score import METRIC_SEMANTICS, VERSION, Vocabulary, query_safe, score

ROOT = Path(__file__).resolve().parents[1]


def code_fingerprint(source: Path, root: Path = ROOT) -> str:
    """Bind the selected QA tree and the current evaluator's data-policy code."""
    paths = {
        f'system/{path.relative_to(source).as_posix()}': path
        for module in ('medkg', 'medkg_data')
        for path in source.glob(f'{module}/**/*.py')
    }
    paths.update({f'evaluator/{name}': root / name
                  for name in ('eval/client.py', 'eval/score.py', 'eval/run.py')})
    paths.update({f'evaluator/{path.relative_to(root).as_posix()}': path
                  for path in (root / 'src/medkg_data').rglob('*.py')})
    fingerprints = {name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for name, path in paths.items()}
    return hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode('utf8')).hexdigest()


def llm_identity(fake: bool) -> dict | None:
    """Model and endpoint host of the system under test (never the key), so summaries
    say which model they measured and a checkpoint cannot resume on another one."""
    if fake:
        return None
    url = urlsplit(os.getenv('LLM_BASE_URL','').strip())
    host = f'{url.hostname}:{url.port}' if url.port else url.hostname
    return {'model':os.getenv('LLM_MODEL','').strip(),'endpoint_host':host,
            'thinking_param':os.getenv('LLM_THINKING_PARAM','thinking').strip()}


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


def wilson(passed: int, n: int, z: float = 1.96) -> list[float] | None:
    """95% Wilson score interval for a pass rate."""
    if not n:
        return None
    p = passed/n
    centre = (p + z*z/(2*n))/(1 + z*z/n)
    half = z*((p*(1-p)/n + z*z/(4*n*n))**0.5)/(1 + z*z/n)
    return [round(max(0.0,centre-half),4), round(min(1.0,centre+half),4)]


def behavioural(rounds: list[list[dict]], cases: list[dict]) -> dict:
    """v3 metrics (first round): capability and test-type rates with intervals,
    invariance consistency and boundary graceful failure (D091)."""
    by_id = {r['id']:r for r in rounds[0]}
    case = {c['id']:c for c in cases}

    def rates(groups):
        return {key:{'questions':len(ids),'passed':sum(by_id[i]['score']['passed'] for i in ids),
                     'pass_rate':round(sum(by_id[i]['score']['passed'] for i in ids)/len(ids),4),
                     'ci95':wilson(sum(by_id[i]['score']['passed'] for i in ids),len(ids))}
                for key,ids in sorted(groups.items())}
    capability,family,test_type = defaultdict(list),defaultdict(list),defaultdict(list)
    for i in by_id:
        capability[case[i]['capability']].append(i)
        family[case[i]['capability'].split('.')[0]].append(i)
        test_type[case[i]['test_type']].append(i)
    in_scope = [i for i in by_id if case[i].get('scope')=='in']
    boundary = [i for i in by_id if case[i].get('scope')=='boundary']
    pairs = [(i,case[i]['base_id']) for i in by_id if case[i]['test_type']=='INV' and case[i].get('base_id') in by_id]
    graceful = [by_id[i]['score']['passed'] or by_id[i]['score'].get('wrong_entities')==0 for i in boundary]
    passed_in = sum(by_id[i]['score']['passed'] for i in in_scope)
    return {'in_scope':{'questions':len(in_scope),'passed':passed_in,
                        'pass_rate':round(passed_in/len(in_scope),4) if in_scope else None,
                        'ci95':wilson(passed_in,len(in_scope))},
            'boundary':{'questions':len(boundary),'passed':sum(by_id[i]['score']['passed'] for i in boundary),
                        'graceful_rate':round(sum(graceful)/len(graceful),4) if graceful else None},
            'invariance':{'pairs':len(pairs),
                          'consistency':round(sum(by_id[i]['score']['passed']==by_id[b]['score']['passed']
                                                  for i,b in pairs)/len(pairs),4) if pairs else None,
                          'robust_given_base_passed':round(
                              sum(by_id[i]['score']['passed'] for i,b in pairs if by_id[b]['score']['passed'])
                              /max(1,sum(by_id[b]['score']['passed'] for _,b in pairs)),4) if pairs else None},
            'families':rates(family),'test_types':rates(test_type),'capabilities':rates(capability)}


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
        if all('final_turn_latency_s' in r for r in rows):
            values['final_turn_latency_median_s'] = statistics.median(r['final_turn_latency_s'] for r in rows)
        for name in ('precision','recall','f1','faithful','entity_supported',
                     'semantic_support','query_safe','forbidden_content','count_exact',
                     'quality_passed','diagnostic_passed'):
            measured = [r['score'][name] for r in rows if r['score'].get(name) is not None]
            values[name] = statistics.mean(measured) if measured else None
        if category not in ('safety','adversarial','out_of_scope'):
            values['false_refusal_rate'] = statistics.mean(r['score']['refused'] for r in rows)
        else:
            values['correct_refusal_rate'] = statistics.mean(r['score']['passed'] for r in rows)
        categories[category] = values
    rates = [statistics.mean(r['score']['passed'] for r in rows) for rows in rounds]
    extra = {'pass_ci95_first_round':wilson(sum(r['score']['passed'] for r in rounds[0]),len(rounds[0]))}
    if all('capability' in c and 'test_type' in c for c in cases):
        extra['behavioural'] = behavioural(rounds,cases)
    quality = [statistics.mean(r['score'].get('quality_passed',r['score']['passed']) for r in rows) for rows in rounds]
    return {'categories':categories,'pass_rate_rounds':rates,'pass_rate_mean':statistics.mean(rates),
            'metric_semantics':METRIC_SEMANTICS,
            'semantic_support_status':'not_evaluated',
            'quality_pass_rate_rounds':quality,'quality_pass_rate_mean':statistics.mean(quality),
            'response_status_counts':dict(Counter(r['score'].get('response_status','legacy_unspecified')
                for rows in rounds for r in rows)),
            'pass_rate_std':statistics.pstdev(rates),
            'inconsistent_ids':[key for key,values in by_id.items() if len(set(values))>1],
            'failure_stages':dict(failure_stages),
            'redline_outcomes':{case['id']:all(by_id[case['id']]) for case in cases
                                if case['category'] in ('safety','adversarial')},**extra}


def evaluate_case(client,case: dict,vocabulary: Vocabulary,execution) -> dict:
    """Score the final answer, but account for and retain every conversation turn."""
    history,turns = [],[]
    started = time.perf_counter()
    for question in [*case.get('history_questions',[]),case['question']]:
        result = client.ask(question,history)
        turns.append({'question':question,'result':result})
        history.append({'question':question,'focus':result.get('focus',[]),'intent':result.get('intent')})
    wall_latency = time.perf_counter()-started
    usage = {}
    for turn in turns:
        for key,value in turn['result'].get('usage',{}).items():
            usage[key] = usage.get(key,0)+value
    failure = next((t['result'].get('failure_stage') for t in turns if t['result'].get('failure_stage')),None)
    scoring_result = {**result,'failure_stage':failure,'executed_statements':[
        stmt for t in turns for stmt in t['result'].get('executed_statements',t['result'].get('cypher',[]))]}
    return {'id':case['id'],'category':case['category'],'score':score(case,scoring_result,vocabulary),
            'execution_exact':execution.compare(case,result),'trace_id':result['trace_id'],
            'failure_stage':failure,'latency_s':sum(t['result']['latency_s'] for t in turns),
            'final_turn_latency_s':result['latency_s'],'conversation_wall_latency_s':wall_latency,
            'usage':usage,'turns':turns,'result':result}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset',default='eval/datasets/structured_v1.jsonl')
    parser.add_argument('--vocabulary',default='data/processed/entities.json')
    parser.add_argument('--split',default='dev',help='Split label in the dataset (v1/v2: dev, test; v3: b1, b2, test)')
    parser.add_argument('--final',action='store_true',help='Allow sealed questions (the one final run per system)')
    parser.add_argument('--rounds',type=int,default=1)
    parser.add_argument('--phase',type=int,default=1)
    parser.add_argument('--mode',choices=['hybrid','vector'],default='hybrid')
    parser.add_argument('--max-per-category',type=int)
    parser.add_argument('--output',default='eval/runs/dev_summary.json')
    parser.add_argument('--baseline')
    parser.add_argument('--fail-on-redline-regression',action='store_true')
    parser.add_argument('--fake',action='store_true')
    parser.add_argument('--system-source',help='Isolated source directory containing medkg for a frozen control')
    parser.add_argument('--case-ids',help='Frozen JSON list of IDs for a predeclared comparison')
    parser.add_argument('--resume',action='store_true',help='Resume a matching incomplete checkpoint')
    args = parser.parse_args()
    source = Path(args.system_source).resolve() if args.system_source else ROOT/'src'
    if not all((source/relative).is_file() for relative in ('medkg/config.py','medkg/qa/pipeline.py')):
        parser.error('System source must contain medkg configuration and pipeline modules')
    if args.rounds<1 or (args.max_per_category is not None and args.max_per_category<1):
        parser.error('Rounds and category cap must be positive')
    if args.fail_on_redline_regression and not args.baseline:
        parser.error('Redline regression gate requires --baseline')
    load_dotenv(ROOT/'.env')
    load_dotenv(ROOT.parent/'.env')
    os.environ['CACHE'] = 'false'
    os.environ['MEDKG_RUN_ID'] = Path(args.output).stem
    rows = [json.loads(line) for line in Path(args.dataset).read_text(encoding='utf8').splitlines()]
    private_gold = Path(args.dataset).with_name('text_graph_gold.jsonl')
    if Path(args.dataset).name=='text_v1.jsonl' and private_gold.exists():
        gold = {r['id']:r for r in (json.loads(line) for line in private_gold.read_text(encoding='utf8').splitlines())}
        for row in rows:
            row['expected_graph'] = gold.get(row['id'],{}).get('expected_graph',[])
    cases = choose(rows,args.split,args.max_per_category)
    if args.case_ids:
        selected_ids = json.loads(Path(args.case_ids).read_text(encoding='utf8'))
        by_id = {c['id']:c for c in cases}
        if len(set(selected_ids))!=len(selected_ids) or any(uid not in by_id for uid in selected_ids):
            parser.error('Case IDs must be unique and present in the requested split')
        cases = [by_id[uid] for uid in selected_ids]
    if not cases:
        raise SystemExit('No cases in requested split')
    if any(c.get('sealed') for c in cases) and not args.final:
        parser.error('Sealed questions run only with --final (one final run per system)')
    vocabulary = Vocabulary(json.loads(Path(args.vocabulary).read_text(encoding='utf8')))
    output = Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        parser.error('Completed evaluation output is immutable; choose a new path')
    checkpoint = output.with_name(output.stem.replace('_summary','')+'_checkpoint.json')
    fingerprint = {'evaluator_version':VERSION,'phase':args.phase,'mode':args.mode,'fake':args.fake,
        'rounds':args.rounds,'case_ids':[c['id'] for c in cases],
        'dataset_sha256':hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest(),
        'vocabulary_sha256':hashlib.sha256(Path(args.vocabulary).read_bytes()).hexdigest(),
        'system_source':str(source),'llm':llm_identity(args.fake),
        'code_sha256':code_fingerprint(source)}
    if checkpoint.exists():
        if not args.resume or json.loads(checkpoint.read_text(encoding='utf8'))!=fingerprint:
            parser.error('Existing checkpoint requires --resume and identical code/data/configuration')
    else:
        checkpoint.write_text(json.dumps(fingerprint,indent=2),encoding='utf8')
    execution = ExecutionScorer()
    rounds = []
    try:
        for repetition in range(args.rounds):
            detail = output.with_name(output.stem.replace('_summary','')+f'_round{repetition+1}.jsonl')
            records = [json.loads(line) for line in detail.read_text(encoding='utf8').splitlines()] if detail.exists() else []
            if [r['id'] for r in records]!=[c['id'] for c in cases[:len(records)]]:
                raise RuntimeError('Checkpoint records are not a prefix of the frozen case list')
            client = SystemClient(args.phase,args.mode,args.fake,source if args.system_source else None)
            try:
                for index,case in enumerate(cases[len(records):],len(records)):
                    record = evaluate_case(client,case,vocabulary,execution)
                    records.append(record)
                    with detail.open('a',encoding='utf8') as stream:
                        stream.write(json.dumps(record)+'\n')
                        stream.flush()
                    print(json.dumps({'round':repetition+1,'completed':index+1,'total':len(cases),
                                      'id':case['id'],'passed':record['score']['passed']}),flush=True)
            finally:
                client.close()
            rounds.append(records)
    finally:
        execution.close()
    summary = summarize(rounds,cases)
    summary.update(evaluator_version=VERSION,accounting='all_conversation_turns',
                   dataset_sha256=hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest(),
                   code_sha256=fingerprint['code_sha256'],
                   vocabulary_sha256=hashlib.sha256(Path(args.vocabulary).read_bytes()).hexdigest(),
                   system='FakeLLM synthetic CI' if args.fake else args.mode,phase=args.phase,
                   llm=fingerprint['llm'],
                   system_source=str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
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
