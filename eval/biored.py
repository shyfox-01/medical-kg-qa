"""BioRED pair and native-type extraction scoring through the same extractor worker."""

import argparse
import json
import random
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from eval.client import JSONProcess

ROOT = Path(__file__).resolve().parents[1]


def parse_bioc(path: Path) -> list[dict]:
    output = []
    for doc in ET.parse(path).getroot().findall('.//document'):
        entities = {}
        passages = doc.findall('passage')
        text = '\n'.join(p.findtext('text','') for p in passages)
        for annotation in doc.findall('.//annotation'):
            fields = {e.get('key'):e.text for e in annotation.findall('infon')}
            entities[annotation.get('id')] = {'type':fields.get('type',''),
                'identifier':fields.get('identifier',annotation.get('id')),
                'text':annotation.findtext('text','')}
        gold = set()
        pairs = set()
        by_identifier = {e['identifier']:e for e in entities.values()}
        for relation in doc.findall('.//relation'):
            fields = {e.get('key'):e.text for e in relation.findall('infon')}
            refs = [n.get('refid') for n in relation.findall('node')]
            if len(refs)==2 and all(r in entities for r in refs):
                a,b = [entities[r] for r in refs]
            elif fields.get('entity1') in by_identifier and fields.get('entity2') in by_identifier:
                a,b = by_identifier[fields['entity1']],by_identifier[fields['entity2']]
            else:
                continue
            types = {a['type'],b['type']}
            if not (a['type']=='ChemicalEntity' and b['type']=='ChemicalEntity' or
                    types=={'ChemicalEntity','DiseaseOrPhenotypicFeature'}):
                continue
            pair = tuple(sorted((a['identifier'],b['identifier'])))
            pairs.add(pair)
            gold.add((*pair,fields.get('type','Association')))
        if pairs:
            output.append({'id':doc.findtext('id'),'text':text,'entities':entities,
                           'gold':gold,'pairs':pairs})
    return output


def metrics(predicted: set,gold: set) -> dict:
    tp = len(predicted & gold)
    precision = tp/len(predicted) if predicted else 0
    recall = tp/len(gold) if gold else 0
    return {'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0,
            'true_positive':tp,'predicted':len(predicted),'gold':len(gold)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=12)
    args = parser.parse_args()
    paths = sorted(p for p in (ROOT/'data/raw/biored').rglob('*') if p.is_file()
                   and 'test' in p.name.casefold() and p.suffix.casefold()=='.xml')
    if not paths:
        raise SystemExit('BioRED test BioC XML is unavailable')
    documents = parse_bioc(paths[0])
    if not documents:
        raise SystemExit('No Chemical–Chemical/Chemical–Disease gold pairs parsed')
    selected = random.Random(42).sample(documents,min(args.limit,len(documents)))
    worker = JSONProcess(['-m','scripts.extract_worker'])
    predicted,pairs,gold,gold_pairs = set(),set(),set(),set()
    details = []
    try:
        for doc in selected:
            response = worker.request({'text':doc['text'],'mode':'biored'})
            mapping = {}
            for e in doc['entities'].values():
                mapping[re.sub(r'\W','',e['text'].casefold())] = e
            found = []
            for relation in response.get('relations',[]):
                a = mapping.get(re.sub(r'\W','',relation['subject'].casefold()))
                b = mapping.get(re.sub(r'\W','',relation['object'].casefold()))
                if not a or not b:
                    continue
                types = {a['type'],b['type']}
                if not (a['type']==b['type']=='ChemicalEntity' or types=={'ChemicalEntity','DiseaseOrPhenotypicFeature'}):
                    continue
                pair = tuple(sorted((a['identifier'],b['identifier'])))
                pairs.add((doc['id'],*pair))
                predicted.add((doc['id'],*pair,relation['relation']))
                found.append(relation)
            gold.update((doc['id'],*r) for r in doc['gold'])
            gold_pairs.update((doc['id'],*r) for r in doc['pairs'])
            details.append({'id':doc['id'],'relations':found,'error_type':response.get('error_type')})
            print(f'BioRED completed {len(details)}/{len(selected)}',flush=True)
    finally:
        worker.close()
    summary = {'dataset':'BioRED test','test_file':str(paths[0].relative_to(ROOT)),
               'seed':42,'available_documents':len(documents),'sampled_documents':len(selected),
               'pair_detection':metrics(pairs,gold_pairs),'native_typed_relations':metrics(predicted,gold),
               'production_contraindication_validation':False,
               'caveat':'BioRED association labels do not establish clinical contraindications.',
               'errors':sum(bool(r['error_type']) for r in details)}
    directory = ROOT/'eval/runs'
    (directory/'biored_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    (directory/'biored_details.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in details),encoding='utf8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
