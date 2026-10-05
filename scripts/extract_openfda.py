import argparse
import json
import random
from collections import Counter

from medkg.config import ROOT
from medkg.graph.store import GraphStore
from medkg.ingest.extract import extract, link_relations
from medkg.llm import LLMClient
from medkg.qa.linker import Linker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=60)
    parser.add_argument('--retry-empty-once',action='store_true',help='One recovery for legacy cache entries without error metadata')
    args = parser.parse_args()
    if not 1<=args.limit<=300:
        parser.error('Extraction sample must be between 1 and 300 chunks')
    if not (ROOT/'eval/runs/biored_summary.json').exists():
        raise SystemExit('Run the BioRED extractor check before production extraction')
    processed = ROOT/'data/processed'
    chunks = [json.loads(line) for line in (processed/'chunks.jsonl').read_text(encoding='utf8').splitlines()]
    eligible = [c for c in chunks if c['source']=='openfda' and c['section'] in
                ('contraindications','drug_interactions','boxed_warning')]
    rng = random.Random(42)
    rng.shuffle(eligible)
    chosen = eligible[:args.limit]
    entities = json.loads((processed/'entities.json').read_text(encoding='utf8'))
    linker,llm,store = Linker(entities),LLMClient(),GraphStore()
    cache = processed/'extractions.jsonl'
    prior = {r['chunk_uid']:r for r in (json.loads(line) for line in cache.read_text(encoding='utf8').splitlines())} if cache.exists() else {}
    all_edges,errors,error_types,recovered = [],0,Counter(),0
    try:
        for i,chunk in enumerate(chosen):
            previous = prior.get(chunk['uid'])
            retry = bool(args.retry_empty_once and previous and not previous['edges']
                         and 'error_type' not in previous and not previous.get('recovery_attempted'))
            if previous and not retry:
                edges = prior[chunk['uid']]['edges']
            else:
                error_type = None
                try:
                    relations = extract(llm,chunk['text'])
                    edges = link_relations(relations,chunk,linker,processed/'unlinked_mentions.jsonl')
                except Exception as exc:
                    edges = []
                    errors += 1
                    error_type = type(exc).__name__
                    error_types[error_type] += 1
                    print('Extraction call failed: '+error_type,flush=True)
                recovered += bool(retry)
                with cache.open('a',encoding='utf8') as stream:
                    stream.write(json.dumps({'chunk_uid':chunk['uid'],'edges':edges,
                        'error_type':error_type,'recovery_attempted':retry})+'\n')
            all_edges.extend(edges)
            print(f'Extracted {i+1}/{len(chosen)} chunks; {len(all_edges)} linked assertions',flush=True)
        merged = {}
        for edge in all_edges:
            key = (edge['a'],edge['b'],edge['type'])
            if key not in merged:
                merged[key] = dict(edge)
            else:
                merged[key]['evidence'] = sorted(set(merged[key]['evidence']+edge['evidence']))
                merged[key]['confidence'] = min(merged[key]['confidence'],edge['confidence'])
        edges = list(merged.values())
        latest = {r['chunk_uid']:r for r in (json.loads(line) for line in cache.read_text(encoding='utf8').splitlines())}
        agree,conflicts = 0,0
        for edge in edges:
            same = store.read('MATCH (a:Drug {uid:$a})-[r:'+edge['type']+']->(b {uid:$b}) '
                              'WHERE r.source="primekg" RETURN count(r) AS count',edge)[0]['count']
            agree += bool(same)
            if edge['type']=='CONTRAINDICATED_FOR':
                opposite = store.read('MATCH (a:Drug {uid:$a})-[r:INDICATED_FOR]->(b:Disease {uid:$b}) '
                    'WHERE r.source="primekg" RETURN count(r) AS count',edge)[0]['count']
                if opposite:
                    edge['conflict'] = True
                    conflicts += 1
                    store.write('MATCH (a:Drug {uid:$a})-[r:INDICATED_FOR]->(b:Disease {uid:$b}) '
                                'WHERE r.source="primekg" SET r.conflict=true',edge)
        store.load([], [{k:v for k,v in e.items() if k!='quote'} for e in edges])
        (processed/'extracted_edges.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in edges),encoding='utf8')
        labels = ROOT/'eval/human_labels'
        labels.mkdir(parents=True,exist_ok=True)
        sampled = rng.sample(edges,min(30,len(edges)))
        by_chunk = {c['uid']:c for c in chunks}
        todo = [{'id':f'extraction-{i+1:03d}',**edge,'review_status':'todo',
                 'contexts':[by_chunk[uid] for uid in edge['evidence']],
                 'human_supported':None,'human_linking_correct':None} for i,edge in enumerate(sampled)]
        (labels/'extraction_review_todo.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in todo),encoding='utf8')
        unlinked = processed/'unlinked_mentions.jsonl'
        summary = {'eligible_chunks':len(eligible),'processed_chunks':len(chosen),'errors':errors,
                   'error_types':dict(error_types),'legacy_cache_recoveries':recovered,
                   'cached_failed_chunks':sum(bool(latest[c['uid']].get('error_type')) for c in chosen),
                   'relations':dict(Counter(e['type'] for e in edges)),'unique_assertions':len(edges),
                   'primekg_agreement_rate':agree/len(edges) if edges else None,
                   'conflicts':conflicts,'unlinked_mentions':len(unlinked.read_text(encoding='utf8').splitlines()),
                   'human_review_items':len(todo),'extractor_version':'openfda-json-1.0',
                   'confidence_calibrated':False,'clinical_validation':False}
        (ROOT/'eval/runs/extraction_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
        print(json.dumps(summary,indent=2))
    finally:
        store.close()


if __name__=='__main__':
    main()
