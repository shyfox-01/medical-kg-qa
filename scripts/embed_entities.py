import json

import numpy as np

from medkg.config import ROOT
from medkg.embeddings import Embeddings


def main() -> None:
    processed = ROOT/'data/processed'
    entities = json.loads((processed/'entities.json').read_text())
    aliases = [{'uid':e['uid'],'text':alias} for e in entities
               for alias in sorted({e['name'],*(e.get('synonyms') or [])})]
    if (processed/'alias_vectors.npy').exists() and (processed/'vector_aliases.json').exists():
        old = json.loads((processed/'vector_aliases.json').read_text())
        if old==aliases:
            print(f'Cached {len(aliases)} alias embeddings')
            return
    embedder = Embeddings()
    parts = []
    for i in range(0,len(aliases),512):
        parts.append(embedder.encode([a['text'] for a in aliases[i:i+512]]))
        print(f'Embedded {min(i+512,len(aliases))}/{len(aliases)} aliases',flush=True)
    np.save(processed/'alias_vectors.npy',np.concatenate(parts))
    (processed/'vector_aliases.json').write_text(json.dumps(aliases),encoding='utf8')


if __name__=='__main__':
    main()
