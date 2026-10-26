"""Fresh batch b4: yes/no questions about one drug and one disease or phenotype (D112).

    python -m eval.generate_v3_b4 --dry-run  # counts and samples; no writes
    python -m eval.generate_v3_b4            # freeze dataset and manifest

"Is metformin used to treat type 2 diabetes?", "Is X contraindicated in Y?", "Can X
cause Y?": half are recorded in the graph, half are not (the disease or phenotype
then has the relation with some other drug, so it is a plausible pairing). Template
wording only. A third of the rows are b4_dev, for building the rules; the rest are
b4, measured once. Historical datasets supply anchor UIDs only, including the used
sealed test.
"""

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

from eval import generate_v2 as v2
from eval.generate_v3 import RELATIONS, ROOT, VERSION, Builder, Graph, anchors_of
from medkg_data.ontology import load_obo
from medkg_data.primekg import read_graph

DATASET = ROOT / 'eval/datasets/structured_v3_b4.jsonl'
MANIFEST = ROOT / 'eval/datasets/MANIFEST_v3_b4.json'
SEED_B4 = 3051
PER_ANSWER = 10
DEV_SHARE = 1 / 3
PREVIOUS_DATASETS = ('structured_v1.jsonl', 'structured_v2.jsonl', 'structured_v3.jsonl',
                     'structured_v3_sealed.jsonl', 'structured_v3_b3.jsonl')
PAIR_TEMPLATES = {
    'indications': ['Is {a} used to treat {b}?', 'Does {a} treat {b}?', 'Is {a} indicated for {b}?',
                    'Can {a} be used for {b}?'],
    'contraindications': ['Is {a} contraindicated in {b}?', 'Is {a} contraindicated for patients with {b}?',
                          'Is {b} a contraindication for {a}?'],
    'side_effects': ['Can {a} cause {b}?', 'Is {b} a side effect of {a}?', 'Does {a} have {b} as a side effect?'],
}


def excluded_anchors(directory: Path) -> set[str]:
    paths = [directory / name for name in PREVIOUS_DATASETS]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f'Required anchor history is missing: {path}')
    return set().union(*(anchors_of(path) for path in paths))


def pair_rows(builder: Builder) -> list[dict]:
    t, rows = builder.g.targets, []
    for intent, templates in PAIR_TEMPLATES.items():
        label, target, relation, direction = RELATIONS[intent]
        drugs = [u for u in builder.by_label[label] if builder.free(u) and 1 <= len(t(intent, u)) <= 200]
        common = [u for u in drugs if u in builder.common[label]]
        # Plausible "no" partners: targets of the same relation for other drugs.
        pool = sorted({b for u in drugs for b in t(intent, u)})
        query = (f'MATCH (a:{label} {{uid:$a}})-[:{relation}]->(b:{target} {{uid:$b}}) '
                 'RETURN DISTINCT b.uid AS uid')
        for answer in (True, False):
            made = 0
            for _ in range(5000):
                if made >= PER_ANSWER:
                    break
                a = builder.rng.choice(common or drugs)
                if not builder.free(a):
                    continue
                recorded = t(intent, a)
                partners = sorted(recorded) if answer else [b for b in builder.rng.sample(pool, min(60, len(pool)))
                                                            if b not in recorded]
                partners = [b for b in partners if builder.free(b)]
                if not partners:
                    continue
                b = builder.rng.choice(partners)
                builder.claim(a, b)
                made += 1
                question = builder.rng.choice(templates).format(a=builder.display(a), b=builder.display(b))
                rows.append(builder.mft(f"yesno.{intent}_{'yes' if answer else 'no'}", question,
                                        {b} if answer else set(), query, {'a': a, 'b': b},
                                        [builder.display(a), builder.display(b)], [a, b], 'yesno',
                                        category='yes_no', expected_answer=answer, target_label=target,
                                        intent=intent))
    return rows


def finish(rows: list[dict], rng: random.Random) -> list[dict]:
    order = list(range(len(rows)))
    rng.shuffle(order)
    dev = set(order[:round(len(rows) * DEV_SHARE)])
    for i, row in enumerate(rows, 1):
        split = 'b4_dev' if i - 1 in dev else 'b4'
        row.update(id=f'v3-{split.replace("_", "")}-{i:04d}', split=split, generator_version=VERSION,
                   paraphrase_status='template')
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not args.dry_run and (DATASET.exists() or MANIFEST.exists()):
        raise SystemExit('b4 output already exists; frozen outputs are never overwritten')
    excluded = excluded_anchors(ROOT / 'eval/datasets')
    raw, processed = ROOT / 'data/raw', ROOT / 'data/processed'
    nodes, edges, _ = read_graph(raw / 'kg.csv', load_obo(raw / 'mondo.obo'), load_obo(raw / 'hp.obo'))
    catalog = json.loads((processed / 'entities.json').read_text(encoding='utf8'))
    documents = [json.loads(line) for line in (processed / 'documents.jsonl').read_text(encoding='utf8').splitlines()]
    additions = [json.loads(line) for line in
                 (processed / 'synonym_additions.jsonl').read_text(encoding='utf8').splitlines()]
    builder = Builder(Graph(nodes, edges), catalog, documents, additions, seed=SEED_B4,
                      qualifiers=v2.hpo_qualifiers(load_obo(raw / 'hp.obo')),
                      brands=v2.fda_brands(raw / 'openfda'),
                      lay=v2.lay_names(raw / 'medlineplus.xml', documents), excluded=excluded)
    rows = finish(pair_rows(builder), random.Random(SEED_B4))
    counts = {'rows': len(rows), 'splits': dict(Counter(r['split'] for r in rows)),
              'capabilities': dict(sorted(Counter(r['capability'] for r in rows).items()))}
    print(json.dumps(counts, indent=2))
    if args.dry_run:
        for row in rows[:12]:
            print(f"[{row['split']}/{row['capability']}] {row['question']}")
        return
    payload = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode('utf8')
    manifest = {'generator_version': VERSION, 'seed': SEED_B4, **counts, 'dataset': DATASET.name,
                'dataset_sha256': hashlib.sha256(payload).hexdigest(),
                'kg_sha256': v2.digest(raw / 'kg.csv'), 'catalog_sha256': v2.digest(processed / 'entities.json'),
                'excluded_anchors': len(excluded), 'anchor_sources': list(PREVIOUS_DATASETS)}
    with DATASET.open('xb') as output:
        output.write(payload)
    with MANIFEST.open('xb') as output:
        output.write((json.dumps(manifest, indent=2) + '\n').encode('utf8'))
    print(f'Created {DATASET.relative_to(ROOT)} and {MANIFEST.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
