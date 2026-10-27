"""MedlinePlus topic titles become lay names of one disease when two signals agree (D114)."""

from medkg_data.synonyms import medlineplus_title_proposals

ENTITIES = [
    {'uid': 'MONDO:5746', 'label': 'Disease', 'name': 'enterobiasis', 'synonyms': ['pinworm infection']},
    {'uid': 'MONDO:8638', 'label': 'Disease', 'name': 'varicose disease', 'synonyms': []},
    {'uid': 'MONDO:4975', 'label': 'Disease', 'name': 'asthma', 'synonyms': []},
    {'uid': 'MONDO:1', 'label': 'Disease', 'name': 'asbestosis', 'synonyms': []},
]
EQUIVALENTS = {'MONDO:0005746': {'D004751'}, 'MONDO:0008638': {'D014648'}, 'MONDO:0004975': {'D001249'},
               'MONDO:0000001': {'D001195'}}


def topic(title, meshes, also=()):
    headings = ''.join(f'<mesh-heading><descriptor id="{m}">x</descriptor></mesh-heading>' for m in meshes)
    called = ''.join(f'<also-called>{a}</also-called>' for a in also)
    return f'<health-topic title="{title}" id="{abs(hash(title)) % 10000}" language="English">{called}{headings}</health-topic>'


def proposals(tmp_path, *topics):
    path = tmp_path / 'medlineplus.xml'
    path.write_text('<health-topics>' + ''.join(topics) + '</health-topics>', encoding='utf8')
    return [(uid, title) for uid, title, _ in medlineplus_title_proposals(path, ENTITIES, EQUIVALENTS)]


def test_a_title_joins_the_one_disease_its_mesh_heading_means(tmp_path):
    found = proposals(tmp_path,
                      topic('Pinworms', ['D004751'], also=['Enterobiasis']),       # another name is the disease
                      topic('Varicose Veins', ['D014648', 'D999999']))             # shared stem; a non-disease heading
    assert found == [('MONDO:5746', 'Pinworms'), ('MONDO:8638', 'Varicose Veins')]


def test_population_prevention_substance_and_unrelated_titles_are_not_names(tmp_path):
    assert proposals(tmp_path,
                     topic('Asthma in Children', ['D001249']),
                     topic('How to Prevent Asthma', ['D001249']),
                     topic('Childhood Asthma Problems', ['D001249']),
                     topic('Asbestos', ['D001195']),                       # reviewed: a substance
                     topic('Breathing Trouble', ['D001249'])) == []        # no shared stem, no shared name
