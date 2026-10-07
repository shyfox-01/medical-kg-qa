"""Structured v2 benchmark: common entities, natural wording and clinical multi-hop shapes.

Gold answers come from the PrimeKG CSV transform, never from Neo4j or QA code, as in
v1 (which stays frozen). The entity catalog, documents and synonym additions are read
only to choose anchors and their surface forms; every expected set is computed from
CSV edges. Design: decision D050.

    python -m eval.generate_v2                          # natural templates only
    python -m eval.generate_v2 --paraphrase-share 0.5   # plus validated LLM rewording
"""

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from eval.generate import controls, split
from medkg_data.lexicon import COMMON_WORDS, normalize
from medkg_data.ontology import load_obo
from medkg_data.primekg import read_graph
from medkg_data.synonyms import COVERAGE_PROBES

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT/'eval/datasets/structured_v2.jsonl'
MANIFEST = ROOT/'eval/datasets/MANIFEST_v2.json'
VERSION = 'structured-2.0'
SEED = 2026
COMMON_SHARE = 0.75
RECALL_MAX = 15
COUNTS = {'single_hop': 60, 'reverse': 30, 'lexical_variation': 60, 'multi_constraint': 40,
          'multi_hop': 50, 'aggregation': 40, 'multi_turn': 20, 'sensitive_terms': 20,
          'out_of_scope': 30, 'adversarial': 25, 'safety': 25}

# intent -> (anchor label, target label, relation, direction from the anchor)
RELATIONS = {
    'indications': ('Drug', 'Disease', 'INDICATED_FOR', 'out'),
    'drugs_for': ('Disease', 'Drug', 'INDICATED_FOR', 'in'),
    'side_effects': ('Drug', 'Phenotype', 'HAS_SIDE_EFFECT', 'out'),
    'phenotypes': ('Disease', 'Phenotype', 'HAS_PHENOTYPE', 'out'),
    'contraindications': ('Drug', 'Disease', 'CONTRAINDICATED_FOR', 'out'),
    'contraindicated_drugs': ('Disease', 'Drug', 'CONTRAINDICATED_FOR', 'in'),
    'interactions': ('Drug', 'Drug', 'INTERACTS_WITH', 'both'),
    'genes': ('Disease', 'Gene', 'ASSOCIATED_WITH', 'out'),
    'targets': ('Drug', 'Gene', 'TARGETS', 'out'),
    'drugs_with_side_effect': ('Phenotype', 'Drug', 'HAS_SIDE_EFFECT', 'in'),
    'diseases_for': ('Phenotype', 'Disease', 'HAS_PHENOTYPE', 'in'),
}
ARROWS = {'out': '-[:{r}]->', 'in': '<-[:{r}]-', 'both': '-[:{r}]-'}
TEMPLATES = {
    'indications': ['What is {a} used for?', 'What conditions is {a} indicated for?',
                    'What is {a} prescribed to treat?', 'Which diseases can {a} be used to treat?'],
    'drugs_for': ['Which drugs are used to treat {a}?', 'What medications are indicated for {a}?',
                  'What drugs treat {a}?', 'Which medicines are prescribed for {a}?'],
    'side_effects': ['What are the side effects of {a}?', 'What side effects can {a} cause?',
                     'Which adverse effects are reported for {a}?'],
    'phenotypes': ['What are the symptoms of {a}?', 'What signs and symptoms are associated with {a}?',
                   'Which clinical features does {a} have?'],
    'contraindications': ['When should {a} not be used?', 'Which conditions is {a} contraindicated in?',
                          'In which diseases should {a} be avoided?'],
    'contraindicated_drugs': ['Which drugs are contraindicated in {a}?',
                              'What medications should be avoided in patients with {a}?'],
    'interactions': ['Which drugs interact with {a}?', 'What drugs have interactions with {a}?'],
    'genes': ['Which genes are associated with {a}?', 'What genes are linked to {a}?'],
    'targets': ['Which genes or proteins does {a} target?', 'What are the molecular targets of {a}?'],
    'drugs_with_side_effect': ['Which drugs can cause {a}?', 'Which drugs list {a} as a side effect?',
                               'What medications have {a} as an adverse effect?'],
    'diseases_for': ['Which diseases have {a} as a symptom?', 'What conditions can present with {a}?'],
}
COUNT_TEMPLATES = {
    'drugs_for': ['How many drugs are indicated for {a}?', 'How many medications are used to treat {a}?'],
    'side_effects': ['How many side effects are recorded for {a}?'],
    'indications': ['How many conditions is {a} indicated for?'],
    'genes': ['How many genes are associated with {a}?'],
    'drugs_with_side_effect': ['How many drugs list {a} as a side effect?'],
}
SHAPES = {
    'both_drugs': (['Which drugs are indicated for both {a} and {b}?', 'What medications treat both {a} and {b}?'],
                   'MATCH (a:Disease {uid:$a})<-[:INDICATED_FOR]-(x:Drug)-[:INDICATED_FOR]->(:Disease {uid:$b}) '
                   'RETURN DISTINCT x.uid AS uid'),
    'shared_symptoms': (['Which symptoms do {a} and {b} have in common?',
                         'What clinical features are shared by {a} and {b}?'],
                        'MATCH (:Disease {uid:$a})-[:HAS_PHENOTYPE]->(x:Phenotype)<-[:HAS_PHENOTYPE]-(:Disease {uid:$b}) '
                        'RETURN DISTINCT x.uid AS uid'),
    'exclusion': (['Which drugs used for {a} are not contraindicated in {b}?',
                   'Which medications for {a} can be used without a contraindication in {b}?'],
                  'MATCH (:Disease {uid:$a})<-[:INDICATED_FOR]-(x:Drug) '
                  'WHERE NOT (x)-[:CONTRAINDICATED_FOR]->(:Disease {uid:$b}) RETURN DISTINCT x.uid AS uid'),
    'indicated_interacts': (['Which drugs used to treat {a} interact with {b}?',
                             'Which medications for {a} have interactions with {b}?'],
                            'MATCH (:Disease {uid:$a})<-[:INDICATED_FOR]-(x:Drug)-[:INTERACTS_WITH]-(:Drug {uid:$b}) '
                            'RETURN DISTINCT x.uid AS uid'),
    'indicated_contraindicated': (['Which drugs used for {a} are contraindicated in {b}?',
                                   'Which {a} medications should be avoided in patients with {b}?'],
                                  'MATCH (:Disease {uid:$a})<-[:INDICATED_FOR]-(x:Drug)-[:CONTRAINDICATED_FOR]->'
                                  '(:Disease {uid:$b}) RETURN DISTINCT x.uid AS uid'),
    'class_side_effects': (['What side effects can drugs used to treat {a} cause?',
                            'Which adverse effects are reported for medications indicated for {a}?'],
                           'MATCH (:Disease {uid:$a})<-[:INDICATED_FOR]-(:Drug)-[:HAS_SIDE_EFFECT]->(x:Phenotype) '
                           'RETURN DISTINCT x.uid AS uid'),
    'gene_mediated': (['Which drugs target genes associated with {a}?',
                       'Which drugs act on genes linked to {a}?'],
                      'MATCH (:Disease {uid:$a})-[:ASSOCIATED_WITH]->(:Gene)<-[:TARGETS]-(x:Drug) '
                      'RETURN DISTINCT x.uid AS uid'),
}
# Required wording that a paraphrase must keep for each shape.
CUES = {'both_drugs': r'\bboth\b', 'shared_symptoms': r'\bin common\b|\bshared?\b|\bboth\b',
        'exclusion': r'\bnot\b|\bwithout\b', 'indicated_interacts': r'interact',
        'indicated_contraindicated': r'contraindicat|avoid', 'class_side_effects': r'side effect|adverse',
        'gene_mediated': r'\bgenes?\b'}
# HPO branches that describe qualifiers rather than findings ("Infantile onset",
# "Autosomal recessive inheritance"); they never serve as question anchors.
HPO_QUALIFIER_ROOTS = ('HP:0012823', 'HP:0000005', 'HP:0040279', 'HP:0032223', 'HP:0032443')
# OTC product descriptors that are not brand names ("Childrens Allergy Relief").
PRODUCT_WORDS = re.compile(r'allerg|relief|cream|anti|cool|salt|child|kid|cold|flu|pain|itch|spray|gel|lotion|'
                           r'ointment|tablet|care|plus|extra|strength|daily|night|sleep|health|formula', re.I)
# MedlinePlus topics about care, medicines or populations rather than one disease.
TOPIC_NOT_DISEASE = re.compile(r'\b(?:and|for|in|with|medicines?|drugs?|treatments?|therapy|surgery|tests?|'
                               r'screening|health|nutrition|care|safety|use|abuse|living|coping)\b', re.I)
# Words the pre-D047 safety rules refused on sight; knowledge questions using them must be answered.
SENSITIVE = re.compile(r"chest pain|heart attack|\bsuicid\w*|self[- ]?harm|\bseizures?\b|\bstroke\b|"
                       r"\bbleeding\b|\bunconscious\b|\bbreath\w*|\bpregnan\w*|\bbreast-?feed\w*|"
                       r"\binfants?\b|\bnewborns?\b|\bchild(?:ren)?\b|\belderly\b", re.I)


class Graph:
    def __init__(self, nodes: list[dict], edges: list[dict]):
        self.nodes = {n['uid']: n for n in nodes}
        self.out, self.inc = defaultdict(set), defaultdict(set)
        for e in edges:
            self.out[(e['type'], e['a'])].add(e['b'])
            self.inc[(e['type'], e['b'])].add(e['a'])

    def targets(self, intent: str, uid: str) -> set[str]:
        _, _, relation, direction = RELATIONS[intent]
        found = set()
        if direction in ('out', 'both'):
            found |= self.out.get((relation, uid), set())
        if direction in ('in', 'both'):
            found |= self.inc.get((relation, uid), set())
        return found - {uid}


def single_query(intent: str, count: bool = False) -> str:
    anchor, target, relation, direction = RELATIONS[intent]
    result = 'count(DISTINCT b) AS count' if count else 'DISTINCT b.uid AS uid'
    return f'MATCH (a:{anchor} {{uid:$uid}}){ARROWS[direction].format(r=relation)}(b:{target}) RETURN {result}'


def typo(word: str, rng: random.Random) -> str | None:
    """Swap two adjacent interior letters ("Metformin" -> "Metfromin")."""
    positions = [i for i in range(1, len(word)-2) if word[i] != word[i+1] and word[i].isalpha() and word[i+1].isalpha()]
    if len(word) < 7 or not positions:
        return None
    i = rng.choice(positions)
    return word[:i] + word[i+1] + word[i] + word[i+2:]


def valid_paraphrase(row: dict, text: str) -> bool:
    if not text or not text.strip().endswith('?') or not 10 <= len(text) <= 250:
        return False
    if not all(a.casefold() in text.casefold() for a in row['anchors']):
        return False
    if row['kind'] == 'count' and not re.search(r'\bhow many\b|\bnumber of\b', text, re.I):
        return False
    cue = CUES.get(row.get('shape', ''))
    return not cue or bool(re.search(cue, text, re.I))


def hpo_qualifiers(hp: dict) -> set[str]:
    """PrimeKG phenotype uids (HPO:<n>) under the HPO qualifier branches."""
    children = defaultdict(set)
    for term in hp.values():
        for parent in term.parents:
            children[parent].add(term.id)
    found, stack = set(), list(HPO_QUALIFIER_ROOTS)
    while stack:
        term = stack.pop()
        if term not in found:
            found.add(term)
            stack += children.get(term, ())
    return {'HPO:' + t.removeprefix('HP:').lstrip('0') for t in found}


class Builder:
    def __init__(self, graph: Graph, catalog: list[dict], documents: list[dict], additions: list[dict],
                 seed: int = SEED, qualifiers: set[str] = frozenset(), brands: dict | None = None,
                 lay: dict | None = None):
        self.g, self.rng = graph, random.Random(seed)
        self.qualifiers = set(qualifiers)
        self.brands, self.lay = brands or {}, lay or {}
        self.catalog = {e['uid']: e for e in catalog}
        self.keys = {uid: {normalize(a) for a in [e['name'], *(e.get('synonyms') or [])]}
                     for uid, e in self.catalog.items()}
        self.owners = defaultdict(set)
        for uid, e in self.catalog.items():
            for key in self.keys[uid]:
                self.owners[(e['label'], key)].add(uid)
        self.by_label = defaultdict(list)
        for uid in sorted(self.catalog):
            self.by_label[self.catalog[uid]['label']].append(uid)
        about = defaultdict(set)
        for d in documents:
            about[d['source']].update(d.get('about', []))
        drugs, phenotypes = self.by_label['Drug'], self.by_label['Phenotype']
        by_side_effect = sorted(phenotypes, key=lambda u: -len(graph.targets('drugs_with_side_effect', u)))
        by_disease = sorted(phenotypes, key=lambda u: -len(graph.targets('diseases_for', u)))
        self.common = {
            'Disease': about['medlineplus'] & set(self.by_label['Disease']),
            'Drug': (about['openfda'] & set(drugs)) | {u for u in drugs if len(graph.targets('indications', u)) >= 3},
            'Phenotype': set(by_side_effect[:300]) | set(by_disease[:300]),
            'Gene': set(),
        }
        self.aliases = defaultdict(list)
        for a in additions:
            self.aliases[a['uid']].append(a['alias'])
        self.excluded = {normalize(p) for p in COVERAGE_PROBES}
        self.used = Counter()

    # -- surface forms -------------------------------------------------------------
    def display(self, uid: str) -> str:
        name = self.catalog[uid]['name']
        short = re.sub(r'\s*\((?:disease|disorder)\)$', '', name)
        name = short if short != name and normalize(short) in self.keys[uid] else name
        # HPO labels are sentence-cased ("Diplopia"); mid-sentence they read as "diplopia".
        if self.catalog[uid]['label'] == 'Phenotype' and name[1:2].islower():
            name = name[0].lower() + name[1:]
        return name

    def unambiguous(self, uid: str, text: str) -> bool:
        return self.owners.get((self.catalog[uid]['label'], normalize(text)), set()) == {uid}

    def usable(self, uid: str, text: str | None = None) -> bool:
        text = text or self.display(uid)
        return (uid not in self.qualifiers and not self.catalog[uid]['name'].lower().startswith('obsolete')
                and 3 <= len(text) <= 50 and self.unambiguous(uid, text)
                and normalize(text) not in COMMON_WORDS and normalize(text) not in self.excluded)

    def pool(self, uid: str) -> str:
        return 'common' if uid in self.common[self.catalog[uid]['label']] else 'tail'

    def pick(self, label: str, n: int, ok, max_uses: int = 2) -> list[str]:
        pool = [u for u in self.by_label[label] if self.used[u] < max_uses and self.usable(u) and ok(u)]
        common = [u for u in pool if u in self.common[label]]
        tail = [u for u in pool if u not in self.common[label]]
        k = min(len(common), round(n * COMMON_SHARE))
        chosen = self.rng.sample(common, k) + self.rng.sample(tail, min(len(tail), n - k))
        if len(chosen) < n:
            chosen += self.rng.sample([u for u in common if u not in chosen], min(n - len(chosen), len(common) - k))
        self.used.update(chosen)
        return chosen

    def prefer_common(self, options: list[str]) -> str:
        options = sorted(options)
        common = [u for u in options if u in self.common[self.catalog[u]['label']] and self.usable(u)]
        usable = [u for u in options if self.usable(u)]
        return self.rng.choice(common or usable) if (common or usable) else ''

    # -- rows ------------------------------------------------------------------------
    def row(self, category: str, question: str, expected: set, query: str, params: dict,
            anchors: list[str], anchor_uids: list[str], kind: str = 'list', **extra) -> dict:
        row = {'category': category, 'question': question, 'question_template': question,
               'expected': sorted(expected),
               'expected_names': {u: [self.catalog[u]['name']] for u in sorted(expected) if u in self.catalog},
               'gold_query': query, 'gold_params': params, 'anchors': anchors,
               'anchor_uids': sorted(anchor_uids), 'kind': kind,
               'recall_applicable': kind == 'list' and len(expected) <= RECALL_MAX,
               'anchor_pool': 'common' if all(self.pool(u) == 'common' for u in anchor_uids) else 'tail',
               **extra}
        if kind == 'count':
            row['expected_count'] = len(expected)
        return row

    def single(self, category: str, intent: str, n: int, count: bool = False) -> list[dict]:
        templates = (COUNT_TEMPLATES if count else TEMPLATES)[intent]
        label = RELATIONS[intent][0]
        rows = []
        for uid in self.pick(label, n, lambda u: bool(self.g.targets(intent, u))):
            text = self.display(uid)
            rows.append(self.row(category, self.rng.choice(templates).format(a=text),
                                 self.g.targets(intent, uid), single_query(intent, count), {'uid': uid},
                                 [text], [uid], 'count' if count else 'list', intent=intent))
        return rows

    def surface(self, uid: str, text: str) -> tuple[bool, bool]:
        """(acceptable, linked in catalog) for an alternative surface form of uid."""
        key, own = normalize(text), normalize(self.display(uid))
        owners = self.owners.get((self.catalog[uid]['label'], key), set())
        ok = (3 <= len(text) <= 40 and owners <= {uid} and key not in COMMON_WORDS and key not in self.excluded
              and key != own and key not in own and own not in key)
        return ok, uid in owners

    def lexical(self) -> list[dict]:
        rows = []
        brands = [(uid, sorted(names)) for uid, names in sorted(self.brands.items())
                  if uid in self.catalog and self.g.targets('indications', uid)]
        brands = [(uid, [n for n in names if self.surface(uid, n)[0]]) for uid, names in brands]
        brands = [b for b in brands if b[1]]
        for uid, options in self.rng.sample(brands, min(25, len(brands))):
            alias, intent = self.rng.choice(options), self.rng.choice(['indications', 'side_effects'])
            if not self.g.targets(intent, uid):
                intent = 'indications'
            rows.append(self.row('lexical_variation', self.rng.choice(TEMPLATES[intent]).format(a=alias),
                                 self.g.targets(intent, uid), single_query(intent), {'uid': uid}, [alias], [uid],
                                 intent=intent, variation='us_brand', alias_in_catalog=self.surface(uid, alias)[1]))
        diseases = []
        for uid, names in sorted(self.lay.items()):
            intents = [i for i in ('drugs_for', 'phenotypes', 'genes') if self.g.targets(i, uid)]
            options = [n for n in sorted(names) if self.surface(uid, n)[0]]
            if uid in self.catalog and options and intents:
                diseases.append((uid, options, intents))
        for uid, options, intents in self.rng.sample(diseases, min(20, len(diseases))):
            alias, intent = self.rng.choice(options), self.rng.choice(intents)
            alias = alias if alias.isupper() else alias.lower()
            rows.append(self.row('lexical_variation', self.rng.choice(TEMPLATES[intent]).format(a=alias),
                                 self.g.targets(intent, uid), single_query(intent), {'uid': uid}, [alias], [uid],
                                 intent=intent, variation='lay_disease_name', alias_in_catalog=self.surface(uid, alias)[1]))
        typos = []
        for label, intent in (('Drug', 'indications'), ('Disease', 'drugs_for')):
            for uid in sorted(self.common[label]):
                text = self.display(uid)
                if re.fullmatch(r'[A-Za-z]{7,}', text) and self.g.targets(intent, uid) and self.usable(uid):
                    typos.append((uid, text, intent))
        for uid, text, intent in self.rng.sample(typos, len(typos)):
            if len(rows) >= COUNTS['lexical_variation']:
                break
            wrong = typo(text, self.rng)
            if wrong and not any(self.owners.get((lbl, normalize(wrong))) for lbl in ('Drug', 'Disease', 'Phenotype')):
                rows.append(self.row('lexical_variation', self.rng.choice(TEMPLATES[intent]).format(a=wrong),
                                     self.g.targets(intent, uid), single_query(intent), {'uid': uid}, [wrong], [uid],
                                     intent=intent, variation='typo', typo_of=text))
        return rows

    def pairs(self, shape: str, category: str, n: int, gold, partner, first_ok) -> list[dict]:
        """Sample anchor pairs (a, b) whose CSV gold set is non-empty."""
        rows, seen = [], set()
        firsts = [u for u in self.by_label['Disease'] if self.usable(u) and first_ok(u)]
        common_firsts = [u for u in firsts if u in self.common['Disease']]
        for _ in range(4000):
            if len(rows) >= n:
                break
            pool = common_firsts if common_firsts and self.rng.random() < COMMON_SHARE else firsts
            a = self.rng.choice(pool)
            b = partner(a)
            if not b or b == a or (a, b) in seen or not self.usable(b):
                continue
            expected = gold(a, b)
            if not expected:
                continue
            seen.add((a, b))
            templates, query = SHAPES[shape]
            rows.append(self.row(category, self.rng.choice(templates).format(a=self.display(a), b=self.display(b)),
                                 expected, query, {'a': a, 'b': b}, [self.display(a), self.display(b)], [a, b],
                                 shape=shape))
        return rows

    def via(self, a: str, first: str, second: str) -> str:
        """Partner reached through a random neighbor: a -first-> x -second-> partner."""
        middle = sorted(self.g.targets(first, a))
        return self.prefer_common(sorted(self.g.targets(second, self.rng.choice(middle)))) if middle else ''

    def build(self) -> list[dict]:
        t = self.g.targets
        rows = []
        for intent, n in [('drugs_for', 12), ('indications', 10), ('side_effects', 8), ('phenotypes', 8),
                          ('contraindicated_drugs', 6), ('contraindications', 4), ('interactions', 4),
                          ('genes', 4), ('targets', 4)]:
            rows += self.single('single_hop', intent, n)
        rows += self.single('reverse', 'drugs_with_side_effect', 15) + self.single('reverse', 'diseases_for', 15)
        for intent, n in [('drugs_for', 12), ('side_effects', 8), ('indications', 8), ('genes', 6),
                          ('drugs_with_side_effect', 6)]:
            rows += self.single('aggregation', intent, n, count=True)
        rows += self.lexical()
        rows += self.pairs('both_drugs', 'multi_constraint', 15, lambda a, b: t('drugs_for', a) & t('drugs_for', b),
                           lambda a: self.via(a, 'drugs_for', 'indications'), lambda u: t('drugs_for', u))
        rows += self.pairs('shared_symptoms', 'multi_constraint', 10,
                           lambda a, b: t('phenotypes', a) & t('phenotypes', b),
                           lambda a: self.via(a, 'phenotypes', 'diseases_for'), lambda u: len(t('phenotypes', u)) >= 3)
        rows += self.pairs('exclusion', 'multi_constraint', 15,
                           lambda a, b: t('drugs_for', a) - t('contraindicated_drugs', b)
                           if t('drugs_for', a) & t('contraindicated_drugs', b) else set(),
                           lambda a: self.via(a, 'drugs_for', 'contraindications'), lambda u: len(t('drugs_for', u)) >= 3)
        rows += self.pairs('indicated_contraindicated', 'multi_hop', 15,
                           lambda a, b: t('drugs_for', a) & t('contraindicated_drugs', b),
                           lambda a: self.via(a, 'drugs_for', 'contraindications'), lambda u: t('drugs_for', u))
        rows += self.drug_partner_rows()
        for shape, n, ok, gold in [
                ('class_side_effects', 10, lambda u: 2 <= len(t('drugs_for', u)) <= 30,
                 lambda a: set().union(*(t('side_effects', d) for d in t('drugs_for', a)))),
                ('gene_mediated', 10, lambda u: t('genes', u),
                 lambda a: set().union(*(self.g.inc.get(('TARGETS', g), set()) for g in t('genes', a))))]:
            for uid in self.pick('Disease', n, lambda u, ok=ok, gold=gold: bool(ok(u)) and bool(gold(u))):
                templates, query = SHAPES[shape]
                rows.append(self.row('multi_hop', self.rng.choice(templates).format(a=self.display(uid)), gold(uid),
                                     query.replace('$a', '$uid'), {'uid': uid}, [self.display(uid)], [uid], shape=shape))
        rows += self.multi_turn() + self.sensitive()
        rows += [dict(r, anchor_uids=[], anchor_pool='control') for r in controls()]
        return rows

    def drug_partner_rows(self) -> list[dict]:
        """'Which drugs used to treat A interact with D?' with D a (preferably common) drug."""
        t, rows, seen = self.g.targets, [], set()
        diseases = [u for u in sorted(self.common['Disease']) if self.usable(u) and t('drugs_for', u)]
        for _ in range(4000):
            if len(rows) >= 15:
                break
            a = self.rng.choice(diseases)
            middle = sorted(t('drugs_for', a))
            d = self.prefer_common(sorted(t('interactions', self.rng.choice(middle))))
            if not d or (a, d) in seen:
                continue
            expected = t('drugs_for', a) & t('interactions', d)
            if expected:
                seen.add((a, d))
                templates, query = SHAPES['indicated_interacts']
                rows.append(self.row('multi_hop', self.rng.choice(templates).format(a=self.display(a), b=self.display(d)),
                                     expected, query, {'a': a, 'b': d}, [self.display(a), self.display(d)], [a, d],
                                     shape='indicated_interacts'))
        return rows

    def multi_turn(self) -> list[dict]:
        rows = []
        follow = {'Drug': [('side_effects', 'What are its side effects?'), ('targets', 'Which genes does it target?'),
                           ('contraindications', 'When should it not be used?')],
                  'Disease': [('phenotypes', 'What are its symptoms?'), ('genes', 'Which genes are associated with it?'),
                              ('contraindicated_drugs', 'Which drugs are contraindicated in it?')]}
        opening = {'Drug': ('indications', 'What is {a} used for?'), 'Disease': ('drugs_for', 'Which drugs are used to treat {a}?')}
        for label in ('Drug', 'Disease'):
            first, text = opening[label]
            for uid in self.pick(label, 10, lambda u, label=label, first=first: bool(self.g.targets(first, u))
                                 and any(self.g.targets(i, u) for i, _ in follow[label])):
                intent, question = self.rng.choice([f for f in follow[label] if self.g.targets(f[0], uid)])
                rows.append(self.row('multi_turn', question, self.g.targets(intent, uid), single_query(intent),
                                     {'uid': uid}, [], [uid], intent=intent,
                                     history_questions=[text.format(a=self.display(uid))]))
        return rows

    def sensitive(self) -> list[dict]:
        """Knowledge questions using words the old safety rules refused; they must be answered."""
        options = []
        for label, intents in (('Phenotype', ('drugs_with_side_effect', 'diseases_for')),
                               ('Disease', ('drugs_for', 'phenotypes', 'genes'))):
            for uid in self.by_label[label]:
                ready = [i for i in intents if self.g.targets(i, uid)]
                forms = [self.display(uid)] if self.usable(uid) else []
                forms += [n if n.isupper() else n.lower() for n in sorted(self.lay.get(uid, ()))
                          if self.surface(uid, n)[0]]
                for form in forms:
                    match = SENSITIVE.search(form)
                    if match and ready:
                        options.append((re.sub(r'(?:ren|s)$', '', match[0].lower()), uid, form, ready))
        by_word = defaultdict(list)
        for word, uid, form, intents in options:
            by_word[word].append((uid, form, intents))
        for group in by_word.values():
            self.rng.shuffle(group)
        rows = []
        while len(rows) < COUNTS['sensitive_terms'] and any(by_word.values()):
            for word in sorted(by_word):
                while by_word[word] and len(rows) < COUNTS['sensitive_terms']:
                    uid, form, intents = by_word[word].pop()
                    if all(uid not in r['anchor_uids'] for r in rows):
                        intent = self.rng.choice(intents)
                        rows.append(self.row('sensitive_terms', self.rng.choice(TEMPLATES[intent]).format(a=form),
                                             self.g.targets(intent, uid), single_query(intent), {'uid': uid}, [form],
                                             [uid], intent=intent, sensitive_word=word))
                        break
        return rows


def fda_brands(directory: Path) -> dict[str, set[str]]:
    """US brand names of single-ingredient products in the cached openFDA label responses."""
    brands = defaultdict(set)
    for path in sorted(directory.glob('*.json')):
        record = json.loads(path.read_text(encoding='utf8'))
        for result in record.get('results') or []:
            fields = result.get('openfda', {})
            generics = fields.get('generic_name') or []
            prescription = any('PRESCRIPTION' in t for t in fields.get('product_type') or [])
            if not record.get('drug_uid') or not prescription or len(generics) != 1 or re.search(r'[,;/]| and ', generics[0], re.I):
                continue
            generic = normalize(generics[0])
            for brand in fields.get('brand_name') or []:
                brand, key = brand.strip(), normalize(brand)
                if (re.fullmatch(r'[A-Za-z]{4,15}', brand) and not PRODUCT_WORDS.search(brand)
                        and key != generic and generic not in key and key not in generic):
                    brands[record['drug_uid']].add(brand.title() if brand.isupper() else brand)
    return brands


def lay_names(path: Path, documents: list[dict]) -> dict[str, set[str]]:
    """MedlinePlus consumer titles and also-called names of topics about exactly one disease."""
    import xml.etree.ElementTree as ET
    about = {d['title']: d['about'][0] for d in documents
             if d['source'] == 'medlineplus' and len(d.get('about', [])) == 1}
    names = defaultdict(set)
    for topic in ET.parse(path).getroot().findall('health-topic'):
        uid = about.get(topic.get('title', ''))
        if uid and topic.get('language', '').casefold() == 'english' and not TOPIC_NOT_DISEASE.search(topic.get('title', '')):
            for text in [topic.get('title', ''), *((a.text or '') for a in topic.findall('also-called'))]:
                text = text.strip()
                # A one-word name must be an acronym (HCV) or a real word of 6+ letters (grippe), not "hash".
                single_ok = ' ' in text or '-' in text or text.isupper() or len(text) >= 6
                if re.fullmatch(r"[A-Za-z][A-Za-z' -]{1,38}", text) and single_ok:
                    names[uid].add(text)
    return names

def paraphrase(rows: list[dict], share: float, seed: int = SEED) -> None:
    from eval.client import ResearchLLM
    rng = random.Random(seed)
    eligible = [r for r in rows if r['category'] not in ('out_of_scope', 'adversarial', 'safety', 'multi_turn')]
    selected = [r for r in eligible if rng.random() < share]
    llm = ResearchLLM()
    try:
        for i in range(0, len(selected), 8):
            batch = selected[i:i+8]
            try:
                response = llm.json(
                    'Rewrite each question as a natural question a patient or clinician might ask. Keep the '
                    'meaning exactly, keep every anchor string verbatim (including misspellings), and keep '
                    'words such as both, not, interact, contraindicated and how many. Return JSON '
                    '{"questions":[{"id":"...","question":"..."}]}.',
                    {'questions': [{'id': r['id'], 'question': r['question'], 'anchors': r['anchors']} for r in batch]},
                    900)
                mapping = {q.get('id'): q.get('question', '') for q in response.get('questions', [])}
            except (RuntimeError, KeyError, ValueError, AttributeError):
                mapping = {}
            for row in batch:
                text = mapping.get(row['id'], '')
                if text.strip() == row['question']:
                    row['paraphrase_status'] = 'llm_unchanged'
                elif valid_paraphrase(row, text):
                    row.update(question=text.strip(), paraphrase_status='llm_validated')
                else:
                    row['paraphrase_status'] = 'template_after_failed_validation'
            print(f'Paraphrased {min(i+8, len(selected))}/{len(selected)}', flush=True)
    finally:
        llm.close()


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--paraphrase-share', type=float, default=0.0)
    parser.add_argument('--dry-run', action='store_true', help='Print statistics and samples; write nothing')
    args = parser.parse_args()
    if DATASET.exists() and not args.dry_run:
        raise SystemExit('Frozen v2 dataset already exists; do not silently regenerate')
    raw, processed = ROOT/'data/raw', ROOT/'data/processed'
    nodes, edges, _ = read_graph(raw/'kg.csv', load_obo(raw/'mondo.obo'), load_obo(raw/'hp.obo'))
    catalog = json.loads((processed/'entities.json').read_text(encoding='utf8'))
    documents = [json.loads(line) for line in (processed/'documents.jsonl').read_text(encoding='utf8').splitlines()]
    additions = [json.loads(line) for line in (processed/'synonym_additions.jsonl').read_text(encoding='utf8').splitlines()]
    builder = Builder(Graph(nodes, edges), catalog, documents, additions,
                      qualifiers=hpo_qualifiers(load_obo(raw/'hp.obo')), brands=fda_brands(raw/'openfda'),
                      lay=lay_names(raw/'medlineplus.xml', documents))
    rows = builder.build()
    counts = Counter(r['category'] for r in rows)
    if counts != Counter(COUNTS):
        raise SystemExit(f'Category counts differ from the design: {dict(counts)}')
    split(rows, SEED)
    for i, row in enumerate(rows, 1):
        row.update(id=f'v2-{i:04d}', generator_version=VERSION)
        row.setdefault('paraphrase_status', 'template')
    if args.dry_run:
        sizes = Counter(min(len(r['expected']), 26) // 5 * 5 for r in rows if r['kind'] == 'list')
        print(json.dumps({'counts': dict(counts), 'anchor_pool': dict(Counter(r['anchor_pool'] for r in rows)),
                          'variations': dict(Counter(r.get('variation') for r in rows if r.get('variation'))),
                          'list_size_buckets': dict(sorted(sizes.items()))}, indent=2))
        sample = random.Random(1)
        for category in COUNTS:
            group = [r for r in rows if r['category'] == category]
            for r in sample.sample(group, min(4, len(group))):
                print(f"[{category}/{r.get('intent') or r.get('shape') or r.get('variation') or r['kind']}] "
                      f"{' >> '.join([*r.get('history_questions', []), r['question']])}  "
                      f"(gold {len(r['expected'])}, {r['anchor_pool']})")
        return
    if args.paraphrase_share:
        paraphrase(rows, args.paraphrase_share)
    DATASET.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf8')
    manifest = {
        'generator_version': VERSION, 'seed': SEED, 'counts': COUNTS,
        'splits': dict(Counter(r['split'] for r in rows)),
        'dataset_sha256': digest(DATASET), 'kg_sha256': digest(raw/'kg.csv'),
        'catalog_sha256': digest(processed/'entities.json'), 'documents_sha256': digest(processed/'documents.jsonl'),
        'synonym_additions_sha256': digest(processed/'synonym_additions.jsonl'),
        'mesh_sha256': digest(raw/'desc2026.gz'),
        'common_pools': {k: len(v) for k, v in builder.common.items()},
        'anchor_pool': dict(Counter(r['anchor_pool'] for r in rows)),
        'variations': dict(Counter(r['variation'] for r in rows if r.get('variation'))),
        'shapes': dict(Counter(r['shape'] for r in rows if r.get('shape'))),
        'recall_applicable': dict(Counter(str(r['recall_applicable']) for r in rows if r['kind'] == 'list')),
        'paraphrases': dict(Counter(r['paraphrase_status'] for r in rows)),
        'excluded_probe_aliases': len(builder.excluded), 'controls_from': 'eval.generate.controls (v1)',
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding='utf8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
