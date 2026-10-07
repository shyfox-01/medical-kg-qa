import json
from pathlib import Path

from medkg.qa.linker import Linker


def mentions(chunks: list[dict],linker: Linker,unlinked_path: Path) -> list[dict]:
    edges = []
    unlinked_path.parent.mkdir(parents=True,exist_ok=True)
    # Structured ABOUT anchors are always linked; lexical mentions add other known entities.
    for chunk in chunks:
        ids = set(chunk.get('about',[]))
        found,_ = linker.question_mentions(chunk['text'],exact_only=True)
        ids.update(c.uid for c in found if not c.ambiguous and c.label in ('Disease','Drug','Phenotype'))
        edges.extend({'a':chunk['uid'],'b':uid} for uid in sorted(ids))
    if not unlinked_path.exists():
        unlinked_path.write_text('',encoding='utf8')
    return edges


def record_unlinked(path: Path,mention: str,chunk_uid: str,reason: str) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf8') as stream:
        stream.write(json.dumps({'mention':mention,'chunk_uid':chunk_uid,'reason':reason})+'\n')
