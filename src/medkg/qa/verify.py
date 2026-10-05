import json

from medkg.qa.answer import messages
from medkg.qa.linker import normalize


def entities_in_text(text: str,linker) -> set[str]:
    words = normalize(text).split()
    found,occupied = set(),set()
    for size in range(min(12,len(words)),0,-1):
        for start in range(len(words)-size+1):
            positions = set(range(start,start+size))
            if occupied & positions:
                continue
            alias = ' '.join(words[start:start+size])
            if len(alias)>=3 and alias in linker.aliases:
                found.update(linker.aliases[alias])
                occupied |= positions
    return found


def unsupported(answer: str,rows: list[dict],linker) -> set[str]:
    supported = entities_in_text(json.dumps(rows),linker) | {r['uid'] for r in rows if r.get('uid')}
    return entities_in_text(answer,linker)-supported


def verify_answer(llm,question: str,answer: str,rows: list[dict],linker) -> str:
    missing = unsupported(answer,rows,linker)
    if not missing:
        return answer
    names = [linker.entities[uid]['name'] for uid in sorted(missing)]
    revised = llm.chat(messages(question,rows,'Remove unsupported entities: '+json.dumps(names)))
    missing = unsupported(revised,rows,linker)
    if not missing:
        return revised
    kept = [line for line in revised.splitlines() if not (entities_in_text(line,linker) & missing)]
    return '\n'.join(kept)+'\n\nSome entries were removed because their entities were not supported by retrieved evidence.'
