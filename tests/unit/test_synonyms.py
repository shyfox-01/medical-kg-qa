"""Synonym enrichment rules (decision D049), using fictional records only."""

import io

import pytest

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


def test_apply_additions_routes_by_source_without_mutating_existing_aliases():
    entities = [dict(ENTITIES[0], synonyms=['Asterate'], exact_synonyms=['Oldbrand']),
                ENTITIES[1]]
    additions = [
        {'uid': 'DrugBank:DB90001', 'alias': 'Newbrand', 'source': 'rxnorm:20'},
        {'uid': 'DrugBank:DB90001', 'alias': 'Asterol', 'source': 'mesh:D900001'},
        {'uid': 'DrugBank:DB90001', 'alias': 'Starbrand', 'source': 'openfda:1'},
    ]
    enriched = S.apply_additions(entities, additions)
    assert enriched[0]['synonyms'] == ['Asterate', 'Asterol', 'Starbrand']
    assert enriched[0]['exact_synonyms'] == ['Oldbrand', 'Newbrand']
    assert entities[0]['synonyms'] == ['Asterate']
    assert entities[0]['exact_synonyms'] == ['Oldbrand']
    assert enriched[1] is entities[1]


@pytest.mark.parametrize('source', ['rxnorm:20', 'mesh:D900001'])
@pytest.mark.parametrize('field_name', ['synonyms', 'exact_synonyms'])
def test_merge_rejects_alias_already_owned_in_either_field(source, field_name):
    entities = [dict(ENTITIES[0], **{field_name: ['Starbrand']})]
    additions, skipped = S.merge_synonyms(
        entities, [('DrugBank:DB90001', 'STARBRAND', source)])
    assert additions == []
    assert skipped == {'already_present': 1}


def test_rxnorm_merge_then_apply_is_idempotent_with_exact_aliases():
    proposals = [('DrugBank:DB90001', 'Starbrand', 'rxnorm:20')]
    additions, skipped = S.merge_synonyms(ENTITIES, proposals)
    assert len(additions) == 1 and skipped == {}
    enriched = S.apply_additions(ENTITIES, additions)
    assert enriched[0]['synonyms'] == []
    assert enriched[0]['exact_synonyms'] == ['Starbrand']
    assert S.merge_synonyms(enriched, proposals) == ([], {'already_present': 1})


@pytest.mark.parametrize('source', ['rxnorm:20', 'mesh:D900001'])
def test_merge_counts_exact_aliases_for_same_and_cross_label_collisions(source):
    entities = [dict(e, exact_synonyms=['Starbrand']) if e['uid'] == 'DrugBank:DB90001'
                else e for e in ENTITIES]
    additions, skipped = S.merge_synonyms(entities, [
        ('DrugBank:DB90002', 'Starbrand', source),
        ('MONDO:9000001', 'Starbrand', source),
    ])
    assert additions == []
    assert skipped == {'used_by_other_entity_same_label': 1, 'unrelated_entity_other_label': 1}


def test_drugbank_vocabulary_joins_by_id(tmp_path):
    path = tmp_path/'drugbank vocabulary.csv'
    path.write_text('DrugBank ID,Common name,Synonyms\nDB90002,Brinex,Brinexate | BRX | Brinex\n',
                    encoding='utf8')
    proposals = S.drugbank_proposals(S.read_drugbank_vocabulary(path),ENTITIES)
    assert {alias for _,alias,_ in proposals}=={'Brinex','Brinexate','BRX'}


def label(identifier,brand,generics,substances=None):
    return {'id':identifier,'openfda':{'brand_name':[brand],'generic_name':generics,
                                     'product_type':['HUMAN PRESCRIPTION DRUG'],
                                     'substance_name':substances or []}}


def test_cached_fda_aliases_require_all_ingredients_and_ignore_requested_uid():
    records = [{'drug_uid':'DrugBank:DB90001','results':[
        label('one','Brinexa',['Brinex citrate'],['Brinex']),
        label('two','Mixedbrand',['Brinex','Asteric acid']),
        label('three','Unresolvedbrand',['Brinex'],['Unknown ingredient']),
        label('four','Emptybrand',[]),
    ]}]
    assert S.cached_fda_proposals(records,ENTITIES)==[
        ('DrugBank:DB90002','Brinexa','openfda:one')]


def test_cached_fda_ingredient_matching_accepts_exact_only_aliases():
    entities = [dict(ENTITIES[1], exact_synonyms=['Brinexate'])]
    records = [{'results': [label('one', 'Brinexa', ['Brinexate'])]}]
    assert S.cached_fda_proposals(records, entities) == [
        ('DrugBank:DB90002', 'Brinexa', 'openfda:one')]


@pytest.mark.parametrize('field_name', ['synonyms', 'exact_synonyms'])
def test_cached_fda_ingredient_matching_rejects_quarantined_aliases(field_name):
    entities = [{'uid': 'DrugBank:DB09111', 'label': 'Drug', 'name': 'Pentastarch',
                 field_name: ['Hetastarch']}]
    records = [{'results': [label('one', 'Fictionalbrand', ['Hetastarch'])]}]
    assert S.cached_fda_proposals(records, entities) == []


def test_brand_on_an_unresolved_product_is_vetoed_across_all_records():
    records = [{'results':[label('one','Starbrand',['Brinex'])]},
               {'results':[label('two','Starbrand',['Unknown substance'])]}]
    assert S.cached_fda_proposals(records,ENTITIES)==[]
    records[-1]['results'][0]['openfda']['generic_name']=['Asteric acid']
    assert S.merge_synonyms(ENTITIES,S.cached_fda_proposals(records,ENTITIES))[0]==[]


def test_medline_aliases_need_exact_english_disease_title_not_broad_topic(tmp_path):
    path = tmp_path/'topics.xml'
    path.write_text('''<health-topics>
      <health-topic id="1" language="English" title="Orion Fever">
        <also-called>Orion Pyrexia</also-called></health-topic>
      <health-topic id="2" language="Spanish" title="Orion Fever">
        <also-called>Excluded foreign name</also-called></health-topic>
      <health-topic id="3" language="English" title="Broad Fever Topic">
        <also-called>Orion Fever</also-called><also-called>Different Disease</also-called>
      </health-topic></health-topics>''',encoding='utf8')
    assert S.medlineplus_proposals(path,ENTITIES)==[
        ('MONDO:9000001','Orion Pyrexia','medlineplus:1')]


def test_new_alias_cannot_join_unrelated_labels_within_one_batch():
    proposals = [('DrugBank:DB90001','Starbrand','openfda:1'),
                 ('MONDO:9000001','Starbrand','medlineplus:2')]
    additions,skipped = S.merge_synonyms(ENTITIES,proposals)
    assert additions==[] and skipped=={'proposed_for_unrelated_labels':2}


@pytest.mark.parametrize('field_name', ['synonyms', 'exact_synonyms'])
def test_mesh_narrower_drug_does_not_acquire_a_whole_chemical_class(field_name):
    descriptor = S.Descriptor('D999','Fictional Chemical Class',['D01'],
                              ['Fictional Chemical Class'],['Brinex'])
    assert S.mesh_drug_proposals([descriptor],ENTITIES)==[]
    enriched = [dict(e, **{field_name: ['Fictional Chemical Class']}) if e['name']=='Brinex' else e
                for e in ENTITIES]
    assert S.mesh_drug_proposals([descriptor],enriched)==[]


@pytest.mark.parametrize('field_name', ['synonyms', 'exact_synonyms'])
def test_consumer_title_does_not_join_through_an_existing_acronym(tmp_path, field_name):
    path = tmp_path/'topics.xml'
    path.write_text('<health-topics><health-topic id="1" language="English" title="RASH">'
                    '<also-called>Skin spots</also-called></health-topic></health-topics>')
    entity = {'uid':'MONDO:999','label':'Disease','name':'Rare Astral Syndrome',
              field_name:['RASH']}
    assert S.medlineplus_proposals(path,[entity])==[]


def test_otc_product_description_is_not_a_prescription_brand():
    row = label('one','Allergy Relief',['Brinex'])
    row['openfda']['product_type']=['HUMAN OTC DRUG']
    assert S.cached_fda_proposals([{'results':[row]}],ENTITIES)==[]
