"""Synonym enrichment from MeSH descriptors and the DrugBank vocabulary.

Pure functions shared by the enrichment script and tests. Proposals are
(uid, alias, source) triples; merge_synonyms() decides which become aliases.

* MeSH drugs (tree D): terms of the preferred concept and of narrower (NRW)
  concepts, which hold brand names and salts (Tylenol, Lipitor). Related (REL)
  concepts are often combination products and are skipped. A descriptor is used
  only when its terms match exactly one catalog Drug.
* MeSH diseases: preferred-concept terms only (narrower concepts can be other
  diseases), joined through MONDO xrefs annotated MONDO:equivalentTo.
* DrugBank vocabulary (CC0): synonyms joined by DrugBank id.
"""

import csv
import gzip
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from medkg_data.lexicon import COMMON_WORDS, GENERIC_ANCHORS, normalize
from medkg_data.ontology import mondo_ids

MAX_ALIAS_CHARS = 60

# Everyday names used to measure linking coverage (D049); v2 questions exclude them.
COVERAGE_PROBES = {
    'aspirin': 'Acetylsalicylic acid', 'tylenol': 'Acetaminophen', 'paracetamol': 'Acetaminophen',
    'advil': 'Ibuprofen', 'motrin': 'Ibuprofen', 'aleve': 'Naproxen', 'lipitor': 'Atorvastatin',
    'zocor': 'Simvastatin', 'glucophage': 'Metformin', 'coumadin': 'Warfarin', 'prozac': 'Fluoxetine',
    'zoloft': 'Sertraline', 'xanax': 'Alprazolam', 'valium': 'Diazepam', 'synthroid': 'Levothyroxine',
    'norvasc': 'Amlodipine', 'prilosec': 'Omeprazole', 'nexium': 'Esomeprazole',
    'benadryl': 'Diphenhydramine', 'claritin': 'Loratadine', 'zyrtec': 'Cetirizine',
    'plavix': 'Clopidogrel', 'lasix': 'Furosemide', 'viagra': 'Sildenafil', 'albuterol': 'Salbutamol',
    'ventolin': 'Salbutamol', 'amoxil': 'Amoxicillin', 'cipro': 'Ciprofloxacin', 'tamiflu': 'Oseltamivir',
    'high blood pressure': 'hypertensive disorder', 'heart attack': 'myocardial infarction',
    'flu': 'influenza', 'common cold': 'common cold', 'heartburn': 'heartburn',
    'high cholesterol': 'hypercholesterolemia', 'kidney stones': 'kidney stone',
    'pink eye': 'conjunctivitis', 'chickenpox': 'varicella', 'hay fever': 'allergic rhinitis',
    'lou gehrig disease': 'amyotrophic lateral sclerosis',
}



@dataclass
class Descriptor:
    ui: str
    name: str
    trees: list[str] = field(default_factory=list)
    preferred: list[str] = field(default_factory=list)
    narrower: list[str] = field(default_factory=list)


def parse_mesh(stream) -> Iterator[Descriptor]:
    """Stream DescriptorRecords from MeSH XML (a binary file object)."""
    for _, element in ET.iterparse(stream, events=('end',)):
        if element.tag != 'DescriptorRecord':
            continue
        record = Descriptor(element.findtext('DescriptorUI', ''),
                            element.findtext('DescriptorName/String', ''),
                            [t.text or '' for t in element.findall('TreeNumberList/TreeNumber')])
        for concept in element.findall('ConceptList/Concept'):
            terms = [t.findtext('String', '') for t in concept.findall('TermList/Term')]
            relations = {r.get('RelationName') for r in concept.findall('ConceptRelationList/ConceptRelation')}
            if concept.get('PreferredConceptYN') == 'Y':
                record.preferred += terms
            elif 'NRW' in relations and 'REL' not in relations:
                record.narrower += terms
        element.clear()
        yield record


def load_mesh(path: Path) -> list[Descriptor]:
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rb') as stream:
        return list(parse_mesh(stream))


def usable(term: str) -> bool:
    """Free-text aliases only: no inverted forms ("Pressure, High"), no long chemical names."""
    key = normalize(term)
    return (bool(term) and ',' not in term and len(term) <= MAX_ALIAS_CHARS and len(key) >= 3
            and key not in COMMON_WORDS and key not in GENERIC_ANCHORS)


def _index(entities: Iterable[dict], label: str) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        if entity['label'] == label:
            for alias in [entity['name'], *(entity.get('synonyms') or [])]:
                index[normalize(alias)].add(entity['uid'])
    return index


SALT = re.compile(r'\s+(?:citrate|hydrochloride|hcl|sodium|potassium|calcium|maleate|sulfate|'
                  r'mesylate|tartrate|acetate|phosphate|besylate|fumarate|succinate|bromide|'
                  r'chloride|hydrobromide|monohydrate|dihydrate|trihydrate)$', re.I)


def mesh_drug_proposals(descriptors: Iterable[Descriptor], entities: list[dict]) -> list[tuple]:
    drugs = _index(entities, 'Drug')
    proposals = []
    for d in descriptors:
        if not any(tree.startswith('D') for tree in d.trees):
            continue
        terms = [d.name, *d.preferred, *d.narrower]
        matched = set().union(*(drugs.get(normalize(t), set()) for t in terms))
        if not matched:
            # MeSH may index the salt ("Sildenafil Citrate", with Viagra) while the
            # catalog names the active moiety ("Sildenafil").
            matched = set().union(*(drugs.get(normalize(SALT.sub('', t)), set()) for t in terms))
        if len(matched) == 1:
            uid = matched.pop()
            proposals += [(uid, t, 'mesh:' + d.ui) for t in dict.fromkeys(terms) if usable(t)]
    return proposals


def mondo_mesh_equivalents(obo_text: str) -> dict[str, set[str]]:
    """MONDO term id -> MeSH descriptor ids for xrefs annotated MONDO:equivalentTo."""
    result: dict[str, set[str]] = defaultdict(set)
    term = None
    for line in obo_text.splitlines():
        if line.startswith('id: '):
            term = line[4:].strip()
        elif term and line.startswith('xref: MESH:') and 'MONDO:equivalentTo' in line:
            result[term].add(line.split()[1].split(':', 1)[1])
    return result


def mesh_disease_proposals(descriptors: Iterable[Descriptor], entities: list[dict],
                           equivalents: dict[str, set[str]]) -> list[tuple]:
    by_mesh: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        if entity['label'] != 'Disease':
            continue
        for term in mondo_ids(entity['uid'].split(':', 1)[1]):
            for ui in equivalents.get(term, ()):
                by_mesh[ui].add(entity['uid'])
    proposals = []
    for d in descriptors:
        uids = by_mesh.get(d.ui, set())
        if len(uids) == 1:
            uid = next(iter(uids))
            proposals += [(uid, t, 'mesh:' + d.ui) for t in dict.fromkeys([d.name, *d.preferred]) if usable(t)]
    return proposals


def read_drugbank_vocabulary(path: Path) -> list[dict]:
    """Rows of the DrugBank vocabulary CSV, from the .csv or the downloaded .zip."""
    if path.suffix == '.zip':
        with zipfile.ZipFile(path) as archive:
            name = next(n for n in archive.namelist() if n.endswith('.csv'))
            text = archive.read(name).decode('utf8')
    else:
        text = path.read_text(encoding='utf8')
    return list(csv.DictReader(io.StringIO(text)))


def drugbank_proposals(rows: Iterable[dict], entities: list[dict]) -> list[tuple]:
    drugs = {e['uid'].split(':', 1)[1]: e['uid'] for e in entities
             if e['label'] == 'Drug' and e['uid'].startswith('DrugBank:')}
    proposals = []
    for row in rows:
        uid = drugs.get(row.get('DrugBank ID', ''))
        if uid:
            names = [row.get('Common name', ''), *re.split(r'\s*\|\s*', row.get('Synonyms') or '')]
            proposals += [(uid, n, 'drugbank_vocabulary') for n in names if usable(n)]
    return proposals


def merge_synonyms(entities: list[dict], proposals: Iterable[tuple]) -> tuple[list[dict], dict]:
    """Choose additions that never create a new same-label ambiguity.

    Skips an alias the entity already has, an alias already used by another entity
    of the same label, and an alias proposed for several entities of one label.
    Sharing a name with another label is allowed only between entities that already
    share a name (Disease and Phenotype "gout"); otherwise it would create a new,
    unrelated reading ("DIC" for dacarbazine, "Seizures" for visual epilepsy).
    Returns (additions, skip counts). Re-running on enriched entities adds nothing.
    """
    label = {e['uid']: e['label'] for e in entities}
    owners: dict[tuple, set[str]] = defaultdict(set)
    any_owner: dict[str, set[str]] = defaultdict(set)
    keys: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        for alias in [entity['name'], *(entity.get('synonyms') or [])]:
            owners[(entity['label'], normalize(alias))].add(entity['uid'])
            any_owner[normalize(alias)].add(entity['uid'])
            keys[entity['uid']].add(normalize(alias))
    wanted: dict[tuple, dict[str, tuple]] = defaultdict(dict)
    skipped = defaultdict(int)
    for uid, alias, source in proposals:
        key = (label[uid], normalize(alias))
        others = {o for o in any_owner.get(key[1], ()) if label[o] != label[uid]}
        if uid in owners.get(key, ()):
            skipped['already_present'] += 1
        elif owners.get(key):
            skipped['used_by_other_entity_same_label'] += 1
        elif any(not keys[uid] & keys[o] for o in others):
            skipped['unrelated_entity_other_label'] += 1
        else:
            wanted[key].setdefault(uid, (alias, source))
    additions = []
    for key, by_uid in wanted.items():
        if len(by_uid) > 1:
            skipped['proposed_for_several_entities'] += len(by_uid)
            continue
        (uid, (alias, source)), = by_uid.items()
        additions.append({'uid': uid, 'label': key[0], 'alias': alias, 'source': source})
    return sorted(additions, key=lambda a: (a['uid'], a['alias'])), dict(skipped)


def apply_additions(entities: list[dict], additions: list[dict]) -> list[dict]:
    by_uid = defaultdict(list)
    for addition in additions:
        by_uid[addition['uid']].append(addition['alias'])
    return [dict(e, synonyms=[*(e.get('synonyms') or []), *by_uid[e['uid']]]) if e['uid'] in by_uid else e
            for e in entities]
