"""Versioned offline rescoring; never presents saved outputs as new model runs."""

import argparse
import json
from pathlib import Path

from eval.run import summarize
from eval.score import VERSION, Vocabulary, score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source',required=True,help='Historical summary file')
    parser.add_argument('--dataset',default='eval/datasets/structured_v1.jsonl')
    parser.add_argument('--vocabulary',default='data/processed/entities.json')
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    source,output = Path(args.source),Path(args.output)
    if output.resolve()==source.resolve() or output.exists():
        raise SystemExit('Rescoring needs a new output path; historical results are immutable')
    prior = json.loads(source.read_text(encoding='utf8'))
    cases = {row['id']:row for row in map(json.loads,Path(args.dataset).read_text(encoding='utf8').splitlines())}
    private = Path(args.dataset).with_name('text_graph_gold.jsonl')
    if Path(args.dataset).name=='text_v1.jsonl' and private.exists():
        for gold in map(json.loads,private.read_text(encoding='utf8').splitlines()):
            if gold['id'] in cases:
                cases[gold['id']]['expected_graph'] = gold.get('expected_graph',[])
    selected = [cases[uid] for uid in prior['evaluated_ids']]
    vocabulary = Vocabulary(json.loads(Path(args.vocabulary).read_text(encoding='utf8')))
    rounds = []
    complete_accounting = True
    for index in range(1,prior['rounds']+1):
        detail = source.with_name(source.stem.replace('_summary','')+f'_round{index}.jsonl')
        records = [json.loads(line) for line in detail.read_text(encoding='utf8').splitlines()]
        for record in records:
            scoring_result = {**record['result'],'failure_stage':record.get('failure_stage')}
            if 'turns' in record:
                scoring_result['executed_statements'] = [stmt for turn in record['turns']
                    for stmt in turn['result'].get('executed_statements',turn['result'].get('cypher',[]))]
            record['score'] = score(cases[record['id']],scoring_result,vocabulary)
            if cases[record['id']].get('history_questions') and 'turns' not in record:
                complete_accounting = False
        rounds.append(records)
    result = summarize(rounds,selected)
    result.update(evaluator_version=VERSION,measurement_kind='offline_rescore_of_saved_outputs',
        source_summary=str(source),original_evaluator_version=prior.get('evaluator_version','legacy'),
        accounting_complete=complete_accounting,
        accounting='all_conversation_turns' if complete_accounting else 'legacy_final_turn_only',
        execution_recomputed=False,new_model_calls=0,clinical_validation=False,
        rounds=prior['rounds'],evaluated_ids=prior['evaluated_ids'],evaluated_questions=len(selected),
        total_available=prior['total_available'],split=prior['split'],system=prior['system'],phase=prior['phase'])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({'output':str(output),'pass_rate_mean':result['pass_rate_mean'],
                      'accounting_complete':complete_accounting,'new_model_calls':0}))


if __name__=='__main__':
    main()
