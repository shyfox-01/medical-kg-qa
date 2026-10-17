"""Paired comparison of two systems on the same questions (D091).

Pass rates with Wilson 95% intervals, the discordant questions (passed by only one
system) and an exact two-sided McNemar test on them, overall and per group
(capability family for v3, category otherwise). No model calls.

    python -m eval.compare eval/runs/a_round1.jsonl eval/runs/b_round1.jsonl --names cloud local
"""

import argparse
import json
from collections import defaultdict
from math import comb
from pathlib import Path

from eval.run import wilson


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact binomial test that discordant questions split evenly."""
    n = only_a + only_b
    if not n:
        return 1.0
    tail = sum(comb(n, k) for k in range(min(only_a, only_b) + 1)) / 2 ** n
    return round(min(1.0, 2 * tail), 4)


def compare(a: dict[str, bool], b: dict[str, bool], groups: dict[str, str] | None = None) -> dict:
    ids = sorted(a.keys() & b.keys())
    buckets = defaultdict(list)
    for i in ids:
        buckets['all'].append(i)
        if groups:
            buckets[groups.get(i, 'other')].append(i)
    out = {}
    for name, members in buckets.items():
        pa, pb = sum(a[i] for i in members), sum(b[i] for i in members)
        only_a = [i for i in members if a[i] and not b[i]]
        only_b = [i for i in members if b[i] and not a[i]]
        out[name] = {'questions': len(members), 'a_passed': pa, 'b_passed': pb,
                     'a_ci95': wilson(pa, len(members)), 'b_ci95': wilson(pb, len(members)),
                     'only_a': len(only_a), 'only_b': len(only_b),
                     'mcnemar_p': mcnemar_exact(len(only_a), len(only_b)),
                     'only_a_ids': only_a, 'only_b_ids': only_b}
    return out


def load(path: Path) -> dict[str, bool]:
    return {r['id']: r['score']['passed'] for r in map(json.loads, path.read_text(encoding='utf8').splitlines())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('a')
    parser.add_argument('b')
    parser.add_argument('--names', nargs=2, default=['a', 'b'])
    parser.add_argument('--dataset', help='Dataset for grouping (capability family or category)')
    args = parser.parse_args()
    groups = None
    if args.dataset:
        cases = map(json.loads, Path(args.dataset).read_text(encoding='utf8').splitlines())
        groups = {c['id']: c['capability'].split('.')[0] if 'capability' in c else c['category'] for c in cases}
    result = compare(load(Path(args.a)), load(Path(args.b)), groups)
    na, nb = args.names
    print(f"{'group':22} {'n':>4} {na:>8} {nb:>8} {'only_'+na:>10} {'only_'+nb:>10} {'p':>7}")
    for name, r in sorted(result.items(), key=lambda item: (item[0] != 'all', item[0])):
        print(f"{name:22} {r['questions']:>4} {r['a_passed']:>8} {r['b_passed']:>8} {r['only_a']:>10} "
              f"{r['only_b']:>10} {r['mcnemar_p']:>7}")


if __name__ == '__main__':
    main()
