from pathlib import Path

import pytest

from medkg.ingest.chunking import chunks
from medkg.ingest.extract import Relation, link_relations
from medkg.ingest.medlineplus import parse
from medkg.ingest.ontology import parse_obo
from medkg.qa.linker import Linker
from medkg.qa.verify import verify_answer


def test_section_windows_overlap_and_boundary():
    document = {'uid':'test:doc','title':'Fictional Topic','source':'medlineplus','url':'https://example.test'}
    results = chunks(document,{'first':' '.join(map(str,range(620))),'second':'other section'})
    assert [len(c['text'].split()) for c in results]==[300,300,120,2]
    assert results[0]['text'].split()[-50:]==results[1]['text'].split()[:50]
    assert results[-1]['section']=='second'
    with pytest.raises(ValueError):
        chunks(document,{},size=10,overlap=10)


def test_mesh_link_and_english_filter(tmp_path: Path):
    path = tmp_path/'topics.xml'
    path.write_text('<health-topics><health-topic id="1" title="Public topic" language="English" url="https://example.test/topic"><mesh-heading><descriptor id="D1">test</descriptor></mesh-heading><full-summary>&lt;p&gt;Fictional text.&lt;/p&gt;</full-summary></health-topic><health-topic id="2" title="Otro" language="Spanish" /></health-topics>',encoding='utf8')
    entities = [{'uid':'MONDO:1','name':'Fictional Disease','label':'Disease','synonyms':[]}]
    terms = parse_obo('[Term]\nid: MONDO:0000001\nname: disease\nxref: MESH:D1\n')
    documents,results = parse(path,entities,terms,'2026-10-05')
    assert len(documents)==1 and documents[0]['about']==['MONDO:1']
    assert results[0]['text']=='Fictional text.'


def test_extraction_never_creates_unknown_nodes(tmp_path):
    entities = [{'uid':'drug:a','name':'Fictional Compound Alpha','label':'Drug','synonyms':[]},
                {'uid':'drug:b','name':'Fictional Compound Beta','label':'Drug','synonyms':[]}]
    relation = Relation(subject='Fictional Compound Alpha',object='Unknown Substance',
                        relation='INTERACTS_WITH',evidence='supported quote',confidence=0.8)
    edges = link_relations([relation],{'uid':'chunk:1'},Linker(entities),tmp_path/'unlinked.jsonl')
    assert edges==[] and 'Unknown Substance' in (tmp_path/'unlinked.jsonl').read_text()


def test_verifier_retries_once_then_removes_unsupported_item():
    entities = [{'uid':'a','name':'Fictional Alpha','label':'Drug','synonyms':[]},
                {'uid':'b','name':'Fictional Beta','label':'Drug','synonyms':[]}]
    class Model:
        calls = 0
        def chat(self,messages):
            self.calls += 1
            return '- Fictional Alpha\n- Fictional Beta'
    model = Model()
    result = verify_answer(model,'List entities','Fictional Beta',[{'uid':'a','name':'Fictional Alpha'}],Linker(entities))
    assert model.calls==1
    assert 'Fictional Alpha' in result and 'Fictional Beta' not in result
    assert 'removed' in result
