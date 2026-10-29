"""Star-map coordinates for the web page (D128), from the catalog, the PrimeKG CSV and the ontologies.

    python -m scripts.build_starmap

Writes data/processed/starmap.json.gz (served at GET /starmap) and starmap_uids.json (the uid of
each point, read by the API to place what a question finds). About two minutes.
"""

import gzip
import json

from medkg.config import ROOT
from medkg_data.ontology import load_obo
from medkg_data.primekg import read_graph
from medkg_data.starmap import build


def main() -> None:
    raw, processed = ROOT/'data/raw', ROOT/'data/processed'
    catalog = json.loads((processed/'entities.json').read_text(encoding='utf8'))
    hp, mondo = load_obo(raw/'hp.obo'), load_obo(raw/'mondo.obo')
    _, edges, _ = read_graph(raw/'kg.csv', mondo, hp)
    payload, uids = build(catalog, edges, hp, mondo)
    (processed/'starmap.json.gz').write_bytes(gzip.compress(json.dumps(payload).encode('utf8'), mtime=0))
    (processed/'starmap_uids.json').write_text(json.dumps(uids), encoding='utf8')
    print(f'{len(uids)} points, {len(payload["areas"])} region centres -> {processed/"starmap.json.gz"}')


if __name__ == '__main__':
    main()
