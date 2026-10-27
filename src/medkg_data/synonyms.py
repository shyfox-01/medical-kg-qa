"""Synonym enrichment from MeSH, DrugBank, cached labels and RxNorm.

Pure functions shared by the enrichment script and tests. Proposals are
(uid, alias, source) triples; merge_synonyms() decides which become aliases.

* MeSH drugs (tree D): terms of the preferred concept and of narrower (NRW)
  concepts, which hold brand names and salts (Tylenol, Lipitor). Related (REL)
  concepts are often combination products and are skipped. A descriptor is used
  only when its terms match exactly one catalog Drug.
* MeSH diseases: preferred-concept terms only (narrower concepts can be other
  diseases), joined through MONDO xrefs annotated MONDO:equivalentTo.
* DrugBank vocabulary (CC0): synonyms joined by DrugBank id.
* RxNorm prescribable brands: one ingredient with one catalog Drug; ambiguous
  and ordinary-language brand names are excluded before the shared merge.
  Accepted RxNorm aliases are stored separately for exact matching only.
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

from medkg_data.alias_policy import exact_names, is_excluded
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
            for alias in exact_names(entity):
                index[normalize(alias)].add(entity['uid'])
    return index


SALT = re.compile(r'\s+(?:citrate|hydrochloride|hcl|sodium|potassium|calcium|maleate|sulfate|'
                  r'mesylate|tartrate|acetate|phosphate|besylate|fumarate|succinate|bromide|'
                  r'chloride|hydrobromide|monohydrate|dihydrate|trihydrate)$', re.I)


# Claude's manual review of 556 short RxNorm brands (D099): personal names and
# ordinary English words that would create unrelated mentions in free text.
RXNORM_STOP = frozenset({
    'julie', 'ella', 'nikita', 'muse', 'propel', 'thrive', 'react', 'clarus', 'compro',
    'curae', 'utopic', 'inova', 'allday', 'today', 'focus', 'prevail', 'relief', 'clear',
    'correct', 'ultra',
})


# The 2026-10-24 RxNorm review (D101), compared after shared normalization.
RXNORM_EXCLUDE = frozenset(normalize(name) for name in (
    # Incorrect ingredient mappings, including salt stripping to a bare cation.
    'Hextend', 'K-Phos',
    # Names usually identify another product or formulation.
    'Listerine', 'Chloraseptic', 'Aleve Arthritis Pain', 'Unisom Sleep', 'Clinidine',
    'IsoDitrate',
    # Ordinary phrases create unrelated free-text mentions.
    'Morning After', 'Option 2', 'My Choice', 'Your Choice', 'My Way', 'New Day',
    'Take Action', 'Her Style', "Doctor's Choice", 'Perfect Choice', "Kid's Choice",
    'Fiber Choice', 'Deep Sea', 'Sea Soft', 'Simply Sleep', 'Healthy Mama',
    'Comfort Shield', 'Aqua Care', 'The Magic Bullet', 'Acne-Clear', 'Blink Dry Eye',
    'Sojourn', 'P & S',
    # Personal names create unrelated mentions of people.
    'Terrell', 'Tobi', 'Dotti', 'Alora', 'Avita', 'Antara', 'Flanders',
    # These brands attract spelling corrections of ordinary English words.
    'Medicone', 'Stangard', 'Appearex', 'Vectical', 'OraVerse', 'Mitigare', 'Hurricaine',
))

# Removing a terminal salt must not turn its active ingredient into a bare cation.
RXNORM_SALT_CATIONS = frozenset({
    'potassium', 'sodium', 'calcium', 'magnesium', 'zinc', 'iron', 'lithium',
    'aluminum', 'aluminium', 'ammonium',
})


def _rrf_rows(path: Path, required_fields: int) -> Iterator[list[str]]:
    """Read pipe-delimited records as data, preserving literal quotes in names."""
    with path.open(encoding='utf8') as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            fields = line.rstrip('\r\n').split('|')
            if fields[-1] != '' or len(fields) - 1 < required_fields:
                raise ValueError(f'{path.name}:{number}: malformed RRF record')
            yield fields


def rxnorm_proposal_report(rrf_dir: Path, entities: list[dict],
                           lowercase_words: set[str]) -> tuple[list[tuple], dict]:
    """Return proposals and exclusive first-failure counts for BN/name pairs.

    Scan every brand before emitting any proposal: a spelling seen on a
    combination or unresolved brand must also block otherwise valid namesakes.
    """
    brands: dict[str, set[str]] = defaultdict(set)
    ingredients: dict[str, set[str]] = defaultdict(set)
    for fields in _rrf_rows(rrf_dir / 'RXNCONSO.RRF', 17):
        if fields[11] != 'RXNORM' or fields[16] not in ('N', ''):
            continue
        if fields[12] == 'BN':
            brands[fields[0]].add(fields[14])
        elif fields[12] == 'IN':
            ingredients[fields[0]].add(fields[14])

    brand_ingredients: dict[str, set[str]] = defaultdict(set)
    for fields in _rrf_rows(rrf_dir / 'RXNREL.RRF', 11):
        if fields[10] != 'RXNORM' or fields[7] not in ('tradename_of', 'has_tradename'):
            continue
        a, b = fields[0], fields[4]
        if a in brands and b in ingredients:
            brand_ingredients[a].add(b)
        if b in brands and a in ingredients:
            brand_ingredients[b].add(a)

    drugs = _index(entities, 'Drug')
    resolved: dict[str, str] = {}
    failures: dict[str, str] = {}
    unsafe: set[str] = set()
    for brand, names in brands.items():
        linked = brand_ingredients.get(brand, set())
        if not linked:
            failures[brand] = 'no_ingredient'
        elif len(linked) != 1:
            failures[brand] = 'multiple_ingredients'
        else:
            ingredient = next(iter(linked))
            matches = []
            for name in ingredients[ingredient]:
                ids = drugs.get(normalize(name))
                if not ids:
                    stripped = SALT.sub('', name)
                    key = normalize(stripped)
                    if stripped != name and key in RXNORM_SALT_CATIONS:
                        ids = set()
                    else:
                        ids = drugs.get(key, set())
                matches.append(ids)
            matched = set().union(*matches)
            if any(not ids for ids in matches):
                failures[brand] = 'ingredient_unlinked'
            elif any(len(ids) != 1 for ids in matches) or len(matched) != 1:
                failures[brand] = 'ingredient_ambiguous'
            else:
                resolved[brand] = next(iter(matched))
        if brand in failures:
            unsafe.update(normalize(name) for name in names)

    excluded = dict.fromkeys((
        'no_ingredient', 'multiple_ingredients', 'ingredient_unlinked',
        'ingredient_ambiguous', 'review_excluded', 'unusable', 'parenthesized_or_reformulated',
        'stop_word', 'lowercase_word', 'unsafe_name',
    ), 0)
    proposals = set()
    for brand, names in brands.items():
        for name in names:
            key = normalize(name)
            reason = failures.get(brand)
            if reason is None:
                if key in RXNORM_EXCLUDE:
                    reason = 'review_excluded'
                elif not usable(name):
                    reason = 'unusable'
                elif '(' in name or re.search(r'\breformulated\b', name, re.I):
                    reason = 'parenthesized_or_reformulated'
                elif key in RXNORM_STOP:
                    reason = 'stop_word'
                elif len(key.split()) == 1 and key in lowercase_words:
                    reason = 'lowercase_word'
                elif key in unsafe:
                    reason = 'unsafe_name'
            if reason is not None:
                excluded[reason] += 1
            else:
                proposals.add((resolved[brand], name, 'rxnorm:' + brand))
    result = sorted(proposals)
    return result, {
        'rxnorm_brands_considered': sum(len(names) for names in brands.values()),
        'rxnorm_proposed': len(result),
        'rxnorm_excluded_by_rule': excluded,
    }


def rxnorm_proposals(rrf_dir: Path, entities: list[dict],
                     lowercase_words: set[str]) -> list[tuple]:
    """Propose deduplicated, sorted RxNorm brand aliases for the shared merge."""
    return rxnorm_proposal_report(rrf_dir, entities, lowercase_words)[0]


def mesh_drug_proposals(descriptors: Iterable[Descriptor], entities: list[dict]) -> list[tuple]:
    # Do not recursively use aliases added by a previous enrichment to join a
    # broader descriptor to one of its narrower drugs.
    drugs = _index([dict(e,synonyms=[],exact_synonyms=[]) for e in entities], 'Drug')
    existing_aliases = _index(entities, 'Drug')
    proposals = []
    for d in descriptors:
        if not any(tree.startswith('D') for tree in d.trees):
            continue
        terms = [d.name, *d.preferred, *d.narrower]
        anchors = [d.name, *d.preferred]
        matched = set().union(*(drugs.get(normalize(t), set()) for t in anchors))
        if not matched:
            # MeSH may index the salt ("Sildenafil Citrate", with Viagra) while the
            # catalog names the active moiety ("Sildenafil").
            matched = set().union(*(drugs.get(normalize(SALT.sub('', t)), set()) for t in anchors))
        if len(matched) == 1:
            uid = matched.pop()
            if set().union(*(existing_aliases.get(normalize(t),set()) for t in terms))-{uid}:
                continue
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


def cached_fda_proposals(records: Iterable[dict], entities: list[dict]) -> list[tuple]:
    """Join every cached ingredient name, never the API search's requested drug uid.

    Exact catalog names (or a terminal salt form) must all resolve to one Drug.
    A brand seen on any unresolved/combination label is excluded globally.
    """
    drugs = _index(entities, 'Drug')
    proposals, unsafe = [], set()
    for record in records:
        for label in record.get('results', []):
            fields = label.get('openfda', {})
            brands = fields.get('brand_name') or []
            names = (fields.get('generic_name') or []) + (fields.get('substance_name') or [])
            matches = [drugs.get(normalize(name)) or
                       drugs.get(normalize(SALT.sub('', name)), set()) for name in names]
            matched = set().union(*matches)
            source_id = label.get('id') or label.get('set_id')
            if not matches or any(len(ids)!=1 for ids in matches) or len(matched)!=1 or not source_id:
                unsafe.update(normalize(brand) for brand in brands)
                continue
            # OTC product descriptions (e.g. "Allergy Relief") are not unique
            # brand identities. Keep this expansion scoped to prescription labels.
            if fields.get('product_type')!=['HUMAN PRESCRIPTION DRUG']:
                unsafe.update(normalize(brand) for brand in brands)
                continue
            uid = next(iter(matched))
            proposals.extend((uid, brand, 'openfda:'+source_id) for brand in brands if usable(brand))
    return sorted(set(p for p in proposals if normalize(p[1]) not in unsafe))


def medlineplus_proposals(path: Path, entities: list[dict]) -> list[tuple]:
    """Use also-called names only for an exact, unambiguous Disease topic title.

    ABOUT edges and broad MeSH headings do not establish synonym equivalence.
    No benchmark surface forms or gold anchors participate in this join.
    """
    diseases = _index([dict(e,name=re.sub(r'\s*\((?:disease|disorder)\)$','',e['name']),
                           synonyms=[],exact_synonyms=[]) for e in entities], 'Disease')
    proposals = []
    for topic in ET.parse(path).getroot().findall('health-topic'):
        if topic.get('language', '').casefold()!='english' or not topic.get('id'):
            continue
        matched = diseases.get(normalize(topic.get('title', '')), set())
        if len(matched)!=1:
            continue
        uid = next(iter(matched))
        for alias in topic.findall('also-called'):
            text = (alias.text or '').strip()
            if usable(text):
                proposals.append((uid, text, 'medlineplus:'+topic.get('id')))
    return sorted(set(proposals))


# D114: MedlinePlus topic titles as lay names of a Disease. A topic about a population,
# prevention or care, or one that joins several conditions, names no single disease.
TOPIC_NOT_A_NAME = re.compile(r'\b(?:in|for)\s+(?:children|infants|babies|teens|women|men|pregnancy|older adults)\b'
                              r'|\bchildhood\b|^how to\b|\bcaregivers?\b|\brehabilitation\b|\bexposure\b|\bnutrition\b'
                              r'|\bhealth\b|\band\b|[,/]', re.I)
# Claude's review of the titles the rule proposed (D114): a substance or exposure, not
# the disease ("Asbestos" is not asbestosis), or a narrower or different condition.
REVIEWED_NOT_SYNONYMS = frozenset(normalize(t) for t in (
    'Asbestos', 'Mercury', 'Triglycerides', 'Cannabis', 'Opioid Overdose', 'Alcohol Use Disorder',
    'Genetic Disorders', 'Tailbone Disorders', 'Brachial Plexus Injuries'))


def _lay_key(text: str) -> str:
    text = re.sub(r"['’]s\b", '', text)
    return normalize(re.sub(r'\s*\((?:disease|disorder)\)$', '', text.strip(), flags=re.I))


def medlineplus_title_proposals(path: Path, entities: list[dict], equivalents: dict[str, set[str]]) -> list[tuple]:
    """A MedlinePlus topic title as a lay name ("Tooth Decay", "Pinworms") of the one
    Disease its MeSH heading is MONDO-equivalent to (D114).

    Two signals must agree: exactly one of the topic's MeSH headings names a Disease,
    and the title shares a word stem with one of that Disease's names, or another name
    of the topic is one of them. Only the title is proposed: also-called lists hold
    subtypes and related conditions ("Bulimia" under Eating Disorders).
    """
    by_mesh: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        if entity['label'] == 'Disease':
            for term in mondo_ids(entity['uid'].split(':', 1)[1]):
                for ui in equivalents.get(term, ()):
                    by_mesh[ui].add(entity['uid'])
    by_uid = {e['uid']: e for e in entities}

    def stems(text: str) -> set[str]:
        return {w[:5] for w in _lay_key(text).split() if len(w) >= 5}
    proposals = []
    for topic in ET.parse(path).getroot().findall('health-topic'):
        if topic.get('language', '').casefold() != 'english' or not topic.get('id'):
            continue
        diseases = [by_mesh[d.get('id')] for d in topic.findall('mesh-heading/descriptor') if by_mesh.get(d.get('id'))]
        if len(diseases) != 1 or len(diseases[0]) != 1:
            continue
        uid = next(iter(diseases[0]))
        title = re.sub(r'\s*\([A-Z0-9-]{2,8}\)$', '', topic.get('title', '')).strip()   # "Enlarged Prostate (BPH)"
        if (TOPIC_NOT_A_NAME.search(title) or re.fullmatch(r'[A-Z0-9-]{2,6}', title) or not usable(title)
                or normalize(title) in REVIEWED_NOT_SYNONYMS):
            continue
        own = [by_uid[uid]['name'], *(by_uid[uid].get('synonyms') or [])]
        others = [(a.text or '').strip() for a in topic.findall('also-called') + topic.findall('see-reference')]
        if (stems(title) & set().union(*(stems(n) for n in own))
                or {_lay_key(o) for o in others} & {_lay_key(n) for n in own}):
            proposals.append((uid, title, 'medlineplus-title:' + topic.get('id')))
    return sorted(set(proposals))


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
        for alias in [entity['name'], *(entity.get('synonyms') or []),
                      *(entity.get('exact_synonyms') or [])]:
            owners[(entity['label'], normalize(alias))].add(entity['uid'])
            any_owner[normalize(alias)].add(entity['uid'])
            keys[entity['uid']].add(normalize(alias))
    wanted: dict[tuple, dict[str, tuple]] = defaultdict(dict)
    skipped = defaultdict(int)
    for uid, alias, source in proposals:
        if is_excluded(uid, alias):
            skipped['review_quarantine'] += 1
            continue
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
    proposed_owners: dict[str, set[str]] = defaultdict(set)
    for (_, alias), by_uid in wanted.items():
        proposed_owners[alias].update(by_uid)
    for key, by_uid in wanted.items():
        if len(by_uid) > 1:
            skipped['proposed_for_several_entities'] += len(by_uid)
            continue
        (uid, (alias, source)), = by_uid.items()
        if any(label[other]!=label[uid] and not keys[uid] & keys[other]
               for other in proposed_owners[key[1]]):
            skipped['proposed_for_unrelated_labels'] += 1
            continue
        additions.append({'uid': uid, 'label': key[0], 'alias': alias, 'source': source})
    return sorted(additions, key=lambda a: (a['uid'], a['alias'])), dict(skipped)


def apply_additions(entities: list[dict], additions: list[dict]) -> list[dict]:
    """Append RxNorm aliases to exact_synonyms and other sources to synonyms."""
    by_uid = defaultdict(lambda: defaultdict(list))
    for addition in additions:
        field_name = 'exact_synonyms' if addition.get('source', '').startswith('rxnorm:') else 'synonyms'
        by_uid[addition['uid']][field_name].append(addition['alias'])
    return [dict(e, **{field_name: [*(e.get(field_name) or []), *aliases]
                      for field_name, aliases in by_uid[e['uid']].items()})
            if e['uid'] in by_uid else e for e in entities]
