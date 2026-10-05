"""OpenTelemetry SDK spans; local metadata-only JSONL or configured OTLP HTTP."""

import contextvars
import json
import os
import threading
import time
from contextlib import contextmanager

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Status, StatusCode

from medkg.config import ROOT

_PROVIDER = None
_PROVIDER_LOCK = threading.Lock()
_ROOT_SPAN = contextvars.ContextVar('request_span',default=None)


class JSONLSpanExporter(SpanExporter):
    def __init__(self):
        self.lock = threading.Lock()

    def export(self, spans):
        directory = ROOT/'runs/traces'
        directory.mkdir(parents=True,exist_ok=True)
        # One file per process avoids inter-process append races.
        file = directory/(time.strftime('%Y-%m-%d')+f'-{os.getpid()}.jsonl')
        with self.lock, file.open('a',encoding='utf8') as stream:
            for item in spans:
                record = {
                    'schema_version':1,'trace_id':format(item.context.trace_id,'032x'),
                    'span_id':format(item.context.span_id,'016x'),
                    'parent_span_id':format(item.parent.span_id,'016x') if item.parent else None,
                    'name':item.name,'start_ns':item.start_time,'end_ns':item.end_time,
                    'seconds':(item.end_time-item.start_time)/1e9,
                    'status':item.status.status_code.name,
                    'attributes':dict(item.attributes or {}),
                    'service_name':item.resource.attributes.get('service.name'),
                }
                stream.write(json.dumps(record)+'\n')
        return SpanExportResult.SUCCESS

    def shutdown(self):
        return None


def provider():
    global _PROVIDER
    if _PROVIDER is None:
        with _PROVIDER_LOCK:
            if _PROVIDER is None:
                result = TracerProvider(resource=Resource.create({
                    'service.name':os.getenv('OTEL_SERVICE_NAME','medical-kg-qa'),
                    'openinference.project.name':os.getenv('PHOENIX_PROJECT_NAME','medical-kg-qa')}))
                endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT','').strip()
                if endpoint:
                    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                        OTLPSpanExporter,
                    )
                    endpoint = endpoint.rstrip('/')
                    if not endpoint.endswith('/v1/traces'):
                        endpoint += '/v1/traces'
                    exporter = OTLPSpanExporter(endpoint=endpoint,timeout=5)
                    result.add_span_processor(BatchSpanProcessor(exporter,
                        max_queue_size=512,schedule_delay_millis=1000,export_timeout_millis=5000))
                else:
                    result.add_span_processor(SimpleSpanProcessor(JSONLSpanExporter()))
                _PROVIDER = result
    return _PROVIDER


@contextmanager
def request_trace():
    tracer = provider().get_tracer('medkg.qa')
    with tracer.start_as_current_span('ask',record_exception=False,
                                     set_status_on_exception=False) as root:
        token = _ROOT_SPAN.set(root)
        try:
            yield format(root.get_span_context().trace_id,'032x')
        except Exception as exc:
            root.set_status(Status(StatusCode.ERROR,type(exc).__name__))
            raise
        finally:
            _ROOT_SPAN.reset(token)


@contextmanager
def span(name: str, **attributes):
    tracer = provider().get_tracer('medkg.qa')
    with tracer.start_as_current_span(name,record_exception=False,
                                     set_status_on_exception=False) as current:
        start = time.perf_counter()
        try:
            yield attributes
        except Exception as exc:
            attributes['error_type'] = type(exc).__name__
            current.set_status(Status(StatusCode.ERROR,type(exc).__name__))
            raise
        finally:
            attributes['latency_s'] = time.perf_counter()-start
            current.set_attributes(attributes)
            if name=='request.result' and _ROOT_SPAN.get() is not None:
                root = _ROOT_SPAN.get()
                root.set_attributes(attributes)
                if attributes.get('failure_stage'):
                    root.set_status(Status(StatusCode.ERROR,attributes.get('error_type','request_failure')))
