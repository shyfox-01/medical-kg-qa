"""Build the frozen LiveQA real-question benchmark from local inputs (D097).

    python -m eval.build_liveqa --dry-run  # statistics and summary-wording samples
    python -m eval.build_liveqa            # create the dataset and manifest once

NLM annotations determine eligibility; catalog names determine exact links; the
CSV graph determines gold. No QA linker, model, network or Neo4j is used.
"""

import argparse
import hashlib
import json
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

from eval import generate_v2 as v2
from eval.generate_v3 import RELATIONS, Graph, single_query
from medkg_data.ontology import load_obo
from medkg_data.primekg import read_graph

ROOT = Path(__file__).resolve().parents[1]
XML = (ROOT / 'data/raw/liveqa_trec2017/TestDataset/'
       'TREC-2017-LiveQA-Medical-Test-Questions-w-summaries.xml')
SUPERSEDED = ROOT / 'eval/datasets/liveqa_v1.jsonl'
DATASET = ROOT / 'eval/datasets/liveqa_v2.jsonl'
MANIFEST = ROOT / 'eval/datasets/MANIFEST_liveqa.json'
VERSION = 'liveqa-2'
EXPECTED_ROWS = 208
LABELS = {'Problem': 'Disease', 'DrugSupplement': 'Drug'}
RULES = {
    ('TREATMENT', ('Problem',)): 'drugs_for',
    ('INDICATION', ('DrugSupplement',)): 'indications',
    ('SIDE_EFFECT', ('DrugSupplement',)): 'side_effects',
    ('SYMPTOM', ('Problem',)): 'phenotypes',
    ('CONTRAINDICATION', ('DrugSupplement',)): 'contraindications',
    ('INTERACTION', ('DrugSupplement', 'DrugSupplement')): 'interaction_yesno',
    ('INTERACTION', ('DrugSupplement',)): 'interactions',
}
YESNO_QUERY = ('MATCH (a:Drug {uid:$a})-[:INTERACTS_WITH]-(b:Drug {uid:$b}) '
               'RETURN DISTINCT b.uid AS uid')
SOURCE = {
    'url': 'https://github.com/abachaa/LiveQA_MedicalTask_TREC2017',
    'license': 'CC BY 4.0',
    'license_url': 'https://creativecommons.org/licenses/by/4.0/',
    'citation': {
        'authors': ['Asma Ben Abacha', 'Eugene Agichtein', 'Yuval Pinter',
                    'Dina Demner-Fushman'],
        'title': 'Overview of the Medical Question Answering Task at TREC 2017 LiveQA',
        'year': 2017,
        'url': 'https://trec.nist.gov/pubs/trec26/papers/Overview-QA.pdf',
    },
}


def key(text: str) -> str:
    """NFKC, lowercase, and collapse runs of non-alphanumeric characters."""
    normalized = unicodedata.normalize('NFKC', text).lower()
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in normalized).split())


def build_index(catalog: list[dict]) -> dict[tuple[str, str], set[str]]:
    """Index catalog names and synonyms separately within each entity label."""
    index = defaultdict(set)
    for entity in catalog:
        for name in [entity['name'], *(entity.get('synonyms') or [])]:
            normalized = key(name)
            if normalized:
                index[(entity['label'], normalized)].add(entity['uid'])
    return dict(index)


def link_focus(focus: dict, index: dict[tuple[str, str], set[str]]) -> dict:
    return link_entity(focus, LABELS.get(focus['category']), index)


def link_entity(annotation: dict, label: str | None,
                index: dict[tuple[str, str], set[str]]) -> dict:
    candidates = index.get((label, key(annotation['text'])), set()) if label else set()
    status = 'linked' if len(candidates) == 1 else 'ambiguous' if candidates else 'unlinked'
    return {**annotation, 'uid': next(iter(candidates)) if status == 'linked' else None,
            'status': status}


def _one(parent: ET.Element, tag: str) -> ET.Element:
    matches = parent.findall(tag)
    if len(matches) != 1:
        raise ValueError(f'Unexpected LiveQA XML structure: expected exactly one {tag}')
    return matches[0]


def _text(element: ET.Element) -> str:
    if len(element):
        raise ValueError(f'Unexpected LiveQA XML structure: nested text in {element.tag}')
    return (element.text or '').strip()


def read_questions(root: ET.Element) -> list[dict]:
    """Validate XML structure and flag duplicate or dangling annotation IDs."""
    if root.tag != 'LiveQA2017-Medical-Test-Set-Full':
        raise ValueError(f'Unexpected LiveQA XML root: {root.tag}')
    questions, seen = [], set()
    for element in root:
        qid = element.get('qid', '').strip()
        if element.tag != 'NLM-QUESTION' or not qid or qid in seen:
            raise ValueError('Unexpected LiveQA XML structure: invalid or duplicate question')
        seen.add(qid)
        original = _one(element, 'Original-Question')
        annotations = _one(element, 'ANNOTATIONS')
        foci, fids = [], set()
        malformed = False
        for focus in annotations.findall('FOCUS'):
            fid, category = focus.get('fid', '').strip(), focus.get('fcategory', '').strip()
            text = _text(focus)
            if not fid or not category or not text:
                raise ValueError(f'Unexpected LiveQA XML structure: invalid FOCUS in {qid}')
            malformed |= fid in fids
            fids.add(fid)
            foci.append({'fid': fid, 'text': text, 'category': category})
        keywords, kids = [], set()
        for keyword in annotations.findall('KEYWORD'):
            kid = keyword.get('kid', '').strip()
            category = keyword.get('kcategory', '').strip()
            text = _text(keyword)
            if not kid or not category or not text:
                raise ValueError(f'Unexpected LiveQA XML structure: invalid KEYWORD in {qid}')
            malformed |= kid in kids
            kids.add(kid)
            keywords.append({'kid': kid, 'text': text, 'category': category})
        types = []
        for annotation in annotations.findall('TYPE'):
            name = _text(annotation)
            refs = [fid.strip() for fid in annotation.get('hasFocus', '').split(',')]
            keyword_text = annotation.get('hasKeyword', '').strip()
            keyword_refs = [kid.strip() for kid in keyword_text.split(',')] if keyword_text else []
            if (not name or not all(refs) or len(set(refs)) != len(refs)
                    or not all(keyword_refs) or len(set(keyword_refs)) != len(keyword_refs)):
                raise ValueError(f'Unexpected LiveQA XML structure: invalid TYPE in {qid}')
            malformed |= not set(refs) <= fids or not set(keyword_refs) <= kids
            types.append({'name': name, 'refs': refs, 'keyword_refs': keyword_refs})
        if not foci or not types:
            raise ValueError(f'Unexpected LiveQA XML structure: missing annotations in {qid}')
        questions.append({'qid': qid, 'subject': _text(_one(original, 'SUBJECT')),
                          'message': _text(_one(original, 'MESSAGE')),
                          'summary': _text(_one(element, 'NLM-Summary')),
                          'foci': foci, 'types': types, 'keywords': keywords,
                          'malformed_annotation': malformed})
    return questions


def original_question(subject: str, message: str) -> str:
    subject, message = subject.strip(), message.strip()
    if not subject or key(message).startswith(key(subject)):
        return message
    return f'{subject}\n{message}'.strip()


def _eligible(question: dict, foci: list[dict]) -> tuple[str | None, list[dict]]:
    if len(question['types']) != 1:
        return None, []
    annotation = question['types'][0]
    by_id = {focus['fid']: focus for focus in foci}
    selected = [by_id[fid] for fid in annotation['refs']]
    categories = tuple(focus['category'] for focus in selected)
    return RULES.get((annotation['name'], categories)), selected


def pair_query(intent: str) -> str:
    anchor, target, relation, direction = RELATIONS[intent]
    arrow = v2.ARROWS[direction].format(r=relation)
    return (f'MATCH (a:{anchor} {{uid:$a}}){arrow}(b:{target} {{uid:$b}}) '
            'RETURN DISTINCT b.uid AS uid')


def _classify(question: dict, foci: list[dict], keywords: list[dict], graph: Graph,
              index: dict[tuple[str, str], set[str]]) -> dict:
    result = {'split': 'liveqa_observe', 'scope': 'out', 'kind': 'list',
              'category': 'real_observe', 'capability': 'real.observe', 'intent': None,
              'expected': [], 'gold_query': '', 'gold_params': {}}
    if any(annotation['name'] == 'DOSAGE' for annotation in question['types']):
        return {**result, 'split': 'liveqa', 'scope': 'in', 'kind': 'refusal',
                'category': 'real_safety', 'capability': 'real.dosage_refusal',
                'reason': 'A DOSAGE annotation requires refusal regardless of other annotations.'}
    if question['malformed_annotation']:
        return {**result, 'reason': 'malformed annotation: duplicate or missing ids'}
    intent, selected = _eligible(question, foci)
    if intent is None:
        reason = ('Multiple TYPE annotations are outside the single-type scoring rules.'
                  if len(question['types']) != 1 else
                  'The TYPE or its referenced focus categories/count do not match a scoring rule.')
        return {**result, 'reason': reason}
    missing = [focus for focus in selected if focus['status'] != 'linked']
    if missing:
        detail = ', '.join(f"{focus['fid']}={focus['status']}" for focus in missing)
        return {**result, 'split': 'liveqa_gap', 'category': 'real_gap',
                'capability': 'real.gap',
                'reason': f'The supported annotation has no unique catalog match for {detail}.'}
    selected_keywords = []
    if intent != 'interaction_yesno':
        refs = question['types'][0]['keyword_refs']
        for keyword in keywords:
            if keyword['kid'] in refs:
                keyword.update(link_entity(keyword, RELATIONS[intent][1], index))
                selected_keywords.append(keyword)
        if selected_keywords and (len(selected_keywords) != 1
                                  or selected_keywords[0]['status'] != 'linked'):
            return {**result, 'reason': 'keywords not representable as one graph pair'}
    result.update(split='liveqa', scope='in', category=f'real_{intent}',
                  capability=f'real.{intent}', intent=intent)
    if intent == 'interaction_yesno':
        a, b = (focus['uid'] for focus in selected)
        answer = b in graph.targets('interactions', a)
        result.update(kind='yesno', expected=[b] if answer else [], expected_answer=answer,
                      intent='interactions', target_label='Drug', gold_query=YESNO_QUERY,
                      gold_params={'a': a, 'b': b})
    elif selected_keywords:
        a, b = selected[0]['uid'], selected_keywords[0]['uid']
        answer = b in graph.targets(intent, a)
        capability = 'interaction_yesno' if intent == 'interactions' else f'{intent}_yesno'
        result.update(kind='yesno', expected=[b] if answer else [], expected_answer=answer,
                      target_label=RELATIONS[intent][1], gold_query=pair_query(intent),
                      gold_params={'a': a, 'b': b}, capability=f'real.{capability}')
        if intent == 'interactions':
            result['category'] = 'real_interaction_yesno'
    else:
        uid = selected[0]['uid']
        expected = sorted(graph.targets(intent, uid))
        result.update(expected=expected, kind='list' if expected else 'none',
                      gold_query=single_query(intent), gold_params={'uid': uid})
        if not expected:
            result['target_label'] = RELATIONS[intent][1]
    return {**result, 'reason': 'The supported annotation links uniquely; gold comes from the CSV graph.'}


def build_rows(root: ET.Element, graph: Graph, catalog: list[dict]) -> list[dict]:
    index = build_index(catalog)
    catalog_by_uid = {entity['uid']: entity for entity in catalog}
    rows = []
    for question in read_questions(root):
        foci = [link_focus(focus, index) for focus in question['foci']]
        keywords = [{**keyword, 'uid': None, 'status': 'not_used'}
                    for keyword in question['keywords']]
        classification = _classify(question, foci, keywords, graph, index)
        reason = classification.pop('reason')
        expected = classification['expected']
        common = {**classification,
                  'expected_names': {uid: [catalog_by_uid[uid]['name']] for uid in expected
                                     if uid in catalog_by_uid},
                  'anchors': [focus['text'] for focus in foci],
                  'anchor_uids': sorted(focus['uid'] for focus in foci if focus['uid']),
                  'recall_applicable': classification['kind'] == 'list'
                                       and len(expected) <= v2.RECALL_MAX,
                  'anchor_pool': 'real', 'test_type': 'REAL', 'pair_id': question['qid'],
                  'generator_version': VERSION,
                  'liveqa': {'qid': question['qid'],
                             'types': [annotation['name'] for annotation in question['types']],
                             'type_focus_ids': [annotation['refs']
                                                for annotation in question['types']],
                             'type_keyword_ids': [annotation['keyword_refs']
                                                  for annotation in question['types']],
                             'foci': foci, 'keywords': keywords,
                             'malformed_annotation': question['malformed_annotation'],
                             'reason': reason}}
        for wording, suffix, text in [
                ('original', 'orig', original_question(question['subject'], question['message'])),
                ('summary', 'sum', question['summary'])]:
            rows.append({**common, 'id': f"liveqa-{question['qid']}-{suffix}", 'wording': wording,
                         'question': text, 'question_template': text})
    return rows


def summarize(rows: list[dict]) -> dict:
    """Count rows by wording, but each annotation only once per question."""
    focus_counts = defaultdict(Counter)
    keyword_counts = defaultdict(Counter)
    unmatched = set()
    originals = [row for row in rows if row['wording'] == 'original']
    for row in originals:
        for focus in row['liveqa']['foci']:
            focus_counts[focus['category']][focus['status']] += 1
        for keyword in row['liveqa']['keywords']:
            keyword_counts[keyword['category']][keyword['status']] += 1
        if row['split'] == 'liveqa_gap':
            selected = set(row['liveqa']['type_focus_ids'][0])
            for focus in row['liveqa']['foci']:
                if focus['fid'] in selected and focus['status'] != 'linked':
                    unmatched.add(focus['text'])
    return {'rows': len(rows), 'questions': len(originals),
            **{field: dict(sorted(Counter(row[field] for row in rows).items()))
               for field in ('split', 'capability', 'kind', 'wording')},
            'scorable_capability': dict(sorted(Counter(
                row['capability'] for row in rows if row['scope'] == 'in').items())),
            'focus_linking': {category: {status: counts[status]
                                        for status in ('linked', 'unlinked', 'ambiguous')}
                              for category, counts in sorted(focus_counts.items())},
            'keyword_linking': {category: {status: counts[status]
                                          for status in ('linked', 'unlinked', 'ambiguous', 'not_used')}
                                for category, counts in sorted(keyword_counts.items())},
            'unmatched_foci': sorted(unmatched)}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_outputs(dataset: Path, manifest_path: Path,
                  superseded_sha256: str | None = None) -> bool:
    """Allow only the documented v1 manifest transition; never replace a dataset."""
    if dataset.exists():
        raise FileExistsError('LiveQA output already exists; frozen outputs are never overwritten')
    if not manifest_path.exists():
        return False
    if dataset.name == 'liveqa_v2.jsonl' and superseded_sha256:
        try:
            previous = json.loads(manifest_path.read_text(encoding='utf8'))
        except (ValueError, UnicodeError):
            previous = None
        if (isinstance(previous, dict) and previous.get('generator_version') == 'liveqa-1'
                and previous.get('dataset') == 'eval/datasets/liveqa_v1.jsonl'
                and previous.get('dataset_sha256') == superseded_sha256):
            return True
    raise FileExistsError('LiveQA manifest already exists; only a verified v1 manifest can be upgraded')


def write_outputs(rows: list[dict], manifest: dict, dataset: Path, manifest_path: Path) -> None:
    superseded_hash = (manifest.get('superseded', {}).get('liveqa_v1.jsonl', {}).get('sha256')
                       if manifest.get('generator_version') == VERSION else None)
    upgrading = check_outputs(dataset, manifest_path, superseded_hash)
    payload = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode('utf8')
    manifest = {**manifest, 'dataset_sha256': hashlib.sha256(payload).hexdigest()}
    metadata = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf8')
    # Freeze the dataset before updating the shared manifest. Partial outputs remain
    # for manual inspection on failure; a subsequent run must not overwrite them.
    with dataset.open('xb') as output:
        output.write(payload)
    with manifest_path.open('wb' if upgrading else 'xb') as manifest_output:
        manifest_output.write(metadata)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dry-run', action='store_true',
                        help='Print statistics and up to five summary samples per split; write nothing')
    args = parser.parse_args()
    try:
        superseded_hash = digest(SUPERSEDED)
        if not args.dry_run:
            check_outputs(DATASET, MANIFEST, superseded_hash)
        root = ET.parse(XML).getroot()
        # Validate source structure before loading the much larger CSV graph.
        read_questions(root)
        raw, processed = ROOT / 'data/raw', ROOT / 'data/processed'
        nodes, edges, _ = read_graph(raw / 'kg.csv', load_obo(raw / 'mondo.obo'),
                                   load_obo(raw / 'hp.obo'))
        catalog = json.loads((processed / 'entities.json').read_text(encoding='utf8'))
        rows = build_rows(root, Graph(nodes, edges), catalog)
        if len(rows) != EXPECTED_ROWS:
            raise ValueError(f'Expected {EXPECTED_ROWS} LiveQA rows; got {len(rows)}; stopping')
        stats = summarize(rows)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        if args.dry_run:
            for split in sorted(stats['split']):
                samples = [row for row in rows
                           if row['split'] == split and row['wording'] == 'summary'][:5]
                for row in samples:
                    print(f"[{split}/{row['capability']}/{row['kind']}] {row['question']}")
            return
        inputs = {'xml': XML, 'kg': raw / 'kg.csv', 'catalog': processed / 'entities.json',
                  'mondo': raw / 'mondo.obo', 'hp': raw / 'hp.obo'}
        manifest = {'generator_version': VERSION, 'source': SOURCE,
                    'inputs': {name: {'path': path.relative_to(ROOT).as_posix(),
                                      'sha256': digest(path)} for name, path in inputs.items()},
                    'dataset': DATASET.relative_to(ROOT).as_posix(), 'statistics': stats,
                    'superseded': {SUPERSEDED.name: {
                        'sha256': superseded_hash,
                        'reason': 'mapping ignored keywords; never evaluated'}},
                    'malformed_annotations': sorted({row['pair_id'] for row in rows
                                                     if row['liveqa']['malformed_annotation']}),
                    'focus_count_unit': 'NLM FOCUS annotation, once per question',
                    'keyword_count_unit': 'NLM KEYWORD annotation, once per question',
                    'row_count_unit': 'question wording; each question has original and summary'}
        write_outputs(rows, manifest, DATASET, MANIFEST)
        print(f'Created {DATASET.relative_to(ROOT)} and {MANIFEST.relative_to(ROOT)}')
    except (OSError, ValueError, ET.ParseError) as error:
        raise SystemExit(str(error)) from error


if __name__ == '__main__':
    main()
