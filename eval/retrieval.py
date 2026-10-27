"""Text retrieval on the frozen text set: is the gold chunk among the chunks returned? (D115)

Each question of eval/datasets/text_v1.jsonl was written from one chunk. The question
itself is the query, with no filters, as the planner's vector_search would send it.

    python -m eval.retrieval --split dev --output eval/runs/d115_retrieval_dev.json
    python -m eval.retrieval --arms hybrid rerank --rerank-model Xenova/ms-marco-MiniLM-L-6-v2
"""

import argparse
import json
import time
from pathlib import Path

from medkg.config import ROOT
from medkg.graph.store import GraphStore
from medkg.retrieval import vector

ARMS = ('dense', 'sparse', 'hybrid', 'rerank')
DATASET = ROOT/'eval/datasets/text_v1.jsonl'


def retrieve(store, arm: str, question: str, model: str | None = None) -> list[dict]:
    if arm == 'dense':
        return vector.dense(store, question, limit=vector.TOP)
    if arm == 'sparse':
        return vector.sparse(store, question, limit=vector.TOP)
    if arm == 'hybrid':
        return vector.fuse([vector.dense(store, question), vector.sparse(store, question)])
    if arm == 'rerank':
        fused = vector.fuse([vector.dense(store, question), vector.sparse(store, question)], top=vector.CANDIDATES)
        return vector.rerank(question, fused, model)
    raise ValueError(f'Unknown arm {arm}')


def rank_of(rows: list[dict], gold: str) -> int | None:
    uids = [row['uid'] for row in rows]
    return uids.index(gold)+1 if gold in uids else None


def summary(ranks: list[int | None]) -> dict:
    n = len(ranks)
    out = {'questions': n}
    for k in (1, 3, 8):
        out[f'recall@{k}'] = round(sum(1 for r in ranks if r and r <= k)/n, 3) if n else None
    out['mrr'] = round(sum(1/r for r in ranks if r)/n, 3) if n else None
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=('dev', 'test', 'all'), default='dev')
    parser.add_argument('--arms', nargs='+', choices=ARMS, default=['dense', 'sparse', 'hybrid'])
    parser.add_argument('--rerank-model', help='Cross-encoder for the rerank arm (fastembed name)')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if 'rerank' in args.arms and not args.rerank_model:
        parser.error('The rerank arm needs --rerank-model')
    cases = [json.loads(line) for line in DATASET.read_text(encoding='utf8').splitlines()]
    cases = [c for c in cases if args.split == 'all' or c['split'] == args.split]
    store = GraphStore()
    rows, seconds = [], {arm: 0.0 for arm in args.arms}
    try:
        for case in cases:
            gold = case['contexts'][0]['uid']
            row = {'id': case['id'], 'category': case['category'], 'gold': gold}
            for arm in args.arms:
                start = time.perf_counter()
                row[arm] = rank_of(retrieve(store, arm, case['question'], args.rerank_model), gold)
                seconds[arm] += time.perf_counter()-start
            rows.append(row)
    finally:
        store.close()
    report = {'dataset': DATASET.name, 'split': args.split, 'top': vector.TOP, 'candidates': vector.CANDIDATES,
              'rrf_k': vector.RRF_K, 'rerank_model': args.rerank_model, 'arms': {}, 'by_category': {}, 'rows': rows}
    for arm in args.arms:
        report['arms'][arm] = {**summary([r[arm] for r in rows]),
                               'ms_per_query': round(1000*seconds[arm]/max(len(rows), 1), 1)}
        for category in sorted({r['category'] for r in rows}):
            report['by_category'].setdefault(category, {})[arm] = summary(
                [r[arm] for r in rows if r['category'] == category])
    print(json.dumps({k: report[k] for k in ('split', 'arms', 'by_category')}, indent=1))
    if args.output:
        with args.output.open('x', encoding='utf8') as stream:
            json.dump(report, stream, indent=1)


if __name__ == '__main__':
    main()
