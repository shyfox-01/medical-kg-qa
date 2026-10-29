"""The b5 batch excludes every earlier anchor and is never overwritten (D127)."""

import json

import pytest

from eval import generate_v3 as v3
from eval import generate_v3_b5 as b5


def test_excluded_anchors_cover_every_earlier_structured_set(tmp_path):
    for index, name in enumerate(b5.PREVIOUS_DATASETS):
        (tmp_path / name).write_text(json.dumps({'anchor_uids': [f'fiction:old:{index}']}) + '\n',
                                     encoding='utf8')
    assert 'structured_v3_b4.jsonl' in b5.PREVIOUS_DATASETS
    assert b5.excluded_anchors(tmp_path) == {f'fiction:old:{i}' for i in range(len(b5.PREVIOUS_DATASETS))}


@pytest.mark.parametrize('missing', b5.PREVIOUS_DATASETS)
def test_a_missing_history_is_rejected(tmp_path, missing):
    for name in b5.PREVIOUS_DATASETS:
        if name != missing:
            (tmp_path / name).write_text('{"anchor_uids": []}\n', encoding='utf8')
    with pytest.raises(FileNotFoundError, match=missing):
        b5.excluded_anchors(tmp_path)


def test_existing_outputs_are_never_overwritten(tmp_path):
    dataset, manifest = tmp_path / 'b5.jsonl', tmp_path / 'manifest.json'
    dataset.write_bytes(b'frozen output\n')
    with pytest.raises(FileExistsError):
        b5.write_outputs([], set(), tmp_path, tmp_path, dataset, manifest)
    assert dataset.read_bytes() == b'frozen output\n'
    assert not manifest.exists()


def test_b5_ids():
    rows = v3.finish([{'kind': 'list', 'question': 'Which drugs treat Orion fever?'}], 'b5')
    assert rows[0]['id'] == 'v3-b5-0001' and rows[0]['split'] == 'b5'


def test_b6_excludes_b5_too_and_keeps_its_own_ids():
    from eval import generate_v3_b6 as b6
    assert b6.PREVIOUS_DATASETS[-1] == 'structured_v3_b5.jsonl' and b6.SEED_B6 != b5.SEED_B5
    rows = v3.finish([{'kind': 'list', 'question': 'Which drugs treat Orion fever?'}], 'b6')
    assert rows[0]['id'] == 'v3-b6-0001' and rows[0]['split'] == 'b6'
