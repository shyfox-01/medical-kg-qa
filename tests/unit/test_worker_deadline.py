"""Public worker deadline and deterministic process cleanup."""

import pytest

from eval.client import JSONProcess


def test_worker_deadline_closes_its_process():
    worker = JSONProcess(['-c','import sys,time; sys.stdin.readline(); time.sleep(0.2)'],timeout=0.02)
    with pytest.raises(TimeoutError,match='deadline'):
        worker.request({'fictional':True})
    assert worker.process.poll() is not None
    worker.close()
