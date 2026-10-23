"""Read-only catalog collision/provenance audit; creates unlabelled review tasks.

Flags are review candidates, never automatic decisions to delete a synonym.
No evaluation questions or answers are read by this audit.
"""

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from medkg.config import ROOT
from medkg_data import synonyms


def audit(entities: list[dict], additions: list[dict], supported: set[tuple]) -> list[dict]:
    owners, names, forms, provenance = defaultdict(set), {}, defaultdict(set), defaultdict(set)
    by_uid = {e['uid']:e for e in entities}
    for entity in entities:
        uid = entity['uid']
        names[uid] = synonyms.normalize(re.sub(r'\s*\((?:disease|disorder)\)$','',entity['name']))
        # Audit raw ownership, including quarantined and exact-only aliases.
        raw_aliases = [*(entity.get('synonyms') or []), *(entity.get('exact_synonyms') or [])]
        for alias in [entity['name'], *raw_aliases]:
            owners[synonyms.normalize(alias)].add(uid)
        for alias in raw_aliases:
            forms[(uid,synonyms.normalize(alias))].add(alias)
    for entry in additions:
        provenance[(entry['uid'],synonyms.normalize(entry['alias']))].add(entry['source'])
    flagged = []
    for (uid,key),variants in sorted(forms.items()):
        entity = by_uid[uid]
        others = owners[key]-{uid}
        flags = []
        same = {other for other in others if by_uid[other]['label']==entity['label']}
        unrelated = {other for other in others if by_uid[other]['label']!=entity['label']
                     and names[other]!=names[uid]}
        if same:
            flags.append('same_label_collision')
        if unrelated:
            flags.append('cross_label_distinct_canonical_names')
        if (same or unrelated) and any(a.isupper() and a.isalpha() and len(a)<=5 for a in variants):
            flags.append('acronym_collision')
        if key in synonyms.COMMON_WORDS or key in synonyms.GENERIC_ANCHORS:
            flags.append('ordinary_or_generic_word')
        sources = sorted(provenance[(uid,key)])
        unsupported = [source for source in sources if source.startswith('mesh:')
                       and (uid,key,source) not in supported]
        if unsupported:
            flags.append('mesh_join_not_reproduced')
        if not flags:
            continue
        # Scheduling priority is mechanical, not an expert correctness verdict.
        priority = (0 if unsupported else 1 if same or 'acronym_collision' in flags else 2)
        identifier = hashlib.sha256((uid+'\0'+key).encode()).hexdigest()[:16]
        flagged.append({'id':'alias-review:'+identifier,'uid':uid,'label':entity['label'],
                        'canonical_name':entity['name'],'alias_key':key,'forms':sorted(variants),
                        'flags':flags,'priority':priority,'source_ids':sources,
                        'unreproduced_source_ids':unsupported,
                        'other_owners':[{'uid':other,'label':by_uid[other]['label'],
                                         'name':by_uid[other]['name']} for other in sorted(others)]})
    return sorted(flagged,key=lambda row:(row['priority'],row['uid'],row['alias_key']))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--review-queue',type=Path,required=True)
    parser.add_argument('--review-limit',type=int,default=100)
    args = parser.parse_args()
    if not 1<=args.review_limit<=500:
        parser.error('Review batch must contain 1-500 tasks')
    output,queue = args.output_dir.resolve(),args.review_queue.resolve()
    if not output.is_relative_to(ROOT) or not queue.is_relative_to(ROOT):
        parser.error('All outputs must stay inside the repository')
    if output.exists() or queue.exists():
        parser.error('Audit outputs are immutable; choose new paths')
    catalog = ROOT/'data/processed/entities.json'
    entities = json.loads(catalog.read_text(encoding='utf8'))
    additions = [json.loads(line) for line in (ROOT/'data/processed/synonym_additions.jsonl')
                 .read_text(encoding='utf8').splitlines()]
    descriptors = synonyms.load_mesh(ROOT/'data/raw/desc2026.gz')
    equivalents = synonyms.mondo_mesh_equivalents((ROOT/'data/raw/mondo.obo').read_text(encoding='utf8'))
    proposals = [*synonyms.mesh_drug_proposals(descriptors,entities),
                 *synonyms.mesh_disease_proposals(descriptors,entities,equivalents)]
    supported = {(uid,synonyms.normalize(alias),source) for uid,alias,source in proposals}
    flagged = audit(entities,additions,supported)
    summary = {'catalog_sha256':hashlib.sha256(catalog.read_bytes()).hexdigest(),
               'entities_examined':len(entities),
               'synonym_strings_examined':sum(len(e.get('synonyms') or []) +
                                             len(e.get('exact_synonyms') or []) for e in entities),
               'flagged_entity_alias_pairs':len(flagged),
               'flags':dict(Counter(flag for row in flagged for flag in row['flags'])),
               'priorities':dict(Counter(row['priority'] for row in flagged)),
               'review_tasks':min(args.review_limit,len(flagged)),
               'unreviewed_flagged_pairs_outside_batch':max(0,len(flagged)-args.review_limit),
               'catalog_modified':False,'human_labels_assigned':0,'benchmark_rows_read':0,
               'downloads':0,'llm_calls':0}
    output.mkdir(parents=True)
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    with (output/'flagged.jsonl').open('x',encoding='utf8') as stream:
        for row in flagged:
            stream.write(json.dumps(row)+'\n')
    queue.parent.mkdir(parents=True,exist_ok=True)
    with queue.open('x',encoding='utf8') as stream:
        for row in flagged[:args.review_limit]:
            stream.write(json.dumps({**row,'decision':None,'reviewer':None,'review_notes':None})+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
