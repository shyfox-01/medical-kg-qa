import json

import numpy as np

from medkg.config import ROOT
from medkg.embeddings import Embeddings


def main() -> None:
    processed = ROOT/'data/processed'
    entities = json.loads((processed/'entities.json').read_text(encoding='utf8'))
    aliases = [{'uid':e['uid'],'text':alias} for e in entities
               for alias in sorted({e['name'],*(e.get('synonyms') or [])})]
    old_index, old_vectors = {}, None
    if (processed/'alias_vectors.npy').exists() and (processed/'vector_aliases.json').exists():
        old = json.loads((processed/'vector_aliases.json').read_text(encoding='utf8'))
        if old==aliases:
            print(f'Cached {len(aliases)} alias embeddings')
            return
        old_index = {(a['uid'],a['text']):i for i,a in enumerate(old)}
        old_vectors = np.load(processed/'alias_vectors.npy',mmap_mode='r')
    embedder = Embeddings()
    result = np.empty((len(aliases),384),dtype=np.float32)
    missing = []
    for i,alias in enumerate(aliases):
        key = (alias['uid'],alias['text'])
        if key in old_index:
            result[i] = old_vectors[old_index[key]]
        else:
            missing.append(i)
    for start in range(0,len(missing),512):
        indexes = missing[start:start+512]
        result[indexes] = embedder.encode([aliases[i]['text'] for i in indexes])
        print(f'Embedded {min(start+512,len(missing))}/{len(missing)} new aliases',flush=True)
    if old_vectors is not None:
        old_vectors._mmap.close()
    np.save(processed/'alias_vectors.npy',result)
    (processed/'vector_aliases.json').write_text(json.dumps(aliases),encoding='utf8')


if __name__=='__main__':
    main()
