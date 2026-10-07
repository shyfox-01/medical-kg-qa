"""Fault injection at publication boundaries; fictional assertions only."""

import json

import pytest

from medkg.ingest.publication import publish_assertions


class Store:
    def __init__(self,fail=False):
        self.fail,self.calls = fail,0
    def reconcile_extracted(self,*args):
        self.calls += 1
        if self.fail:
            raise RuntimeError('Injected database failure')


def test_publication_resumes_database_failure_and_detects_completed_drift(tmp_path):
    target = tmp_path/'edges.jsonl'
    target.write_text('',encoding='utf8')
    work = tmp_path/'journal'
    edge = {'a':'fiction:a','b':'fiction:b','type':'INTERACTS_WITH',
            'source':'openfda_extracted','evidence':['fiction:chunk']}
    with pytest.raises(RuntimeError,match='Injected'):
        publish_assertions(Store(True),{'fiction:chunk'},[edge],target,work)
    assert target.read_text()==''
    store = Store()
    state = publish_assertions(store,{'fiction:chunk'},[edge],target,work)
    assert state['phase']=='complete' and json.loads(target.read_text())==edge
    publish_assertions(store,{'fiction:chunk'},[edge],target,work)
    assert store.calls==2
    target.write_text('{}\n',encoding='utf8')
    with pytest.raises(RuntimeError,match='drifted'):
        publish_assertions(store,{'fiction:chunk'},[edge],target,work)


def test_publication_resumes_file_failure_after_database_commit(tmp_path,monkeypatch):
    target = tmp_path/'edges.jsonl'
    target.write_text('',encoding='utf8')
    store = Store()
    original = type(target).replace
    def replace(path,destination):
        if destination==target:
            raise OSError('Injected file failure')
        return original(path,destination)
    monkeypatch.setattr(type(target),'replace',replace)
    with pytest.raises(OSError,match='Injected'):
        publish_assertions(store,{'fiction:chunk'},[],target,tmp_path/'journal')
    manifest = next((tmp_path/'journal').glob('*/manifest.json'))
    assert json.loads(manifest.read_text())['phase']=='graph_applied'
    monkeypatch.setattr(type(target),'replace',original)
    assert publish_assertions(store,{'fiction:chunk'},[],target,tmp_path/'journal')['phase']=='complete'
    assert store.calls==2


def test_completed_sample_refresh_preserves_later_outside_publication(tmp_path):
    target,work = tmp_path/'edges.jsonl',tmp_path/'journal'
    store = Store()
    edge = {'a':'fiction:a','b':'fiction:b','type':'INTERACTS_WITH',
            'source':'openfda_extracted','evidence':['fiction:first']}
    outside = {**edge,'b':'fiction:c','evidence':['fiction:outside']}
    publish_assertions(store,{'fiction:first'},[edge],target,work)
    publish_assertions(store,{'fiction:outside'},[outside],target,work)
    assert publish_assertions(store,{'fiction:first'},[edge],target,work)['phase']=='complete'
    exported = [json.loads(line) for line in target.read_text().splitlines()]
    assert {row['b'] for row in exported}=={'fiction:b','fiction:c'}
    generations = len(list(work.glob('*/manifest.json')))
    publish_assertions(store,{'fiction:first'},[edge],target,work)
    assert len(list(work.glob('*/manifest.json')))==generations


def test_incomplete_publication_refuses_concurrent_export_change(tmp_path):
    target,work = tmp_path/'edges.jsonl',tmp_path/'journal'
    target.write_text('',encoding='utf8')
    with pytest.raises(RuntimeError,match='Injected'):
        publish_assertions(Store(True),{'fiction:first'},[],target,work)
    outside = {'a':'fiction:a','b':'fiction:b','type':'INTERACTS_WITH',
               'source':'openfda_extracted','evidence':['fiction:outside']}
    target.write_text(json.dumps(outside)+'\n',encoding='utf8')
    with pytest.raises(RuntimeError,match='changed during incomplete'):
        publish_assertions(Store(),{'fiction:first'},[],target,work)
    assert json.loads(target.read_text())==outside


def test_publication_checks_original_backup_integrity(tmp_path):
    target,work = tmp_path/'edges.jsonl',tmp_path/'journal'
    target.write_text('',encoding='utf8')
    publish_assertions(Store(),{'fiction:first'},[],target,work)
    next(work.glob('*/before.jsonl')).write_text('changed',encoding='utf8')
    with pytest.raises(RuntimeError,match='integrity'):
        publish_assertions(Store(),{'fiction:first'},[],target,work)
