"""No-key requests, persistent cap of 500, cached responses and conservative pacing."""

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from rapidfuzz import fuzz, process

from medkg.ingest.chunking import chunks
from medkg.qa.linker import normalize

SECTIONS = ('indications_and_usage','contraindications','drug_interactions','boxed_warning',
            'warnings_and_cautions','adverse_reactions','description')


def fetch(drugs: list[dict],raw: Path) -> list[dict]:
    directory = raw/'openfda'
    directory.mkdir(parents=True,exist_ok=True)
    ledger = directory/'requests.jsonl'
    records = [json.loads(line) for line in ledger.read_text(encoding='utf8').splitlines()] if ledger.exists() else []
    total = len(records)
    outputs = []
    for drug in drugs[:500]:
        key = hashlib.sha256(drug['uid'].encode()).hexdigest()[:20]
        path = directory/(key+'.json')
        if path.exists():
            cached = json.loads(path.read_text(encoding='utf8'))
            if cached.get('status')=='ok' or cached.get('query_version')=='phrase-v2':
                outputs.append(cached)
                continue
        if total>=500:
            break
        term = drug['name'].replace('"','').replace('\\','')
        search = f'(openfda.generic_name:"{term}" OR openfda.substance_name:"{term}")'
        url = 'https://api.fda.gov/drug/label.json?'+urllib.parse.urlencode(
            {'search':search,'sort':'effective_time:desc','limit':1})
        entry = {'drug_uid':drug['uid'],'timestamp':time.time(),'url':url,'query_version':'phrase-v2'}
        with ledger.open('a',encoding='utf8') as stream:
            stream.write(json.dumps(entry)+'\n')
        total += 1
        try:
            request = urllib.request.Request(url,headers={'User-Agent':'medkg-research/0.1'})
            with urllib.request.urlopen(request,timeout=25) as response:
                data = json.loads(response.read())
            entry.update(status='ok',results=data.get('results',[]))
        except urllib.error.HTTPError as exc:
            entry.update(status=f'http_{exc.code}',results=[])
        except (OSError,ValueError):
            entry.update(status='network_or_parse_failure',results=[])
        path.write_text(json.dumps(entry),encoding='utf8')
        outputs.append(entry)
        print(f'openFDA request {total}/500: {entry["status"]}',flush=True)
        time.sleep(1.6)
    return outputs


def parse(records: list[dict],entities: list[dict],retrieved_at: str) -> tuple[list,list,dict]:
    drugs = {e['uid']:e for e in entities if e['label']=='Drug'}
    aliases = {}
    for drug in drugs.values():
        for alias in [drug['name'],*drug.get('synonyms',[])]:
            aliases.setdefault(normalize(alias),set()).add(drug['uid'])
    documents,sections_by_id,brand_candidates = {},{},{}
    unsafe_brands = set()
    stats = {'labels':0,'unlinked_labels':0,'ambiguous_labels':0,'quarantined_aliases':0}
    for record in records:
        for label in record.get('results',[]):
            stats['labels'] += 1
            fields = label.get('openfda',{})
            names = fields.get('generic_name',[])+fields.get('substance_name',[])
            about,matched_names = set(),{}
            ambiguous,unmatched = False,False
            for name in names:
                ids = set(aliases.get(normalize(name),set()))
                if not ids:
                    scored = process.extract(normalize(name),aliases.keys(),
                        scorer=fuzz.token_sort_ratio,score_cutoff=95,limit=2)
                    if scored:
                        maximum = scored[0][1]
                        ids = set().union(*(aliases[alias] for alias,score,_ in scored
                                            if score==maximum))
                if len(ids)==1:
                    uid = next(iter(ids))
                    about.add(uid)
                    matched_names.setdefault(uid,set()).add(name)
                elif ids:
                    ambiguous = True
                else:
                    unmatched = True
            if ambiguous or len(about)>1:
                stats['ambiguous_labels'] += 1
            brands = fields.get('brand_name',[])
            if len(about)!=1 or ambiguous or unmatched:
                unsafe_brands.update(normalize(brand) for brand in brands)
            if not about:
                stats['unlinked_labels'] += 1
                stats['quarantined_aliases'] += len(brands)
                continue
            for uid in about:
                drugs[uid]['synonyms'] = sorted(set(drugs[uid].get('synonyms',[])) | matched_names[uid])
            if len(about)==1 and not ambiguous and not unmatched:
                uid = next(iter(about))
                for brand in brands:
                    entry = brand_candidates.setdefault(normalize(brand),{'uids':set(),'names':set()})
                    entry['uids'].add(uid)
                    entry['names'].add(brand)
            else:
                stats['quarantined_aliases'] += len(brands) + sum(
                    name not in set().union(*matched_names.values()) for name in names)
            identifier = label.get('id',label.get('set_id',''))
            if not identifier:
                stats['unlinked_labels'] += 1
                continue
            if identifier in documents:
                documents[identifier]['about'] = sorted(set(documents[identifier]['about']) | about)
                continue
            document = {'uid':'openfda:'+identifier,'source':'openfda',
                'url':'https://api.fda.gov/drug/label.json?'+urllib.parse.urlencode({'search':'id:"'+identifier+'"'}),
                'title':'; '.join(names) or 'Drug label','name':'; '.join(names) or 'Drug label',
                'synonyms':[],'retrieved_at':retrieved_at,'about':sorted(about)}
            sections = {s:' '.join(label.get(s,[])) for s in SECTIONS if label.get(s)}
            documents[identifier] = document
            sections_by_id[identifier] = sections
    for key,entry in brand_candidates.items():
        if key in unsafe_brands or len(entry['uids'])!=1 or aliases.get(key,set())-entry['uids']:
            stats['quarantined_aliases'] += len(entry['names'])
            unsafe_brands.add(key)
            continue
        uid = next(iter(entry['uids']))
        drugs[uid]['synonyms'] = sorted(set(drugs[uid]['synonyms']) | entry['names'])
    # Also remove an unsafe brand retained from an earlier import. Canonical
    # names remain authoritative and are never removed by this alias operation.
    for drug in drugs.values():
        drug['synonyms'] = [name for name in drug.get('synonyms',[])
                            if normalize(name) not in unsafe_brands]
    all_chunks = [chunk for identifier,document in documents.items()
                  for chunk in chunks(document,sections_by_id[identifier])]
    return list(documents.values()),all_chunks,stats
