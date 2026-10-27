"""Exact, label-specific fuzzy, then precomputed alias-vector linking."""

import re
from dataclasses import asdict, dataclass

import numpy as np
from rapidfuzz import fuzz, process
from rapidfuzz.distance import DamerauLevenshtein

from medkg_data.alias_policy import EXCLUDED_ALIASES, allowed_names, exact_names, is_excluded
from medkg_data.lexicon import COMMON_WORDS, GENERIC_ANCHORS, ambiguous_word, normalize

__all__ = ['Candidate', 'Linker', 'label_choices', 'normalize']


@dataclass
class Candidate:
    uid: str
    name: str
    label: str
    score: float
    method: str
    ambiguous: bool = False
    mention: str | None = None
    span: tuple[int,int] | None = None


# D106: words that end a noun phrase or do not change which entity it names.
PHRASE_BREAK = frozenset('''
a an the of for about with without and or but nor between versus vs is are was were be been being
am do does did can could may might must shall should will would to from in on at by into onto over
under after before during while than as if then that this these those there here what which who whom
whose how why when where i me my we our you your he him his she her they them their it its any some
all no not each every both other such own same so very also just only even still please thank thanks
yes ok okay drug drugs medicine medicines medication medications treatment treatments therapy disease
diseases condition conditions disorder disorders illness symptom symptoms sign signs side effect
effects gene genes protein proteins phenotype phenotypes entity entitie entities target targets
patient patients people person treat treats treated treating cause causes caused causing use used
uses using take takes taking taken give given help helps prevent prevents prevented detect detected
indicated prescribed approved contraindicated recorded listed associated linked known documented
reported present presents presenting occur occurs include includes belong belongs trigger triggers
represent represents produce produces manifest manifests capable safe safely unsafe transmitted
contagious inherited hereditary aggravated similar possible especially beneficial stay receive
received manufactured expired always often usually storage requirement requirements interact
interacts interaction interactions combined right left new old get got have has had know tell show
list find search explain mean means name names called beside besides off stop stopping start
starting taper tapering wean weaning switch switching describe describes described define defines
definition overview information info details regarding concerning medlineplus say says write
experience experiences experiencing experienced provide provides drink drinks drinking eat eats
catch catches caught buy buying really hi hello hey location general health
'''.split())
# Common words also end a phrase, except a few that modify a medical name ("cold" sore,
# "high" voltage shock, "red" eye).
PHRASE_COMMON = COMMON_WORDS - {'cold', 'hot', 'high', 'low', 'red', 'eye'}
NEUTRAL_MODIFIERS = frozenset('''
severe mild moderate acute chronic bad terrible early late advanced recurrent frequent persistent
constant sudden occasional serious extreme current suspected diagnosed long term stage huge big
large small little tiny slight minor
tablet tablets capsule capsules patch patches pill pills mg mcg ml dose doses dosage xl xr er sr cr
extended release strength extra regular generic brand oral topical
'''.split())
PHRASE_STOP = PHRASE_BREAK | PHRASE_COMMON | NEUTRAL_MODIFIERS
# Head nouns that name a different thing than the word before them ("sodium deficiency" is
# not Sodium). An overdose, vaccine, surgery or withdrawal of X is answered from X's own
# evidence (the label's overdose section), so those words do not start a check.
HEAD_NOUNS = frozenset('''
deficiency deficiencies allergy allergies intolerance injury injuries infection infections
cancer tumor tumour syndrome
'''.split())
# D107: a name joined to a product or function word ("metformintablets", normalised).
SPACING_TAILS = frozenset('tablet pill capsule dose dosage injection cream with and for side'.split())
SPACING_MIN_CHARS = 7
# Endings of contractions and possessives ("what's", "don't", "I'd", "mother's").
CLITICS = frozenset('s t d ll re ve m'.split())
SPACING_MAX_WORDS = 8
# Words that never start or end a space fix: "ramipril at" is not Ramiprilat, "me
# prednisone" is not Meprednisone, "the coma" is not thecoma. A name may still end in a
# category word ("majordepressive disorder", "Ehlers-Danlossyndrome, vascular type").
SPACING_HEADS = frozenset('''
disease diseases disorder disorders illness syndrome syndromes infection infections cancer cancers
type types
'''.split())
SPACING_STOP = (PHRASE_STOP | COMMON_WORDS | GENERIC_ANCHORS) - SPACING_HEADS


class Linker:
    def __init__(self, entities: list[dict], embedder=None, vectors=None, vector_aliases=None):
        self.entities = {e['uid']: e for e in entities}
        self.aliases: dict[str, list[str]] = {}
        self.by_label: dict[str, dict[str, list[str]]] = {}
        self.fuzzy_aliases: dict[str, list[str]] = {}
        self.fuzzy_by_label: dict[str, dict[str, list[str]]] = {}
        self.vector_names = {e['uid']: set(allowed_names(e)) for e in entities}
        # PrimeKG grouped nodes can carry a truncated group label ("nephrotic syndrome,").
        # When it equals another entity's name of the same label, the name belongs to
        # that entity; the group stays reachable through its subtype names (D088).
        names: dict[tuple[str, str], int] = {}
        for e in entities:
            names[(e['label'], normalize(e['name']))] = names.get((e['label'], normalize(e['name'])), 0) + 1
        truncated = {e['uid'] for e in entities if e['uid'].startswith('MONDO_grouped')
                     and re.search(r'[,;:]\s*$', e['name']) and names[(e['label'], normalize(e['name']))] > 1}
        for e in entities:
            # RxNorm aliases may identify literal mentions but must not become
            # spelling-correction or token-similarity targets (D101).
            for aliases, index, by_label in (
                (exact_names(e), self.aliases, self.by_label),
                (allowed_names(e), self.fuzzy_aliases, self.fuzzy_by_label),
            ):
                for alias in aliases:
                    key = normalize(alias)
                    if e['uid'] in truncated and key == normalize(e['name']):
                        continue
                    if key:
                        index.setdefault(key, []).append(e['uid'])
                        by_label.setdefault(e['label'], {}).setdefault(key, []).append(e['uid'])
        # Canonical names as written (case-folded word tokens, no plural strip): a name
        # shared by several entities denotes the one whose own name it is (D087).
        self.written_owners: dict[str, set[str]] = {}
        for e in entities:
            self.written_owners.setdefault(' '.join(re.findall(r'\w+', e['name'].casefold())), set()).add(e['uid'])
        # Keys whose own spelling has a comma or semicolon may span a list separator.
        self.separated = {normalize(a) for e in entities for a in exact_names(e) if re.search(r'[,;]', a)}
        self.embedder, self.vectors, self.vector_aliases = embedder, vectors, vector_aliases
        self.excluded_by_key: dict[str, set[str]] = {}
        for uid in self.entities.keys() & EXCLUDED_ALIASES.keys():
            for key in EXCLUDED_ALIASES[uid]:
                self.excluded_by_key.setdefault(key, set()).add(uid)
        self.quarantined_keys = set(self.excluded_by_key)
        self.alias_sizes = sorted({len(key.split()) for key in
                                   self.aliases.keys() | self.quarantined_keys}, reverse=True)
        # Names written with a missing or extra space ("hyper tension", "heartfailure"),
        # from the same names as spelling correction (no RxNorm-only aliases, D101).
        # A single word may only be a joined multi-word name: one-word names that the exact
        # pass skipped ("disease", common words) must not come back here.
        # Both with and without the plural strip, which differs inside a joined word
        # ("diabetesinsipidus", "toras emide"). Generic names ("medical condition") and
        # names with a single letter ("protein S deficiency", "Advantage-S") are left out:
        # their joined form is an ordinary word or phrase.
        self.compact_aliases: dict[str, set[str]] = {}
        self.joined_names: set[str] = set()
        # Words a space fix can treat as written on purpose: one of the joined words must
        # be none of these ("metfor min", "heartfailure"), so "lip edema" stays two words.
        self.known_words = set(COMMON_WORDS | PHRASE_STOP)
        for e in entities:
            for alias in allowed_names(e):
                key = normalize(alias)
                parts = re.findall(r'\w+', alias.casefold())
                self.known_words.update(key.split(), parts)
                if (not key or (e['uid'] in truncated and key == normalize(e['name']))
                        or key in GENERIC_ANCHORS or any(len(p) < 2 and not p.isdigit() for p in parts)):
                    continue
                for compact in {key.replace(' ', ''), ''.join(parts)}:
                    if len(compact) >= SPACING_MIN_CHARS and compact not in COMMON_WORDS:
                        self.compact_aliases.setdefault(compact, set()).add(e['uid'])
                        if ' ' in key:
                            self.joined_names.add(compact)
        # Single-edit correction is limited to long drug-name tokens. Short
        # acronyms, gene symbols and ordinary words require the existing rules.
        self.drug_spellings = {key:ids for key,ids in self.fuzzy_by_label.get('Drug',{}).items()
                               if key.isalpha() and len(key)>=8 and key not in COMMON_WORDS}

    def link(self, mention: str, label: str | None = None) -> list[Candidate]:
        aliases = self.by_label.get(label, {}) if label else self.aliases
        key = normalize(mention)
        if key in aliases:
            ids = sorted(set(aliases[key]))
            return [self._candidate(uid, 100, 'exact', len(ids)>1) for uid in ids]
        aliases = self.fuzzy_by_label.get(label, {}) if label else self.fuzzy_aliases
        # A reviewed conflicting name must not return through typo or vector
        # similarity to the entity whose exact mapping was quarantined.
        excluded = self.excluded_by_key.get(key, set())
        if (label in (None,'Drug') and key.isalpha() and len(key)>=8
                and key not in COMMON_WORDS):
            matches = process.extract(key,self.drug_spellings.keys(),
                scorer=DamerauLevenshtein.distance,score_cutoff=1,limit=None)
            scored = {}
            for alias,distance,_ in matches:
                for uid in self.drug_spellings[alias]:
                    if uid in excluded:
                        continue
                    score = 100*(1-distance/max(len(alias),len(key)))
                    scored[uid] = max(score,scored.get(uid,0))
            if scored:
                # A one-edit tie is never resolved by a normalized-score margin:
                # distinct nearby drug names are clinically meaningful alternatives.
                ranked = sorted(scored.items(),key=lambda item:(-item[1],item[0]))
                return [self._candidate(uid,score,'fuzzy',len(scored)>1)
                        for uid,score in ranked[:5]]
        matches = process.extract(key, aliases.keys(), scorer=fuzz.token_sort_ratio, limit=5,
                                  score_cutoff=92)
        scored = {}
        for alias, score, _ in matches:
            for uid in aliases[alias]:
                if uid in excluded:
                    continue
                scored[uid] = max(score, scored.get(uid, 0))
        if scored:
            ranked = sorted(scored.items(), key=lambda x: (-x[1], x[0]))
            ambiguous = len(ranked)>1 and ranked[0][1]-ranked[1][1]<3
            return [self._candidate(uid, score, 'fuzzy', ambiguous) for uid, score in ranked[:5]]
        if self.vectors is not None and self.embedder is not None:
            similarities = self.vectors @ self.embedder.encode([mention])[0]
            ranked = []
            seen = set()
            for i in np.argsort(-similarities):
                row = self.vector_aliases[int(i)]
                uid = row['uid']
                if similarities[i]<0.85:
                    break
                # Cached rows must still be eligible for embedding under the
                # current catalog, even if an alias has since become exact-only.
                if (uid not in self.entities or uid in excluded or
                        row['text'] not in self.vector_names[uid] or
                        is_excluded(uid, row['text'])):
                    continue
                if uid not in seen and (not label or self.entities[uid]['label']==label):
                    ranked.append((uid, float(similarities[i])))
                    seen.add(uid)
                if len(ranked)==5:
                    break
            ambiguous = len(ranked)>1 and ranked[0][1]-ranked[1][1]<0.02
            return [self._candidate(uid, score, 'vector', ambiguous) for uid, score in ranked]
        return []

    def partial_phrases(self, question: str, candidates: list[Candidate]) -> list[tuple[str, list[Candidate]]]:
        """Exact matches that cover only part of a noun phrase (D106).

        A modifier on the left ("giant cell" vasculitis, "jock" itch, "sleep" paralysis) or
        a head noun on the right (iron "overdose") can name a different entity than the
        matched part. Question words, relation and meta words, severity and time words,
        doses and product forms do not.
        """
        words = normalize(question).split()
        tokens = list(re.finditer(r'\w+', question))
        original = [t.group() for t in tokens]
        if len(words) != len(tokens):
            # Case folding split a word ("İ" -> "i" + a combining dot); spans cannot be mapped.
            return []
        # A phrase does not run across punctuation ("on [DATE]. Pains started") and stops at
        # a possessive "s" ("the patient's itch"); hyphens join ("auto-immune").
        joined = [bool(re.fullmatch(r"[ \t'’-]*", question[a.end():b.start()]))
                  for a, b in zip(tokens, tokens[1:])]
        spans: dict[tuple, list[Candidate]] = {}
        for candidate in candidates:
            if candidate.method == 'exact' and candidate.span:
                spans.setdefault(tuple(candidate.span), []).append(candidate)
        # Every kept name is occupied, including a corrected one ("hydrochlorothiazid").
        occupied = {i for c in candidates if c.span for i in range(*c.span)}

        def forms(i: int) -> set[str]:
            # Both forms: the plural strip turns "always" into "alway", "allergies" into "allergie".
            return {words[i], original[i].casefold()}

        def content(i: int) -> bool:
            return (i not in occupied and words[i].isalpha() and words[i] != 's'
                    and not forms(i) & PHRASE_STOP)
        found = []
        for (start, end), group in sorted(spans.items()):
            left = start
            while left > 0 and joined[left - 1] and content(left - 1):
                left -= 1
            right = end
            while (right < len(words) and joined[right - 1] and forms(right) & HEAD_NOUNS
                   and right not in occupied):
                right += 1
            if left < start or right > end:
                # The phrase as written, so a confirmed name can replace it in the question.
                found.append((' '.join(original[left:right]), group))
        return found

    def lookalikes(self, mention: str, exclude: set[str], max_edits: int = 2) -> set[str]:
        """Drugs and diseases other than `exclude` with an alias within `max_edits` edits (D105)."""
        key, found = normalize(mention), set()
        for label in ('Drug', 'Disease'):
            index = self.by_label.get(label, {})
            for alias, _, _ in process.extract(key, index.keys(), scorer=DamerauLevenshtein.distance,
                                               score_cutoff=max_edits, limit=None):
                found.update(index[alias])
        return found - exclude

    def edits_to(self, mention: str, uid: str) -> int:
        """Fewest edits from the mention to any exact alias of the entity."""
        key = normalize(mention)
        return min((DamerauLevenshtein.distance(key, normalize(alias))
                    for alias in exact_names(self.entities[uid])), default=99)

    def nearest(self, mention: str, max_edits: int = 2, limit: int = 3) -> list[Candidate]:
        """Drugs and diseases closest in spelling to an unresolved name, for a suggestion."""
        key, ranked = normalize(mention), {}
        for label in ('Drug', 'Disease'):
            index = self.by_label.get(label, {})
            for alias, distance, _ in process.extract(key, index.keys(), scorer=DamerauLevenshtein.distance,
                                                      score_cutoff=max_edits, limit=None):
                for uid in index[alias]:
                    ranked[uid] = min(distance, ranked.get(uid, 99))
        order = sorted(ranked, key=lambda uid: (ranked[uid], self.entities[uid]['name']))[:limit]
        return [self._candidate(uid, 100 - 10 * ranked[uid], 'suggestion', len(order) > 1) for uid in order]

    def capitals_only(self, candidate: Candidate) -> bool:
        """The mention, an ordinary-looking word not typed in capitals, matches only names
        written in capitals: acronyms and gene symbols ("hard" -> HARDS, "itch" -> ITCH), D116.
        Drugs are left out, since brand names are listed in capitals ("Jakafi" -> JAKAFI), and
        so are words with digits ("ifna2"), which are symbols rather than ordinary words."""
        mention = candidate.mention or ''
        if (len(mention.split()) != 1 or mention.isupper() or not mention.isalpha()
                or self.entities[candidate.uid]['label'] == 'Drug'):
            return False
        key = normalize(mention)
        names = [a for a in exact_names(self.entities[candidate.uid]) if normalize(a) == key]
        return bool(names) and all(len(a) > 1 and a.isupper() for a in names)

    def neighbors(self, mention: str, exclude: set[str], limit: int = 4,
                  threshold: float = 0.83) -> list[Candidate]:
        """Vector-similar catalog names of a mention other than `exclude` ("itch" -> Pruritus,
        through its name "Itching"): alternatives to an exact acronym match (D116)."""
        if self.vectors is None or self.embedder is None:
            return []
        similarities = self.vectors @ self.embedder.encode([mention])[0]
        found = {}
        for i in np.argsort(-similarities)[:200]:
            if similarities[i] < threshold:
                break
            row = self.vector_aliases[int(i)]
            uid = row['uid']
            if (uid in exclude or uid in found or uid not in self.entities
                    or row['text'] not in self.vector_names[uid] or is_excluded(uid, row['text'])):
                continue
            found[uid] = self._candidate(uid, float(similarities[i]), 'vector', False)
            if len(found) == limit:
                break
        return list(found.values())

    def _candidate(self, uid: str, score: float, method: str, ambiguous: bool) -> Candidate:
        entity = self.entities[uid]
        return Candidate(uid, entity['name'], entity['label'], score, method, ambiguous)

    def in_question(self, question: str) -> list[Candidate]:
        return self.question_mentions(question)[0]

    def question_mentions(self, question: str, exact_only: bool = False) -> tuple[list[Candidate],list[str]]:
        """Link explicit mention spans independently, retaining unresolved anchors.

        exact_only stops after the exact alias pass (document text: no fuzzy spans).
        """
        words = normalize(question).split()
        original = re.findall(r'\w+',question)
        candidates, occupied, quarantined = {}, set(), []
        clitics = self.clitics(question, words)
        for size in self.alias_sizes:
            if size>len(words):
                continue
            for start in range(len(words)-size+1):
                positions = set(range(start, start+size))
                if occupied & positions or start in clitics:
                    continue
                key = ' '.join(words[start:start+size])
                if key in GENERIC_ANCHORS or ambiguous_word(key,' '.join(original[start:start+size])):
                    continue
                if key in self.aliases:
                    ids = sorted(set(self.aliases[key]))
                    for uid in ids:
                        candidates[uid] = self._candidate(uid, 100, 'exact', len(ids)>1)
                        candidates[uid].mention = ' '.join(original[start:start+size])
                        candidates[uid].span = (start,start+size)
                    occupied |= positions
                elif key in self.quarantined_keys:
                    # Reserve the whole rejected phrase so that a shorter alias
                    # inside it cannot silently identify a different substance.
                    occupied |= positions
                    quarantined.append(key)
        if exact_only:
            return list(candidates.values()),quarantined
        self._spacing(question, words, candidates, occupied, clitics)
        cues = {'of','for','about','with','does','and','between','versus','vs','is','are',
                'can','could','may'}
        stops = cues | {'interact','interacts','target','targets','treat','treats','is',
                        'are','has','have','associated','recorded','indicated','cause','causes','caused','causing',
                        'side','effects','phenotypes','symptoms','contraindicated','indications',
                        'be','been','being','used','using','prescribed',
                        # Relation phrasing, not names: "genes linked to X", "effects
                        # reported for X", "conditions that present with X" (D086).
                        'linked','link','links','reported','report','reports','present',
                        'presents','presenting','related','connected','implicated','involved'}
        # Relation and category words found by the v3 diagnosis (D092), in raw and
        # normalized form ("categories" normalizes to "categorie").
        relation_words = ('subtype subtypes subclass subclasses parent parents category categories '
                          'belong belongs broader unsafe safe combined combine trigger triggers molecular '
                          # Relation nouns ("contraindications for X") are not names (D113).
                          'contraindication contraindications indication interaction interactions')
        stops = stops | {w for word in relation_words.split() for w in (word, normalize(word))}
        # Words are compared in normalized form: "indications" is "indication" (D113).
        stops = stops | {normalize(word) for word in stops}
        generic = {'the','a','an','what','which','it','its','their','that','drug','drugs',
                   'disease','diseases','condition','conditions','gene','genes','protein',
                   'proteins','symptom','symptoms','phenotype','phenotypes','other','both',
                   'relationship','relationships','relation','relations','shared','common',
                   'how','can','could','should','i','you','we','explain','tell','list','find',
                   'information','data','evidence','these','those','some','any','warnings','warning',
                   'treatment','treatments','used','use','why','entities','anything','something',
                   'nothing','all','known','available','recorded'}
        unresolved = list(quarantined)
        interaction = bool(re.search(r'\binteract',question,re.I))
        labels = {c.label for c in candidates.values()}
        hint = 'Drug' if interaction else next(iter(labels)) if len(labels)==1 else None
        if hint is None and re.search(r'side effects?|targets?|indicated|contraindicated',question,re.I):
            hint = 'Drug'
        for start in range(len(words)):
            if (start and words[start-1] not in cues) or start in occupied or words[start] in generic:
                continue
            end = start
            while end<len(words) and end-start<12 and words[end] not in stops and end not in occupied:
                end += 1
            # A span such as "let me know which drug" is phrasing, not an entity:
            # drop leading generic/common words before treating it as a mention.
            first = start
            while first<end and (words[first] in generic or words[first] in COMMON_WORDS):
                first += 1
            if first==end:
                continue
            mention = ' '.join(words[first:end])
            linked = self.link(mention,hint)
            if linked:
                # Non-winning fuzzy/vector neighbors are alternatives, not extra
                # explicit anchors in a question. Preserve all ambiguous choices.
                for candidate in linked if linked[0].ambiguous else linked[:1]:
                    candidate.mention = ' '.join(original[first:end])
                    candidate.span = (first,end)
                    candidates.setdefault(candidate.uid,candidate)
                occupied.update(range(first,end))
            else:
                unresolved.append(mention)
        return list(candidates.values()),unresolved

    @staticmethod
    def clitics(question: str, words: list[str]) -> set[int]:
        """Word positions that end a contraction or possessive. Such an "s" never starts a
        name: "What's warfarin for?" is not (S)-Warfarin (D109). A name may still contain
        one ("Crohn's disease")."""
        tokens = list(re.finditer(r'\w+', question))
        if len(tokens) != len(words):
            return set()
        return {i for i in range(1, len(tokens))
                if re.fullmatch(r"['\u2019]", question[tokens[i - 1].end():tokens[i].start()])
                and tokens[i].group().casefold() in CLITICS}

    def _spacing(self, question: str, words: list[str], candidates: dict, occupied: set,
                 clitics: frozenset = frozenset()) -> None:
        """Names typed with a missing or extra space (D107).

        Up to eight adjacent words are joined and looked up without spaces ("para
        cetamol", "heartfailure", "autoimmunehemolytic anemia"); a single word may also be
        a name joined to a product or function word ("metformintablets"). A fix needs
        evidence of a wrong space: one of the words must be unknown (in no name and not a
        common word), so "lip edema" is not lipedema and "ramipril at" is not Ramiprilat.
        The window may not start or end with a common, relation or generic word, a phrase
        that is a name as written is left to the exact pass, and the longest window wins,
        replacing exact matches inside it. The name review uses a space fix with a note.
        """
        tokens = list(re.finditer(r'\w+', question))
        if len(tokens) != len(words):
            return
        raw = [t.group().casefold() for t in tokens]
        gaps = [question[a.end():b.start()] for a, b in zip(tokens, tokens[1:])]

        def forms(i: int) -> set[str]:
            return {words[i], raw[i]}
        for size in range(min(SPACING_MAX_WORDS, len(words)), 0, -1):
            for start in range(len(words) - size + 1):
                window = range(start, start + size)
                end = start + size - 1
                # Commas occur inside names ("bone dysplasia, lethal Holmgren").
                if (start in clitics or not all(words[i].isalnum() for i in window)
                        or forms(start) & SPACING_STOP or forms(end) & SPACING_STOP
                        or all(forms(i) & self.known_words for i in window)
                        or any(not re.fullmatch(r'[ \t,-]*', gaps[i]) for i in window[:-1])):
                    continue
                inside = [c for c in candidates.values()
                          if c.span and start <= c.span[0] and c.span[1] <= start + size]
                covered = {i for c in inside for i in range(*c.span)}
                if (occupied - covered) & set(window):
                    continue
                spaced = {' '.join(words[start:start + size]), ' '.join(raw[start:start + size])}
                if any(s in self.aliases or s in self.fuzzy_aliases for s in spaced):
                    continue
                ids = set()
                for compact in {s.replace(' ', '') for s in spaced}:
                    if size > 1 or compact in self.joined_names:
                        ids |= self.compact_aliases.get(compact, set())
                if not ids and size == 1:
                    ids = set(self._joined_tail(words[start]))
                # An entity already named elsewhere in the question keeps that mention.
                ids -= candidates.keys() - {c.uid for c in inside}
                if not ids:
                    continue
                for c in inside:
                    if not self._named_outside(words, c, window):
                        del candidates[c.uid]
                for uid in sorted(ids):
                    candidates[uid] = self._candidate(uid, 100, 'spacing', len(ids) > 1)
                    candidates[uid].mention = ' '.join(t.group() for t in tokens[start:start + size])
                    candidates[uid].span = (start, start + size)
                occupied.update(window)

    @staticmethod
    def _named_outside(words: list[str], candidate: Candidate, window: range) -> bool:
        """The candidate's mention also occurs outside the window ("diabetes ... type2 diabetes")."""
        key = normalize(candidate.mention or '').split()
        return any(words[p:p + len(key)] == key and not set(range(p, p + len(key))) & set(window)
                   for p in range(len(words) - len(key) + 1)) if key else False

    def _joined_tail(self, word: str) -> list[str]:
        """A name of 5+ letters followed by a product or function word, as one word."""
        if not word.isalpha() or len(word) < 9 or word in self.aliases:
            return []
        for cut in range(5, len(word) - 2):
            head, tail = word[:cut], word[cut:]
            if tail in SPACING_TAILS and head in self.fuzzy_aliases and head not in SPACING_STOP:
                return sorted(set(self.fuzzy_aliases[head]))
        return []

    def quarantined_mentions(self, unresolved: list[str]) -> list[str]:
        """Only unresolved reviewed names trigger the conservative query gate."""
        return sorted({mention for mention in unresolved if mention in self.quarantined_keys})

    def describe(self, candidates: list[Candidate]) -> list[dict]:
        return [asdict(c) for c in candidates]


def label_choices(candidates: list) -> list[list] | None:
    """Group ambiguous mentions whose readings differ only by label.

    PrimeKG often has a Disease and a Phenotype with the same name ("gout"). Such
    a mention is resolvable from the requested relation. Returns the groups (empty
    when nothing is ambiguous), or None when a mention has several readings of one
    label, or lacks a span, which only a clarification can resolve. Accepts
    Candidate objects or their describe() dictionaries.
    """
    def field(candidate,key):
        return candidate.get(key) if isinstance(candidate,dict) else getattr(candidate,key,None)
    groups: dict[tuple,list] = {}
    for candidate in candidates:
        if not field(candidate,'ambiguous'):
            continue
        span = field(candidate,'span')
        if not span:
            return None
        groups.setdefault(tuple(span),[]).append(candidate)
    for group in groups.values():
        labels = [field(c,'label') for c in group]
        if len(group)<2 or None in labels or len(set(labels))<len(labels):
            return None
    return list(groups.values())
