"""Fresh v3 batch for the RxNorm and routing changes (D098).

    python -m eval.generate_v3_b3 --dry-run  # counts and 25 samples; no model or writes
    python -m eval.generate_v3_b3            # reword, then freeze dataset and manifest

Historical datasets supply anchor UIDs only, including the used sealed test.
Generate and evaluate b3 before changing RxNorm aliases or routing, then reuse
the frozen questions for the after-change comparison.
"""

import argparse
import hashlib
import json
import os
import random
from collections import Counter
from pathlib import Path

from eval import generate_v2 as v2
from eval.generate_v3 import ROOT, VERSION, Builder, Graph, anchors_of, finish, reword
from medkg_data.ontology import load_obo
from medkg_data.primekg import read_graph

DATASET = ROOT / 'eval/datasets/structured_v3_b3.jsonl'
MANIFEST = ROOT / 'eval/datasets/MANIFEST_v3_b3.json'
SEED_B3 = 3032
REWORD_SHARE = 0.6
PREVIOUS_DATASETS = ('structured_v1.jsonl', 'structured_v2.jsonl',
                     'structured_v3.jsonl', 'structured_v3_sealed.jsonl')


def excluded_anchors(directory: Path) -> set[str]:
    """Require all four histories; inspect only their anchor_uids fields."""
    paths = [directory / name for name in PREVIOUS_DATASETS]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f'Required anchor history is missing: {path}')
    return set().union(*(anchors_of(path) for path in paths))


def ensure_new_outputs(dataset: Path, manifest: Path) -> None:
    if dataset.exists() or manifest.exists():
        raise FileExistsError('b3 output already exists; frozen outputs are never overwritten')


def build_rows(builder: Builder, *, dry_run: bool = False) -> list[dict]:
    """Assign IDs, optionally reword bases, then derive invariance variants."""
    mft, other = builder.part(1.0)
    rows = finish(mft + other, 'b3')
    if not dry_run:
        reword([row for row in mft
                if row['kind'] in ('list', 'count') and not row.get('history_questions')],
               REWORD_SHARE, seed=SEED_B3)
    variants = builder.invariance(mft, max(1, round(len(mft) * 0.12)))
    return rows + finish(variants, 'b3', len(rows) + 1)


def summary(rows: list[dict]) -> dict:
    return {'rows': len(rows),
            **{name: dict(sorted(Counter(row[field] for row in rows).items()))
               for name, field in [('test_types', 'test_type'), ('capabilities', 'capability'),
                                   ('paraphrases', 'paraphrase_status')]}}


def write_outputs(rows: list[dict], excluded: set[str], raw: Path, processed: Path,
                  dataset: Path, manifest: Path) -> dict:
    """Create both outputs exclusively; retain partial files if writing fails."""
    ensure_new_outputs(dataset, manifest)
    payload = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode('utf8')
    metadata = {'generator_version': VERSION, 'seed': SEED_B3, 'scale': 1.0,
                'split': 'b3', 'dataset': dataset.name, **summary(rows),
                'dataset_sha256': hashlib.sha256(payload).hexdigest(),
                'kg_sha256': v2.digest(raw / 'kg.csv'),
                'catalog_sha256': v2.digest(processed / 'entities.json'),
                'excluded_anchors': len(excluded), 'anchor_sources': list(PREVIOUS_DATASETS),
                'reword_share': REWORD_SHARE, 'paraphrase_model': os.getenv('LLM_MODEL', '')}
    encoded_manifest = (json.dumps(metadata, indent=2) + '\n').encode('utf8')
    # Recheck after preparing hashes, then rely on exclusive creation as well.
    # Do not delete partial outputs: the operator must inspect an interrupted run.
    ensure_new_outputs(dataset, manifest)
    with dataset.open('xb') as output:
        output.write(payload)
    with manifest.open('xb') as output:
        output.write(encoded_manifest)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dry-run', action='store_true',
                        help='Print statistics and 25 samples; no model calls or file writes')
    args = parser.parse_args()
    try:
        if not args.dry_run:
            ensure_new_outputs(DATASET, MANIFEST)
        excluded = excluded_anchors(ROOT / 'eval/datasets')
        raw, processed = ROOT / 'data/raw', ROOT / 'data/processed'
        nodes, edges, _ = read_graph(raw / 'kg.csv', load_obo(raw / 'mondo.obo'),
                                   load_obo(raw / 'hp.obo'))
        catalog = json.loads((processed / 'entities.json').read_text(encoding='utf8'))
        documents = [json.loads(line) for line in
                     (processed / 'documents.jsonl').read_text(encoding='utf8').splitlines()]
        additions = [json.loads(line) for line in
                     (processed / 'synonym_additions.jsonl').read_text(encoding='utf8').splitlines()]
        builder = Builder(Graph(nodes, edges), catalog, documents, additions, seed=SEED_B3,
                          qualifiers=v2.hpo_qualifiers(load_obo(raw / 'hp.obo')),
                          brands=v2.fda_brands(raw / 'openfda'),
                          lay=v2.lay_names(raw / 'medlineplus.xml', documents), excluded=excluded)
        rows = build_rows(builder, dry_run=args.dry_run)
        print(json.dumps({**summary(rows), 'excluded_anchors': len(excluded)}, indent=2))
        if args.dry_run:
            for row in random.Random(1).sample(rows, min(25, len(rows))):
                question = ' >> '.join([*row.get('history_questions', []), row['question']])
                print(f"[{row['capability']}/{row['test_type']}] {question}"
                      f"  (gold {len(row['expected'])}, kind {row['kind']})")
            return
        write_outputs(rows, excluded, raw, processed, DATASET, MANIFEST)
        print(f'Created {DATASET.relative_to(ROOT)} and {MANIFEST.relative_to(ROOT)}')
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error


if __name__ == '__main__':
    main()
