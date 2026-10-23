"""RxNorm preview wiring and corpus filtering, using local fictional fixtures."""

import builtins
import gzip
import hashlib
import json
import socket
import sys
from pathlib import Path

import pytest

from scripts import enrich_synonyms as enrich


def chunks(path: Path, texts: list[str]) -> Path:
    path.write_text(''.join(json.dumps({'text': text}) + '\n' for text in texts), encoding='utf8')
    return path


def test_lowercase_words_counts_occurrences_across_chunks_at_threshold(tmp_path):
    path = chunks(tmp_path/'chunks.jsonl', ['The aster aster minor', 'The aster minor'])
    assert enrich.lowercase_words(path) == {'aster'}


@pytest.mark.parametrize('punctuation', ['.', '!', '?'])
def test_lowercase_words_excludes_immediate_sentence_starts(tmp_path, punctuation):
    path = chunks(tmp_path/'chunks.jsonl', [f'End{punctuation} aster'] * 3)
    assert enrich.lowercase_words(path) == set()


def test_lowercase_words_uses_exact_case_and_whole_word_rule(tmp_path):
    path = chunks(tmp_path/'chunks.jsonl',
                  ['The Aster ASTER xaster aster-brand ab an'] * 3)
    assert enrich.lowercase_words(path) == {'xaster', 'aster-brand'}


def test_lowercase_words_preserves_specified_regex_at_text_start(tmp_path):
    path = chunks(tmp_path/'chunks.jsonl', ['aster'] * 3)
    assert enrich.lowercase_words(path) == {'aster'}


def rrf_row(size: int, values: dict[int, str]) -> str:
    fields = [''] * size
    for position, value in values.items():
        fields[position] = value
    return '|'.join(fields) + '|\n'


def preview_files(tmp_path: Path, brands: list[str]) -> tuple[Path, Path, Path]:
    raw, processed, rrf = tmp_path/'raw', tmp_path/'processed', tmp_path/'rrf'
    for directory in (raw, processed, rrf):
        directory.mkdir()
    with gzip.open(raw/'desc2026.gz', 'wb') as stream:
        stream.write(b'<DescriptorRecordSet/>')
    (raw/'mondo.obo').write_text('', encoding='utf8')
    (raw/'medlineplus.xml').write_text('<health-topics/>', encoding='utf8')
    entities = [{'uid': 'DrugBank:DB90001', 'label': 'Drug', 'name': 'Asterol',
                 'synonyms': ['Existingbrand']}]
    (processed/'entities.json').write_text(json.dumps(entities), encoding='utf8')
    chunks(processed/'chunks.jsonl', ['The calmer calmer calmer'])
    conso = rrf_row(18, {0: '1', 11: 'RXNORM', 12: 'IN', 14: 'Asterol', 16: 'N'})
    relations = []
    for index, brand in enumerate(brands, start=10):
        conso += rrf_row(18, {0: str(index), 11: 'RXNORM', 12: 'BN', 14: brand, 16: 'N'})
        relations.append(rrf_row(16, {0: str(index), 4: '1', 7: 'tradename_of', 10: 'RXNORM'}))
    (rrf/'RXNCONSO.RRF').write_text(conso, encoding='utf8')
    (rrf/'RXNREL.RRF').write_text(''.join(relations), encoding='utf8')
    return raw, processed, rrf


def deny_external_services(monkeypatch) -> None:
    original_import = builtins.__import__

    def checked_import(name, *args, **kwargs):
        assert name not in {'medkg.graph.store', 'medkg.ingest.link',
                            'scripts.embed_entities', 'openai', 'fastembed'}
        return original_import(name, *args, **kwargs)

    def deny_connect(*args, **kwargs):
        pytest.fail('Preview attempted a network connection')

    monkeypatch.setattr(builtins, '__import__', checked_import)
    monkeypatch.setattr(socket.socket, 'connect', deny_connect)
    monkeypatch.setattr(socket, 'create_connection', deny_connect)


def test_rxnorm_preview_reports_only_new_merged_aliases_without_applying(
        tmp_path, monkeypatch, capsys):
    raw, processed, rrf = preview_files(
        tmp_path, ['Starbrand', 'Existingbrand', 'Calmer', 'Ella'])
    catalog = processed/'entities.json'
    before = catalog.read_bytes()
    output = tmp_path/'preview.json'
    monkeypatch.setattr(enrich, 'ROOT', tmp_path)
    monkeypatch.setattr(enrich, 'RAW', raw)
    monkeypatch.setattr(enrich, 'PROCESSED', processed)
    monkeypatch.setattr(sys, 'argv', ['enrich_synonyms', '--cached-labels', '--rxnorm', str(rrf),
                                    '--output', str(output)])
    deny_external_services(monkeypatch)

    enrich.main()

    report = json.loads(capsys.readouterr().out)
    saved = json.loads(output.read_text(encoding='utf8'))
    assert catalog.read_bytes() == before
    assert not (tmp_path/'.cache').exists()
    assert set(path.name for path in processed.iterdir()) == {'entities.json', 'chunks.jsonl'}
    assert report['catalog_sha256'] == hashlib.sha256(before).hexdigest()
    assert report['rxnorm_brands_considered'] == 4
    assert report['rxnorm_proposed'] == 2
    assert sum(report['rxnorm_excluded_by_rule'].values()) == 2
    assert report['additions_by_source'] == {'rxnorm': 1}
    assert report['skipped'] == {'already_present': 1}
    assert report['rxnorm_examples'] == [
        {'brand': 'Starbrand', 'entity': 'Asterol', 'uid': 'DrugBank:DB90001',
         'source': 'rxnorm:10'}]
    assert saved == {**report, 'proposed_additions': [
        {'alias': 'Starbrand', 'label': 'Drug', 'uid': 'DrugBank:DB90001', 'source': 'rxnorm:10'}]}


def test_rxnorm_preview_examples_are_deterministic_and_capped_at_ten(
        tmp_path, monkeypatch, capsys):
    brands = [f'Fictional brand {letter}' for letter in 'lkjihgfedcba']
    raw, processed, rrf = preview_files(tmp_path, brands)
    monkeypatch.setattr(enrich, 'RAW', raw)
    monkeypatch.setattr(enrich, 'PROCESSED', processed)
    monkeypatch.setattr(sys, 'argv', ['enrich_synonyms', '--rxnorm', str(rrf)])
    deny_external_services(monkeypatch)

    enrich.main()

    report = json.loads(capsys.readouterr().out)
    assert report['rxnorm_proposed'] == 12
    assert report['additions_by_source'] == {'rxnorm': 12}
    assert [example['brand'] for example in report['rxnorm_examples']] == sorted(brands)[:10]


def test_preview_without_rxnorm_keeps_existing_report_and_needs_no_chunks(
        tmp_path, monkeypatch, capsys):
    raw, processed, _ = preview_files(tmp_path, [])
    monkeypatch.setattr(enrich, 'RAW', raw)
    monkeypatch.setattr(enrich, 'PROCESSED', processed)
    monkeypatch.setattr(sys, 'argv', ['enrich_synonyms'])

    def deny_corpus_read(path):
        pytest.fail('Preview without --rxnorm attempted to read corpus words')

    monkeypatch.setattr(enrich, 'lowercase_words', deny_corpus_read)
    deny_external_services(monkeypatch)

    enrich.main()

    report = json.loads(capsys.readouterr().out)
    assert not any(key.startswith('rxnorm_') for key in report)
