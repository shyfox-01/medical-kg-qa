"""Repeated comparisons reuse genuine records and reject mixed source versions."""

import json

import pytest

from eval import improvement_balanced as experiment


def setup_records(tmp_path,monkeypatch,mismatch=False):
    monkeypatch.setattr(experiment,'ROOT',tmp_path)
    directory = tmp_path/'eval/runs'
    directory.mkdir(parents=True)
    metadata = {'evaluator_version':'fictional','dataset_sha256':'fixture','vocabulary_sha256':'fixture',
        'code_sha256':'same','system':'hybrid','phase':3,'system_source':'src','split':'test',
        'total_available':240,'cache_enabled':False,'judge_status':'uncalibrated','clinical_validation':False}
    (directory/'improvement_full_after_summary.json').write_text(json.dumps(metadata))
    (directory/'improvement_repeat_after_summary.json').write_text(json.dumps({**metadata,
        'code_sha256':'different' if mismatch else 'same'}))
    cases = [{'id':f'fiction:{i}','category':'single_hop'} for i in range(70)]
    for prefix,rounds in [('full',1),('repeat',2)]:
        for index in range(1,rounds+1):
            rows = [{**case,'score':{'passed':prefix=='repeat','quality_passed':prefix=='repeat','refused':False},
                     'failure_stage':None,'execution_exact':None,'latency_s':0.01,'usage':{}}
                    for case in cases]
            (directory/f'improvement_{prefix}_after_round{index}.jsonl').write_text(
                ''.join(json.dumps(r)+'\n' for r in rows))
    return directory,cases


def test_combined_rates_preserve_the_first_real_round(tmp_path,monkeypatch):
    directory,cases = setup_records(tmp_path,monkeypatch)
    original = (directory/'improvement_full_after_round1.jsonl').read_bytes()
    experiment.combine('after',cases)
    result = json.loads((directory/'improvement_balanced_after_summary.json').read_text())
    assert result['pass_rate_rounds']==[0,1,1]
    assert result['pass_rate_mean']==pytest.approx(2/3)
    assert result['rounds']==3 and result['evaluated_questions']==70
    assert (directory/'improvement_full_after_round1.jsonl').read_bytes()==original


def test_combination_rejects_different_measured_code(tmp_path,monkeypatch):
    directory,cases = setup_records(tmp_path,monkeypatch,mismatch=True)
    with pytest.raises(RuntimeError,match='different frozen inputs'):
        experiment.combine('after',cases)
    assert not (directory/'improvement_balanced_after_summary.json').exists()
