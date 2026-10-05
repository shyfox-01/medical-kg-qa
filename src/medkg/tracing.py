import contextvars
import json
import time
import uuid
from contextlib import contextmanager

from medkg.config import ROOT

CURRENT = contextvars.ContextVar('trace_id',default='')


@contextmanager
def request_trace():
    trace_id = uuid.uuid4().hex
    token = CURRENT.set(trace_id)
    try:
        yield trace_id
    finally:
        CURRENT.reset(token)


@contextmanager
def span(name: str, **attributes):
    start,status = time.perf_counter(),'ok'
    try:
        yield attributes
    except Exception:
        status = 'error'
        raise
    finally:
        directory = ROOT/'runs/traces'
        directory.mkdir(parents=True,exist_ok=True)
        with (directory/(time.strftime('%Y-%m-%d')+'.jsonl')).open('a',encoding='utf8') as stream:
            stream.write(json.dumps({'trace_id':CURRENT.get(),'span':name,'status':status,
                'seconds':time.perf_counter()-start,'attributes':attributes})+'\n')
