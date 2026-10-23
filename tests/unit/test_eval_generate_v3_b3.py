"""Fresh-batch generation and freezing, using synthetic inputs only (D098)."""

import hashlib
import json
import sys

import pytest

from eval import generate_v3 as v3
from eval import generate_v3_b3 as b3


def histories(directory):
    for index, name in enumerate(b3.PREVIOUS_DATASETS):
        rows = [{'anchor_uids': [f'fiction:old:{index}', 'fiction:shared'],
                 'question': 'Synthetic historical question must not appear in output'},
                {'anchor_uids': []}]
        (directory / name).write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf8')


def case(kind='list', **extra):
    return {'kind': kind, 'question': 'Which drugs treat Orion fever?',
            'question_template': 'Which drugs treat Orion fever?', 'anchors': ['Orion fever'],
            'anchor_uids': ['fiction:disease:orion'], 'expected': ['fiction:drug:asterol'],
            'test_type': 'MFT', 'capability': 'single.drugs_for', **extra}


def test_excluded_anchors_union_all_four_histories_including_sealed(tmp_path, capsys):
    histories(tmp_path)
    assert b3.excluded_anchors(tmp_path) == {'fiction:shared', *(
        f'fiction:old:{index}' for index in range(4))}
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('missing', b3.PREVIOUS_DATASETS)
def test_missing_history_is_rejected_instead_of_silently_weakening_exclusion(tmp_path, missing):
    for name in b3.PREVIOUS_DATASETS:
        if name != missing:
            (tmp_path / name).write_text('{"anchor_uids": []}\n', encoding='utf8')
    with pytest.raises(FileNotFoundError, match=missing):
        b3.excluded_anchors(tmp_path)


@pytest.mark.parametrize('existing', ['dataset', 'manifest'])
def test_either_existing_output_refuses_writing_and_preserves_files(tmp_path, existing):
    dataset, manifest = tmp_path / 'b3.jsonl', tmp_path / 'manifest.json'
    frozen = dataset if existing == 'dataset' else manifest
    other = manifest if existing == 'dataset' else dataset
    frozen.write_bytes(b'frozen output\n')
    with pytest.raises(FileExistsError):
        b3.ensure_new_outputs(dataset, manifest)
    with pytest.raises(FileExistsError):
        b3.write_outputs([], set(), tmp_path, tmp_path, dataset, manifest)
    assert frozen.read_bytes() == b'frozen output\n'
    assert not other.exists()


@pytest.mark.parametrize('start', [1, 17])
def test_finish_assigns_b3_ids_and_version_without_sealing(start):
    rows = v3.finish([case(), case('count')], 'b3', start)
    assert [row['id'] for row in rows] == [f'v3-b3-{number:04d}' for number in (start, start + 1)]
    assert all(row['split'] == 'b3' and row['generator_version'] == v3.VERSION for row in rows)
    assert all('sealed' not in row and row['paraphrase_status'] == 'template' for row in rows)


def test_build_rewords_eligible_mft_after_ids_and_before_invariance(monkeypatch):
    mft = [case(), case('count'), case(history_questions=['What is Orion fever?']),
           case('none'), case('yesno')]
    other = [case(test_type='DIR', capability='dir.base_list')]
    events = []

    class Builder:
        def part(self, scale):
            assert scale == 1.0
            events.append('part')
            return mft, other

        def invariance(self, bases, number):
            assert bases is mft and number == 1
            assert events == ['part', 'reword']
            assert bases[0]['question'] == 'Which medicines treat Orion fever?'
            events.append('invariance')
            return [{**bases[0], 'test_type': 'INV', 'capability': 'inv.wrapper',
                     'question': 'Please tell me: ' + bases[0]['question'], '_base': bases[0]}]

    def reword(rows, share, *, seed):
        assert rows == mft[:2]
        assert share == 0.6 and seed == 3032
        assert [row['id'] for row in rows] == ['v3-b3-0001', 'v3-b3-0002']
        events.append('reword')
        rows[0].update(question='Which medicines treat Orion fever?', paraphrase_status='llm_validated')

    monkeypatch.setattr(b3, 'reword', reword)
    rows = b3.build_rows(Builder())
    assert events == ['part', 'reword', 'invariance']
    assert rows == mft + other + [rows[-1]]
    assert rows[-1]['id'] == 'v3-b3-0007' and rows[-1]['base_id'] == 'v3-b3-0001'
    assert '_base' not in rows[-1]


def test_cli_dry_run_never_calls_model_or_writes_and_prints_25_samples(tmp_path, monkeypatch, capsys):
    datasets = tmp_path / 'eval/datasets'
    processed = tmp_path / 'data/processed'
    datasets.mkdir(parents=True)
    processed.mkdir(parents=True)
    histories(datasets)
    (processed / 'entities.json').write_text('[]', encoding='utf8')
    (processed / 'documents.jsonl').write_text('', encoding='utf8')
    (processed / 'synonym_additions.jsonl').write_text('', encoding='utf8')
    dataset, manifest = datasets / 'structured_v3_b3.jsonl', datasets / 'MANIFEST_v3_b3.json'
    before = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError('Dry-run must not call a model or write outputs')

    class Builder:
        def __init__(self, graph, catalog, documents, additions, **kwargs):
            assert catalog == documents == additions == []
            assert kwargs == {'seed': 3032, 'qualifiers': set(), 'brands': {}, 'lay': {},
                              'excluded': {'fiction:shared', *(f'fiction:old:{i}' for i in range(4))}}

        def part(self, scale):
            assert scale == 1.0
            return [case() for _ in range(26)], []

        def invariance(self, bases, number):
            assert number == 3
            return []

    monkeypatch.setattr(b3, 'ROOT', tmp_path)
    monkeypatch.setattr(b3, 'DATASET', dataset)
    monkeypatch.setattr(b3, 'MANIFEST', manifest)
    monkeypatch.setattr(b3, 'Builder', Builder)
    monkeypatch.setattr(b3, 'read_graph', lambda *args: ([], [], {}))
    monkeypatch.setattr(b3, 'load_obo', lambda path: {})
    monkeypatch.setattr(b3.v2, 'hpo_qualifiers', lambda ontology: set())
    monkeypatch.setattr(b3.v2, 'fda_brands', lambda path: {})
    monkeypatch.setattr(b3.v2, 'lay_names', lambda path, documents: {})
    monkeypatch.setattr(b3, 'reword', forbidden)
    monkeypatch.setattr(b3, 'write_outputs', forbidden)
    monkeypatch.setattr(sys, 'argv', ['eval.generate_v3_b3', '--dry-run'])
    b3.main()

    output = capsys.readouterr().out
    stats, _ = json.JSONDecoder().raw_decode(output)
    assert stats == {'rows': 26, 'test_types': {'MFT': 26},
                     'capabilities': {'single.drugs_for': 26}, 'paraphrases': {'template': 26},
                     'excluded_anchors': 5}
    assert sum(line.startswith('[') for line in output.splitlines()) == 25
    assert 'Synthetic historical question' not in output
    assert not dataset.exists() and not manifest.exists()
    assert {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()} == before


def test_write_outputs_records_hashes_counts_model_and_freezes(tmp_path, monkeypatch):
    raw, processed = tmp_path / 'raw', tmp_path / 'processed'
    raw.mkdir()
    processed.mkdir()
    kg, catalog = raw / 'kg.csv', processed / 'entities.json'
    kg.write_bytes(b'fictional graph\n')
    catalog.write_bytes(b'[]\n')
    rows = v3.finish([case(paraphrase_status='llm_validated'),
                      case(test_type='INV', capability='inv.wrapper')], 'b3')
    dataset, manifest = tmp_path / 'b3.jsonl', tmp_path / 'manifest.json'
    monkeypatch.setenv('LLM_MODEL', 'fictional-reworder')
    metadata = b3.write_outputs(rows, {'fiction:old:a'}, raw, processed, dataset, manifest)
    assert [json.loads(line) for line in dataset.read_text(encoding='utf8').splitlines()] == rows
    assert json.loads(manifest.read_text(encoding='utf8')) == metadata
    for field, path in [('dataset_sha256', dataset), ('kg_sha256', kg), ('catalog_sha256', catalog)]:
        assert metadata[field] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert metadata['generator_version'] == v3.VERSION and metadata['seed'] == 3032
    assert metadata['excluded_anchors'] == 1
    assert metadata['anchor_sources'] == list(b3.PREVIOUS_DATASETS)
    assert metadata['paraphrase_model'] == 'fictional-reworder' and metadata['reword_share'] == 0.6
    assert metadata['rows'] == 2 and metadata['test_types'] == {'MFT': 1, 'INV': 1}
    assert metadata['capabilities'] == {'single.drugs_for': 1, 'inv.wrapper': 1}
    assert metadata['paraphrases'] == {'llm_validated': 1, 'template': 1}
    frozen = dataset.read_bytes(), manifest.read_bytes()
    with pytest.raises(FileExistsError):
        b3.write_outputs([], set(), raw, processed, dataset, manifest)
    assert (dataset.read_bytes(), manifest.read_bytes()) == frozen
