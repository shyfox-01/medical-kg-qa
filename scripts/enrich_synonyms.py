"""Add MeSH (and, when present, DrugBank vocabulary) synonyms to the entity catalog.

Preview by default; --apply backs up the catalog and alias vectors, then updates
entities.json, Neo4j synonyms, chunk MENTIONS edges and alias vectors (decision D049).

    python -m scripts.enrich_synonyms            # report only
    python -m scripts.enrich_synonyms --apply    # requires a running Neo4j

The DrugBank vocabulary cannot be fetched by scripts; download "DrugBank Vocabulary"
(CC0, no account) from https://go.drugbank.com/releases/latest#open-data into data/raw/.
"""

import argparse
import hashlib
import json
import shutil
import time
from collections import Counter
from pathlib import Path

from medkg.config import ROOT
from medkg.qa.linker import Linker
from medkg_data import synonyms

RAW, PROCESSED = ROOT/'data/raw', ROOT/'data/processed'

PROBES = synonyms.COVERAGE_PROBES


def coverage(entities: list[dict]) -> dict:
    linker = Linker(entities)
    result = {}
    for probe in PROBES:
        uids = linker.aliases.get(synonyms.normalize(probe), [])
        result[probe] = sorted({linker.entities[u]['name'] for u in uids})
    return result


def drugbank_file():
    found = sorted([*RAW.glob('*drugbank*vocabulary*'), *RAW.glob('*DrugBank*Vocabulary*')])
    return found[0] if found else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--cached-labels', action='store_true',
                        help='Also propose aliases from existing openFDA and MedlinePlus files')
    parser.add_argument('--output', type=Path,
                        help='Write an immutable preview with source ids and catalog fingerprint')
    args = parser.parse_args()
    entities = json.loads((PROCESSED/'entities.json').read_text(encoding='utf8'))
    descriptors = synonyms.load_mesh(RAW/'desc2026.gz')
    equivalents = synonyms.mondo_mesh_equivalents((RAW/'mondo.obo').read_text(encoding='utf8'))
    proposals = [*synonyms.mesh_drug_proposals(descriptors, entities),
                 *synonyms.mesh_disease_proposals(descriptors, entities, equivalents)]
    vocabulary = drugbank_file()
    if vocabulary:
        proposals += synonyms.drugbank_proposals(synonyms.read_drugbank_vocabulary(vocabulary), entities)
    if args.cached_labels:
        records = [json.loads(path.read_text(encoding='utf8')) for path in sorted((RAW/'openfda').glob('*.json'))]
        proposals += synonyms.cached_fda_proposals(records, entities)
        proposals += synonyms.medlineplus_proposals(RAW/'medlineplus.xml', entities)
    additions, skipped = synonyms.merge_synonyms(entities, proposals)
    enriched = synonyms.apply_additions(entities, additions)
    before, after = coverage(entities), coverage(enriched)
    report = {
        'descriptors': len(descriptors), 'drugbank_vocabulary': vocabulary.name if vocabulary else None,
        'proposals': len(proposals), 'additions': len(additions), 'skipped': skipped,
        'additions_by_source': dict(Counter(a['source'].split(':')[0] for a in additions)),
        'additions_by_label': dict(Counter(a['label'] for a in additions)),
        'entities_enriched': len({a['uid'] for a in additions}),
        'probe_coverage_before': sum(bool(v) for v in before.values()),
        'probe_coverage_after': sum(bool(v) for v in after.values()), 'probes': len(PROBES),
        'probes_after': after, 'probes_unresolved': sorted(p for p, v in after.items() if not v),
        'cached_labels': args.cached_labels,
        'catalog_sha256': hashlib.sha256((PROCESSED/'entities.json').read_bytes()).hexdigest(),
    }
    if args.output:
        with args.output.open('x', encoding='utf8') as stream:
            json.dump({**report, 'proposed_additions': additions}, stream, indent=2)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not args.apply or not additions:
        return
    backup = ROOT/'.cache'/f'synonyms-{time.strftime("%Y%m%d-%H%M%S")}'
    backup.mkdir(parents=True)
    for name in ('entities.json', 'vector_aliases.json', 'alias_vectors.npy',
                 'synonym_additions.jsonl', 'unlinked_mentions.jsonl'):
        if (PROCESSED/name).exists():
            shutil.copy2(PROCESSED/name, backup/name)
    (PROCESSED/'entities.json').write_text(json.dumps(enriched), encoding='utf8')
    with (PROCESSED/'synonym_additions.jsonl').open('a', encoding='utf8') as stream:
        for addition in additions:
            stream.write(json.dumps(addition)+'\n')
    from medkg.graph.store import GraphStore
    from medkg.ingest.link import mentions
    changed = {a['uid'] for a in additions}
    store = GraphStore()
    try:
        for label in ('Drug', 'Disease'):
            rows = [{'uid': e['uid'], 'synonyms': e['synonyms']} for e in enriched
                    if e['uid'] in changed and e['label'] == label]
            for i in range(0, len(rows), 5000):
                store.write(f'UNWIND $rows AS row MATCH (n:{label} {{uid: row.uid}}) '
                            'SET n.synonyms = row.synonyms', {'rows': rows[i:i+5000]})
        chunks = [json.loads(line) for line in (PROCESSED/'chunks.jsonl').read_text(encoding='utf8').splitlines()]
        linked = mentions(chunks, Linker(enriched), PROCESSED/'unlinked_mentions.jsonl')
        store.write('MATCH (d:Document)-[:HAS_CHUNK]->(:Chunk)-[r:MENTIONS]->() '
                    'WHERE d.source IN ["medlineplus","openfda"] DELETE r')
        for label in ('Disease', 'Drug', 'Phenotype'):
            for i in range(0, len(linked), 10000):
                store.write('UNWIND $rows AS row MATCH (c:Chunk {uid: row.a}), '
                            f'(n:{label} {{uid: row.b}}) MERGE (c)-[:MENTIONS]->(n)',
                            {'rows': linked[i:i+10000]})
    finally:
        store.close()
    from scripts.embed_entities import main as embed
    embed()
    print(json.dumps({'applied': len(additions), 'mentions_edges': len(linked),
                      'backup': str(backup.relative_to(ROOT))}))


if __name__ == '__main__':
    main()
