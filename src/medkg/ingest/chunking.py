"""Section-aware windows of approximately 300 words with 50-word overlap."""


def chunks(document: dict,sections: dict[str,str],size: int = 300,overlap: int = 50) -> list[dict]:
    if not 0<=overlap<size:
        raise ValueError('Overlap must be smaller than window size')
    result = []
    for section,text in sections.items():
        words = text.split()
        for start in range(0,len(words),size-overlap):
            piece = words[start:start+size]
            if not piece:
                continue
            order = len(result)
            result.append({'uid':f"{document['uid']}:{section}:{start}",'name':document['title'],
                'synonyms':[],'text':' '.join(piece),'section':section,'order':order,
                'document_uid':document['uid'],'source':document['source'],'url':document['url'],
                'about':document.get('about',[])})
            if start+size>=len(words):
                break
    return result
