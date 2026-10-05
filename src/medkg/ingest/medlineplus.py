import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from medkg.ingest.chunking import chunks
from medkg.ingest.ontology import mondo_ids
from medkg.qa.linker import normalize


def parse(path: Path,entities: list[dict],mondo: dict,retrieved_at: str) -> tuple[list,list]:
    mesh,names = {},{}
    for entity in entities:
        if entity['label']!='Disease':
            continue
        for alias in [entity['name'],*entity.get('synonyms',[])]:
            names.setdefault(normalize(alias),set()).add(entity['uid'])
        identifier = entity['uid'].split(':',1)[1]
        for term_id in mondo_ids(identifier):
            if term_id in mondo:
                for xref in mondo[term_id].xrefs:
                    if xref.upper().startswith(('MESH:','MSH:')):
                        mesh.setdefault(xref.split(':',1)[1],set()).add(entity['uid'])
    documents,all_chunks = [],[]
    for topic in ET.parse(path).getroot().findall('health-topic'):
        if topic.get('language','').casefold()!='english':
            continue
        about = set()
        for descriptor in topic.findall('.//mesh-heading/descriptor'):
            about.update(mesh.get(descriptor.get('id',''),set()))
        if not about:
            about.update(names.get(normalize(topic.get('title','')),set()))
            for alias in topic.findall('also-called'):
                about.update(names.get(normalize(alias.text or ''),set()))
        summary = topic.find('full-summary')
        text = html.unescape(''.join(summary.itertext())) if summary is not None else ''
        text = re.sub(r'<[^>]+>',' ',text)
        document = {'uid':'medlineplus:'+topic.get('id',''),'source':'medlineplus',
                    'url':topic.get('url',''),'title':topic.get('title',''),
                    'name':topic.get('title',''),'synonyms':[],'retrieved_at':retrieved_at,
                    'about':sorted(about)}
        documents.append(document)
        all_chunks.extend(chunks(document,{'summary':text}))
    return documents,all_chunks
