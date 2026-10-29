"""Static schema; only trusted ingestion can create nodes, relations or indexes."""

LABELS = ('Disease', 'Drug', 'Phenotype', 'Gene', 'Document', 'Chunk')
RELATIONS = ('INDICATED_FOR', 'CONTRAINDICATED_FOR', 'OFF_LABEL_FOR', 'INTERACTS_WITH',
             'HAS_SIDE_EFFECT', 'HAS_PHENOTYPE', 'ASSOCIATED_WITH', 'TARGETS', 'SUBTYPE_OF',
             'HAS_CHUNK', 'MENTIONS', 'ABOUT')
PROPERTIES = {'uid', 'name', 'synonyms', 'source', 'kind', 'evidence', 'confidence',
              'extractor_version', 'conflict', 'url', 'title', 'retrieved_at', 'text',
              'section', 'order', 'embedding'}
# The labels each relation goes from and to, as in SCHEMA_PROMPT.
ENDS = {'INDICATED_FOR': ('Drug', 'Disease'), 'CONTRAINDICATED_FOR': ('Drug', 'Disease'),
        'OFF_LABEL_FOR': ('Drug', 'Disease'), 'INTERACTS_WITH': ('Drug', 'Drug'),
        'HAS_SIDE_EFFECT': ('Drug', 'Phenotype'), 'HAS_PHENOTYPE': ('Disease', 'Phenotype'),
        'ASSOCIATED_WITH': ('Disease', 'Gene'), 'TARGETS': ('Drug', 'Gene'), 'SUBTYPE_OF': ('Disease', 'Disease')}
SCHEMA_PROMPT = '''
Nodes: Disease, Drug, Phenotype, Gene. Each has uid, name, synonyms.
(Drug)-[INDICATED_FOR|CONTRAINDICATED_FOR|OFF_LABEL_FOR]->(Disease)
(Drug)-[INTERACTS_WITH]-(Drug), undirected query
(Drug)-[HAS_SIDE_EFFECT]->(Phenotype)
(Disease)-[HAS_PHENOTYPE]->(Phenotype)
(Disease)-[ASSOCIATED_WITH]->(Gene)
(Drug)-[TARGETS {kind}]->(Gene)
(Disease)-[SUBTYPE_OF]->(Disease), child to parent
(Document)-[HAS_CHUNK]->(Chunk), (Document)-[ABOUT]->(Disease|Drug)
(Chunk)-[MENTIONS]->(Disease|Drug|Phenotype)
Edges carry source and optionally evidence/conflict. Return target.uid AS uid,
target.name AS name, r.source AS source and r.conflict AS conflict.
Use uid parameters for linked anchors. No procedures, writes, unbounded paths.
'''


def statements() -> list[str]:
    result = []
    for label in LABELS:
        result += [f'CREATE CONSTRAINT uid_{label} IF NOT EXISTS FOR (n:{label}) REQUIRE n.uid IS UNIQUE',
                   f'CREATE FULLTEXT INDEX ft_{label} IF NOT EXISTS FOR (n:{label}) '
                   "ON EACH [n.name, n.synonyms] OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}}"]
    result.append('CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS FOR (n:Chunk) '
                  'ON n.embedding OPTIONS {indexConfig: {`vector.dimensions`: 384, '
                  "`vector.similarity_function`: 'cosine'}}")
    result.append('CREATE FULLTEXT INDEX ft_chunk_text IF NOT EXISTS FOR (n:Chunk) ON EACH [n.text] '
                  "OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}}")
    return result
