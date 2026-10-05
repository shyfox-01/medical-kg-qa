"""Repair structurally invalid draft selection before any text test measurement."""

import json
import random
from pathlib import Path

from eval.client import ResearchLLM
from medkg_data.ontology import load_obo
from medkg_data.primekg import read_graph

ROOT = Path(__file__).resolve().parents[1]


def main():
    dataset = ROOT/'eval/datasets/text_v1.jsonl'
    private = dataset.with_name('text_graph_gold.jsonl')
    rows = [json.loads(line) for line in dataset.read_text(encoding='utf8').splitlines()]
    gold = {r['id']:r for r in (json.loads(line) for line in private.read_text(encoding='utf8').splitlines())}
    broken = [r for r in rows if r['category']=='graph_text' and not gold[r['id']]['expected_graph']]
    if not broken:
        return
    if list((ROOT/'eval/runs').glob('*text*round*.jsonl')):
        raise SystemExit('Draft repairs must precede test measurements')
    raw = ROOT/'data/raw'
    nodes,edges,_ = read_graph(raw/'kg.csv',load_obo(raw/'mondo.obo'),load_obo(raw/'hp.obo'))
    names = {n['uid']:n['name'] for n in nodes}
    facts = {}
    for e in edges:
        if e['type'] in ('HAS_PHENOTYPE','ASSOCIATED_WITH'):
            facts.setdefault(e['a'],[]).append({'subject':names[e['a']], 'relation':e['type'],
                'object':names[e['b']],'object_uid':e['b']})
    used = {c['uid'] for r in rows for c in r['contexts']}
    chunks = [json.loads(line) for line in (ROOT/'data/processed/chunks.jsonl').read_text(encoding='utf8').splitlines()]
    eligible = [c for c in chunks if c['source']=='medlineplus' and c['uid'] not in used
                and len(c['text'].split())>=50 and any(uid in facts for uid in c['about'])]
    chosen = random.Random(43).sample(eligible,len(broken))
    llm = ResearchLLM()
    try:
        for row,c in zip(broken,chosen,strict=True):
            graph = [f for uid in c['about'] for f in facts.get(uid,[])]
            try:
                q = llm.json('Draft a question, answer and short verbatim answer_phrases from the text. '
                    'Also include one graph fact in the answer. Return JSON with question, answer, answer_phrases.',
                    {'text':c['text'],'topic':c['name'],'graph_facts':graph[:3]})
                phrases = q.get('answer_phrases',[])
                valid = bool(phrases) and all(isinstance(p,str) and p in c['text'] for p in phrases)
            except (RuntimeError,ValueError):
                valid = False
            if not valid:
                phrases = [c['text'].split('.')[0].strip()]
            row.update(question=f"Give an example of a phenotype or gene associated with {c['name']}, and explain how MedlinePlus describes {c['name']}.",
                draft_answer=' '.join(phrases),answer_phrases=phrases,anchors=[c['name']],
                contexts=[{'uid':c['uid'],'url':c['url'],'section':c['section'],'text':c['text']}],
                generation_status='llm_grounding_checked' if valid else 'template_fallback_after_failure')
            gold[row['id']] = {'id':row['id'],'draft_answer':graph[0]['object']+'. '+' '.join(phrases),
                'graph_facts':graph[:3],'expected_graph':sorted({f['object_uid'] for f in graph})}
            print('Repaired structurally invalid draft '+row['id'],flush=True)
    finally:
        llm.close()
    dataset.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf8')
    private.write_text(''.join(json.dumps(gold[r['id']])+'\n' for r in rows),encoding='utf8')
    summary_path = ROOT/'eval/runs/text_dataset_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf8'))
    summary.update(structural_repairs=[r['id'] for r in broken],
        llm_grounding_checked=sum(r['generation_status']=='llm_grounding_checked' for r in rows))
    summary_path.write_text(json.dumps(summary,indent=2),encoding='utf8')


if __name__=='__main__':
    main()
