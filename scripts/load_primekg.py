import argparse
import json

from medkg.config import ROOT
from medkg.graph.store import GraphStore
from medkg.ingest.ontology import load_obo
from medkg.ingest.primekg import read_graph


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    raw = ROOT / 'data/raw'
    nodes, edges, report = read_graph(raw/'kg.csv', load_obo(raw/'mondo.obo'), load_obo(raw/'hp.obo'))
    if not args.dry_run:
        store = GraphStore()
        try:
            store.create_schema()
            store.load(nodes, edges)
            assert store.counts() == {k: report[k] for k in ('nodes', 'relations')}
        finally:
            store.close()
    processed = ROOT/'data/processed'
    processed.mkdir(parents=True, exist_ok=True)
    (processed/'entities.json').write_text(json.dumps(nodes), encoding='utf8')
    (processed/'primekg_counts.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
