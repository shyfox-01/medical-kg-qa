"""Recoverable assertion publication across database and local export boundaries."""

import hashlib
import json
from pathlib import Path

from medkg.ingest.reconcile import reconcile_edges


def digest(path: Path) -> str | None:
    if not path.exists():
        return None
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def atomic_json(path: Path,value: dict) -> None:
    temporary = path.with_suffix(path.suffix+'.pending')
    temporary.write_text(json.dumps(value,indent=2),encoding='utf8')
    temporary.replace(path)


def publish_assertions(store,selected: set[str],retained: list[dict],target: Path,work: Path) -> dict:
    operation = {'selected':sorted(selected),'retained':retained,'target':str(target.resolve())}
    key = hashlib.sha256(json.dumps(operation,sort_keys=True).encode()).hexdigest()
    current = digest(target)
    matches = []
    for journal in sorted(work.glob('*/manifest.json')):
        prior = json.loads(journal.read_text(encoding='utf8'))
        if prior['operation_sha256']==key:
            staged = journal.parent/'export.jsonl'
            before = journal.parent/'before.jsonl'
            if digest(staged)!=prior['staged_sha256'] or (prior['before_sha256'] is not None and
                    digest(before)!=prior['before_sha256']):
                raise RuntimeError('Publication journal integrity failure')
            matches.append((journal.parent,prior))
    incomplete = [(d,s) for d,s in matches if s['phase']!='complete']
    if len(incomplete)>1:
        raise RuntimeError('Multiple incomplete publication generations')
    if incomplete:
        directory = incomplete[0][0]
    elif any(s['staged_sha256']==current for _,s in matches):
        directory = next(d for d,s in matches if s['staged_sha256']==current)
    else:
        # A different completed sample can legitimately change outside evidence.
        # Keep its export and create a separate recovery generation for this input.
        generation = hashlib.sha256((key+str(current)).encode()).hexdigest() if matches else key
        directory = work/generation
    directory.mkdir(parents=True,exist_ok=True)
    manifest,staged = directory/'manifest.json',directory/'export.jsonl'
    if manifest.exists():
        state = json.loads(manifest.read_text(encoding='utf8'))
        if state['operation_sha256']!=key or digest(staged)!=state['staged_sha256']:
            raise RuntimeError('Publication journal integrity failure')
        current = digest(target)
        if state['phase']=='complete':
            if current!=state['staged_sha256']:
                raise RuntimeError('Completed publication drifted; inspect before refreshing')
            # File equality alone is not database equality: replay the scoped,
            # idempotent transaction to reconcile restored/drifted database state.
            store.reconcile_extracted(selected,retained)
            return state
        if current not in (state['before_sha256'],state['staged_sha256']):
            raise RuntimeError('Export changed during incomplete publication')
    else:
        try:
            previous = [json.loads(line) for line in target.read_text(encoding='utf8').splitlines()] if target.exists() else []
            valid = all(isinstance(e,dict) and all(isinstance(e.get(k),str) and e[k]
                for k in ('a','b','type','source')) and isinstance(e.get('evidence'),list)
                and e['evidence'] and all(isinstance(uid,str) and uid for uid in e['evidence'])
                for e in previous)
        except (ValueError,UnicodeError):
            valid = False
        if not valid:
            raise RuntimeError('Completed publication drifted or export is invalid; inspect before refreshing')
        current = reconcile_edges(previous,selected,retained)
        if target.exists():
            (directory/'before.jsonl').write_bytes(target.read_bytes())
        staged.write_text(''.join(json.dumps(e)+'\n' for e in current),encoding='utf8')
        state = {'operation_sha256':key,'phase':'prepared','before_sha256':digest(target),
                 'staged_sha256':digest(staged),'selected_chunks':len(selected),
                 'retained_selected_assertions':len(retained),'exported_assertions':len(current)}
        atomic_json(manifest,state)
    store.reconcile_extracted(selected,retained)
    state['phase'] = 'graph_applied'
    atomic_json(manifest,state)
    temporary = target.with_suffix(target.suffix+'.pending')
    temporary.write_bytes(staged.read_bytes())
    if digest(temporary)!=state['staged_sha256']:
        raise RuntimeError('Staged export integrity failure')
    temporary.replace(target)
    state['phase'] = 'complete'
    atomic_json(manifest,state)
    return state
