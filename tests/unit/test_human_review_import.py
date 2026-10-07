"""Fictional review import preserves evidence and never creates decisions."""

import copy
import json
from pathlib import Path

import pytest

from eval.human_review import apply_review, merge_blind


def sample():
    return [{'id':'fiction:review','sentence':'Fictional claim.','contexts':[{'text':'Fictional evidence.'}],
             'judge_supported':True,'confidence':0.9,'human_supported':None,'review_status':'todo'}]


def test_unlabelled_review_is_a_noop_and_human_boolean_preserves_model_fields():
    original = sample()
    blind = [{k:v for k,v in original[0].items() if k not in ('judge_supported','confidence')}]
    assert merge_blind(original,blind)==(original,0)
    blind[0].update(human_supported=False,review_status='reviewed',human_note='Fictional mismatch.')
    revised,changed = merge_blind(original,blind)
    assert changed==1 and revised[0]['human_supported'] is False
    assert revised[0]['judge_supported'] is True and revised[0]['confidence']==0.9
    assert revised[0]['contexts']==original[0]['contexts'] and original[0]['human_supported'] is None


@pytest.mark.parametrize('field,value',[
    ('sentence','Altered evidence.'),('human_supported','true'),('review_status','approved'),
    ('human_note',None),('id','fiction:wrong'),
])
def test_invalid_or_altered_review_is_rejected(field,value):
    original = sample()
    blind = copy.deepcopy(original)
    blind[0][field] = value
    with pytest.raises(ValueError):
        merge_blind(original,blind)


def test_duplicate_ids_are_rejected():
    with pytest.raises(ValueError,match='ids'):
        merge_blind(sample(),sample()*2)


def test_failed_replace_preserves_original_and_private_intermediates(tmp_path,monkeypatch):
    source,backup = tmp_path/'source.jsonl',tmp_path/'.cache'
    raw = (json.dumps(sample()[0])+'\n').encode()
    source.write_bytes(raw)
    def fail_replace(temporary,target):
        assert temporary.parent==backup and target==source
        raise OSError('Fictional filesystem failure')
    monkeypatch.setattr(Path,'replace',fail_replace)
    with pytest.raises(OSError):
        apply_review(source,raw,[{**sample()[0],'human_supported':True}],backup)
    assert source.read_bytes()==raw
    assert len(list(backup.glob('*.jsonl')))==1
    assert not list(backup.glob('*.pending'))


def test_import_refuses_a_source_changed_after_validation(tmp_path):
    source,backup = tmp_path/'source.jsonl',tmp_path/'.cache'
    source.write_bytes(b'Changed outside the importer')
    with pytest.raises(ValueError,match='source changed'):
        apply_review(source,b'Original reviewed evidence',sample(),backup)
    assert source.read_bytes()==b'Changed outside the importer'
