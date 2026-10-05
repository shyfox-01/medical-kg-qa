"""Draft public-domain text questions externally; all items await human review."""

import json
import random
from collections import defaultdict
from pathlib import Path

from eval.client import ResearchLLM
from eval.generate import split
from medkg_data.ontology import load_obo
from medkg_data.primekg import read_graph

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    processed,raw = ROOT/'data/processed',ROOT/'data/raw'
    path = ROOT/'eval/datasets/text_v1.jsonl'
    if path.exists():
        raise SystemExit('Text drafts are frozen; edit review labels explicitly')
    source = [json.loads(line) for line in (processed/'chunks.jsonl').read_text(encoding='utf8').splitlines()]
    nodes,edges,_ = read_graph(raw/'kg.csv',load_obo(raw/'mondo.obo'),load_obo(raw/'hp.obo'))
    names = {n['uid']:n['name'] for n in nodes}
    facts = defaultdict(list)
    for edge in edges:
        if edge['type']!='INTERACTS_WITH':
            facts[edge['a']].append({'subject':names[edge['a']],'relation':edge['type'],
                                   'object':names[edge['b']],'object_uid':edge['b']})
    eligible = [c for c in source if c['source']=='medlineplus' and len(c['text'].split())>=50]
    mixed = [c for c in eligible if any(f['relation'] in ('HAS_PHENOTYPE','ASSOCIATED_WITH')
                                      for uid in c['about'] for f in facts.get(uid,[]))]
    rng = random.Random(42)
    selected = [('text_only',c) for c in rng.sample(eligible,40)]
    selected += [('graph_text',c) for c in rng.sample(mixed,40)]
    llm = ResearchLLM()
    rows = []
    private_gold = []
    try:
        for i in range(0,len(selected),4):
            batch = selected[i:i+4]
            payload = []
            for index,(category,chunk) in enumerate(batch,i+1):
                graph = [f for uid in chunk['about'] for f in facts.get(uid,[])][:3] if category=='graph_text' else []
                payload.append({'id':f'text-{index:03d}','category':category,'title':chunk['name'],
                                'chunk_uid':chunk['uid'],'text':chunk['text'],'graph_facts':graph})
            try:
                response = llm.json('Draft one English knowledge question per item using the provided text. '
                    'For graph_text, require at least one provided graph fact AND a textual fact. '
                    'Keep topic names in the question. Return JSON {"questions":[{"id":"...",'
                    '"question":"...","answer":"...","answer_phrases":["short verbatim text quote"],'
                    '"uses_graph_fact":true}]}. No diagnosis or doses. Quotes must appear verbatim in the chunk.',
                    {'items':payload},1800)
                drafted = {q['id']:q for q in response.get('questions',[])}
            except (RuntimeError,ValueError,KeyError):
                drafted = {}
            for item,(category,chunk) in zip(payload,batch,strict=True):
                q = drafted.get(item['id'],{})
                phrases = q.get('answer_phrases',[])
                valid = bool(phrases) and all(p in chunk['text'] for p in phrases)
                valid &= category=='text_only' or bool(q.get('uses_graph_fact') and item['graph_facts'])
                if not valid:
                    quote = chunk['text'].split('.')[0].strip()
                    q = {'question':f"According to MedlinePlus, what does the summary of {chunk['name']} say?",
                         'answer':quote,'answer_phrases':[quote], 'uses_graph_fact':False}
                    if category=='graph_text':
                        fact = item['graph_facts'][0]
                        q['question'] = f"What is recorded as {fact['relation'].lower().replace('_',' ')} for {fact['subject']}, and what does MedlinePlus say about {chunk['name']}?"
                        q['answer'] = fact['object']+'. '+quote
                        q['uses_graph_fact'] = True
                expected_graph = sorted({fact['object_uid'] for uid in chunk['about'] for fact in facts.get(uid,[])
                                         if fact['relation'] in ('HAS_PHENOTYPE','ASSOCIATED_WITH')}) if category=='graph_text' else []
                if category=='graph_text':
                    q['question'] = f"Give an example of a phenotype or gene associated with {chunk['name']}, and explain how MedlinePlus describes {chunk['name']}."
                private_gold.append({'id':item['id'],'draft_answer':q['answer'],
                                     'graph_facts':item['graph_facts'],'expected_graph':expected_graph})
                rows.append({'id':item['id'],'category':category,'kind':'text','question':q['question'],
                    'draft_answer':' '.join(q['answer_phrases']),'answer_phrases':q['answer_phrases'],
                    'contexts':[{'uid':chunk['uid'],'url':chunk['url'],'section':chunk['section'],'text':chunk['text']}],
                    'review_status':'draft',
                    'generation_status':'llm_grounding_checked' if valid else 'template_fallback_after_failure',
                    'expected':[],'anchors':[chunk['name']]})
            print(f'Drafted text questions {len(rows)}/80',flush=True)
    finally:
        llm.close()
    split(rows)
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf8')
    (path.parent/'text_graph_gold.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in private_gold),encoding='utf8')
    report = {'text_only':40,'graph_text':40,'dev':32,'test':48,'review_status':'draft',
              'llm_grounding_checked':sum(r['generation_status']=='llm_grounding_checked' for r in rows),
              'human_validated':False,'text_scoring':'strict quote-phrase coverage; exploratory only'}
    (ROOT/'eval/runs/text_dataset_summary.json').write_text(json.dumps(report,indent=2),encoding='utf8')


if __name__=='__main__':
    main()
