"""Synonym enrichment rules (decision D049), using fictional records only."""

import io

from medkg_data import synonyms as S

MESH = b'''<?xml version="1.0"?>
<DescriptorRecordSet>
 <DescriptorRecord><DescriptorUI>D900001</DescriptorUI>
  <DescriptorName><String>Asterol</String></DescriptorName>
  <TreeNumberList><TreeNumber>D02.001</TreeNumber></TreeNumberList>
  <ConceptList>
   <Concept PreferredConceptYN="Y"><TermList><Term><String>Asterol</String></Term>
    <Term><String>Asteric Acid</String></Term><Term><String>Acid, Asteric</String></Term></TermList></Concept>
   <Concept PreferredConceptYN="N"><ConceptRelationList><ConceptRelation RelationName="NRW"/></ConceptRelationList>
    <TermList><Term><String>Starbrand</String></Term></TermList></Concept>
   <Concept PreferredConceptYN="N"><ConceptRelationList><ConceptRelation RelationName="REL"/></ConceptRelationList>
    <TermList><Term><String>Asterol Combo</String></Term></TermList></Concept>
  </ConceptList></DescriptorRecord>
 <DescriptorRecord><DescriptorUI>D900002</DescriptorUI>
  <DescriptorName><String>Orion Fever</String></DescriptorName>
  <TreeNumberList><TreeNumber>C01.001</TreeNumber></TreeNumberList>
  <ConceptList>
   <Concept PreferredConceptYN="Y"><TermList><Term><String>Orion Fever</String></Term>
    <Term><String>Star Sickness</String></Term></TermList></Concept>
   <Concept PreferredConceptYN="N"><ConceptRelationList><ConceptRelation RelationName="NRW"/></ConceptRelationList>
    <TermList><Term><String>Vela Syndrome</String></Term></TermList></Concept>
  </ConceptList></DescriptorRecord>
 <DescriptorRecord><DescriptorUI>D900003</DescriptorUI>
  <DescriptorName><String>Brinex Citrate</String></DescriptorName>
  <TreeNumberList><TreeNumber>D03.001</TreeNumber></TreeNumberList>
  <ConceptList>
   <Concept PreferredConceptYN="Y"><TermList><Term><String>Brinex Citrate</String></Term></TermList></Concept>
   <Concept PreferredConceptYN="N"><ConceptRelationList><ConceptRelation RelationName="NRW"/></ConceptRelationList>
    <TermList><Term><String>Brinexa</String></Term></TermList></Concept>
  </ConceptList></DescriptorRecord>
</DescriptorRecordSet>'''

ENTITIES = [
    {'uid':'DrugBank:DB90001','label':'Drug','name':'Asteric acid','synonyms':[]},
    {'uid':'DrugBank:DB90002','label':'Drug','name':'Brinex','synonyms':[]},
    {'uid':'MONDO:9000001','label':'Disease','name':'orion fever','synonyms':[]},
    {'uid':'HPO:1','label':'Phenotype','name':'Orion fever','synonyms':[]},
    {'uid':'HPO:2','label':'Phenotype','name':'Star sickness','synonyms':[]},
]
OBO = ('[Term]\nid: MONDO:9000001\nxref: MESH:D900002 {source="MONDO:equivalentTo"}\n'
       '[Term]\nid: MONDO:9000002\nxref: MESH:D900003 {source="MONDO:relatedTo"}\n')


def descriptors():
    return list(S.parse_mesh(io.BytesIO(MESH)))


def test_drug_terms_take_preferred_and_narrower_but_not_related_or_inverted():
    proposals = S.mesh_drug_proposals(descriptors(),ENTITIES)
    asterol = {alias for uid,alias,_ in proposals if uid=='DrugBank:DB90001'}
    assert asterol=={'Asterol','Asteric Acid','Starbrand'}


def test_salt_descriptor_matches_the_active_moiety():
    proposals = S.mesh_drug_proposals(descriptors(),ENTITIES)
    assert ('DrugBank:DB90002','Brinexa','mesh:D900003') in proposals


def test_diseases_use_equivalent_xrefs_and_preferred_terms_only():
    proposals = S.mesh_disease_proposals(descriptors(),ENTITIES,S.mondo_mesh_equivalents(OBO))
    assert {alias for _,alias,_ in proposals}=={'Orion Fever','Star Sickness'}
    assert S.mondo_mesh_equivalents(OBO)=={'MONDO:9000001':{'D900002'}}


def test_merge_never_creates_same_label_or_unrelated_cross_label_readings():
    proposals = [
        ('DrugBank:DB90001','Asterol','mesh'),            # new
        ('DrugBank:DB90001','Asteric acid','mesh'),       # already present
        ('DrugBank:DB90002','Asterol','mesh'),            # same alias for two drugs
        ('DrugBank:DB90001','Brinex','mesh'),             # owned by another drug
        ('MONDO:9000001','Star Sickness','mesh'),         # owned by an unrelated phenotype
        ('DrugBank:DB90001','was','mesh'),                # common English word
    ]
    proposals = [p for p in proposals if S.usable(p[1])]
    additions,skipped = S.merge_synonyms(ENTITIES,proposals)
    assert additions==[]
    assert skipped=={'already_present':1,'used_by_other_entity_same_label':1,
                     'unrelated_entity_other_label':1,'proposed_for_several_entities':2}


def test_merge_allows_cross_label_sharing_within_a_same_name_pair_and_is_idempotent():
    entities = [dict(e) for e in ENTITIES]
    proposals = [('MONDO:9000001','Orion Pyrexia','mesh'),('HPO:1','Orion Pyrexia','hpo')]
    additions,_ = S.merge_synonyms(entities,proposals)
    assert {(a['uid'],a['alias']) for a in additions}=={('MONDO:9000001','Orion Pyrexia'),
                                                       ('HPO:1','Orion Pyrexia')}
    enriched = S.apply_additions(entities,additions)
    assert S.merge_synonyms(enriched,proposals)[0]==[]


def test_drugbank_vocabulary_joins_by_id(tmp_path):
    path = tmp_path/'drugbank vocabulary.csv'
    path.write_text('DrugBank ID,Common name,Synonyms\nDB90002,Brinex,Brinexate | BRX | Brinex\n',
                    encoding='utf8')
    proposals = S.drugbank_proposals(S.read_drugbank_vocabulary(path),ENTITIES)
    assert {alias for _,alias,_ in proposals}=={'Brinex','Brinexate','BRX'}
