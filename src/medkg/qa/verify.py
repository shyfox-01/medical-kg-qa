import json
import re

from medkg.qa.answer import messages
from medkg.qa.linker import normalize
from medkg_data.lexicon import GENERIC_ANCHORS, ITEM_BREAK, ambiguous_word, crosses_break, list_breaks


def entities_in_text(text: str,linker) -> set[str]:
    words = normalize(text).split()
    original = re.findall(r'\w+',text)
    breaks,items = list_breaks(text),list_breaks(text,ITEM_BREAK)
    found,occupied = set(),set()
    for size in linker.alias_sizes:
        if size>len(words):
            continue
        for start in range(len(words)-size+1):
            positions = set(range(start,start+size))
            if occupied & positions:
                continue
            alias = ' '.join(words[start:start+size])
            if alias in GENERIC_ANCHORS or ambiguous_word(alias,' '.join(original[start:start+size])):
                continue
            if crosses_break(start,size,items):
                continue   # a new list item ends every name, also one spelt with a comma (D126)
            if crosses_break(start,size,breaks) and alias in linker.aliases and alias not in getattr(linker,'separated',()):
                continue   # "A, B" names two entities, not the alias "A B" of a third
            if len(alias)>=3 and alias in linker.aliases:
                uids = set(linker.aliases[alias])
                written = ' '.join(original[start:start+size]).casefold()
                owners = uids & getattr(linker,'written_owners',{}).get(written,set())
                found.update(owners if len(uids)>1 and owners else uids)
                occupied |= positions
            elif alias in linker.quarantined_keys:
                # Match the linker's whole-span quarantine: a rejected name must
                # not fall through to a shorter retained entity alias inside it.
                occupied |= positions
    return found


def unsupported(answer: str,rows: list[dict],linker) -> set[str]:
    supported = entities_in_text(json.dumps(rows),linker) | {r['uid'] for r in rows if r.get('uid')}
    return entities_in_text(answer,linker)-supported


def verify_answer(llm,question: str,answer: str,rows: list[dict],linker,queries: list[dict] | None = None,
                  entities: list[dict] | None = None, caution: str = '') -> str:
    missing = unsupported(answer,rows,linker)
    if not missing:
        return answer
    names = [linker.entities[uid]['name'] for uid in sorted(missing)]
    revised = llm.chat(messages(question,rows,'Remove unsupported entities: '+json.dumps(names),queries,entities,
                                caution))
    missing = unsupported(revised,rows,linker)
    if not missing:
        return revised
    kept = [line for line in revised.splitlines() if not (entities_in_text(line,linker) & missing)]
    return '\n'.join(kept)+'\n\nSome entries were removed because their entities were not supported by retrieved evidence.'
