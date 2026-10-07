"""Real process contention and abrupt-exit recovery without provider calls."""

import os
import subprocess
import sys
import time

import pytest

from medkg.llm import ledger_lock


def test_mutex_releases_after_body_exception(tmp_path):
    path = tmp_path/'exception.lock'
    with pytest.raises(ValueError):
        with ledger_lock(path):
            raise ValueError('fictional failure')
    with ledger_lock(path,timeout=0.1):
        pass
    assert not path.exists() and path.with_name(path.name+'.oslock').exists()


def test_legacy_lock_requires_owner_inspection_without_deletion(tmp_path):
    path = tmp_path/'legacy.lock'
    path.write_text('fictional existing owner',encoding='utf8')
    with pytest.raises(RuntimeError,match='Legacy usage lock'):
        with ledger_lock(path,timeout=0.05):
            pytest.fail('Legacy lock must not be bypassed')
    assert path.read_text(encoding='utf8')=='fictional existing owner'


def test_abrupt_owned_process_exit_releases_native_mutex(tmp_path):
    path,ready = tmp_path/'owned.lock',tmp_path/'owner.ready'
    code = ('import sys,time; from pathlib import Path; from medkg.llm import ledger_lock; '
            '\nwith ledger_lock(Path(sys.argv[1])):'
            '\n Path(sys.argv[2]).write_text("owned",encoding="utf8")'
            '\n time.sleep(30)')
    owner = subprocess.Popen([sys.executable,'-c',code,str(path),str(ready)],
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    def terminate_owned_tree():
        if owner.poll() is None:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(owner.pid),'/T','/F'],check=True,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                owner.terminate()
            owner.wait(timeout=5)
    try:
        deadline = time.monotonic()+5
        while not ready.exists() and owner.poll() is None and time.monotonic()<deadline:
            time.sleep(0.02)
        assert ready.exists(), 'Owned mutex probe failed to start'
        with pytest.raises(RuntimeError,match='bounded lock timeout'):
            with ledger_lock(path,timeout=0.1):
                pytest.fail('Live owner must exclude a competitor')
        terminate_owned_tree()
        with ledger_lock(path,timeout=3):
            pass
        assert owner.poll() is not None
    finally:
        terminate_owned_tree()
        owner.stderr.close()
