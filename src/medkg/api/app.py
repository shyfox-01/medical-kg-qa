"""Local FastAPI boundary with explicit conversation state and verified SSE output."""

import inspect
import json
import queue
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from medkg.config import ROOT, Settings
from medkg.qa.pipeline import local_pipeline

STATIC = Path(__file__).parent / 'static'
STARMAP = ROOT / 'data/processed/starmap.json.gz'


class StarMap:
    """The star map built by scripts.build_starmap (D128): its gzipped payload for the page and
    the point of each uid, so progress events can say where on the map an entity is."""

    def __init__(self, path: Path = STARMAP):
        self.payload, self.points = None, {}
        uids = path.with_name('starmap_uids.json')
        if path.exists() and uids.exists():
            self.payload = path.read_bytes()
            self.points = {uid: i for i, uid in enumerate(json.loads(uids.read_text(encoding='utf8')))}

    def event(self, data: dict) -> dict:
        """The event with each entity's point added (None when it is not on the map)."""
        out = dict(data)
        for key in ('sources', 'expected'):
            if key in out:
                out[key] = [{'uid': uid, 'i': self.points.get(uid)} for uid in out[key]]
        for key in ('entities', 'results'):
            if key in out:
                out[key] = [{**entity, 'i': self.points.get(entity.get('uid'))} for entity in out[key]]
        return out


class HistoryTurn(BaseModel):
    model_config = ConfigDict(extra='ignore')
    question: str = Field(default='',max_length=4096)
    focus: list[Annotated[str,StringConstraints(max_length=256)]] = Field(default_factory=list,max_length=2)
    intent: str | None = Field(default=None,max_length=100)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    question: str = Field(min_length=1,max_length=4096)
    history: list[HistoryTurn] = Field(default_factory=list,max_length=4)


def create_app(pipeline=None) -> FastAPI:
    lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        if app.state.pipeline is None:
            try:
                app.state.pipeline = local_pipeline()
            except Exception as exc:
                app.state.initialization_error = type(exc).__name__
        yield
        if app.state.pipeline is not None:
            app.state.pipeline.close()

    application = FastAPI(title='English Medical GraphRAG',version='0.1.0',lifespan=lifespan)
    application.state.pipeline = pipeline
    application.state.starmap = StarMap()

    def ask(request: AskRequest, events=None) -> dict:
        if application.state.pipeline is None:
            raise HTTPException(503,'Service configuration is incomplete')
        history = [turn.model_dump() for turn in request.history]
        pipeline = application.state.pipeline
        with lock:
            # A pipeline without progress events (an older or a test one) is asked as before.
            if events is None or 'events' not in inspect.signature(pipeline.ask).parameters:
                return pipeline.ask(request.question,history)
            return pipeline.ask(request.question,history,events=events)

    @application.get('/')
    def index():
        return FileResponse(STATIC / 'index.html',media_type='text/html')

    @application.get('/static/starmap.js')
    def starmap_script():
        # Revalidated on every load, so a changed script is never run from an old cache.
        return FileResponse(STATIC / 'starmap.js',media_type='text/javascript',headers={'Cache-Control':'no-cache'})

    @application.get('/starmap')
    def starmap():
        # Gzipped once when built; every browser accepts it as is.
        if application.state.starmap.payload is None:
            raise HTTPException(404,'The star map is not built (python -m scripts.build_starmap)')
        return Response(application.state.starmap.payload,media_type='application/json',
                        headers={'Content-Encoding':'gzip','Cache-Control':'max-age=3600'})

    @application.get('/health')
    def health():
        return {'status':'alive','medical_advice':False}

    @application.get('/ready')
    def ready():
        settings = application.state.pipeline.settings if application.state.pipeline else Settings()
        configured = bool(settings.llm_api_key and settings.llm_model and settings.llm_base_url)
        connected = False
        if application.state.pipeline:
            try:
                application.state.pipeline.store.verify()
                connected = True
            except Exception:
                pass
        ok = configured and connected
        return JSONResponse({'status':'ready' if ok else 'not_ready','neo4j':connected,
                             'llm_configured':configured},status_code=200 if ok else 503)

    @application.post('/ask')
    def ask_endpoint(request: AskRequest):
        return ask(request)

    @application.post('/ask/stream')
    def stream_endpoint(request: AskRequest):
        if application.state.pipeline is None:
            raise HTTPException(503,'Service configuration is incomplete')
        # The question is answered on a worker thread; its progress events (D128) are sent as
        # they happen, then the answer and the full result as before.
        updates = queue.Queue()
        def work():
            try:
                updates.put(('result',ask(request,lambda kind,data: updates.put((kind,data)))))
            except Exception as exc:
                updates.put(('error',{'error_type':type(exc).__name__}))
            finally:
                updates.put(None)
        threading.Thread(target=work,daemon=True).start()
        def events():
            yield 'event: status\ndata: '+json.dumps({'stage':'processing'})+'\n\n'
            while (update := updates.get()) is not None:
                kind,data = update
                if kind!='result':
                    if kind!='error':
                        data = application.state.starmap.event(data)
                    yield f'event: {kind}\ndata: '+json.dumps(data)+'\n\n'
                    continue
                for start in range(0,len(data['answer']),160):
                    yield 'event: answer\ndata: '+json.dumps({'trace_id':data['trace_id'],
                        'text':data['answer'][start:start+160]})+'\n\n'
                yield 'event: result\ndata: '+json.dumps(data)+'\n\n'
        return StreamingResponse(events(),media_type='text/event-stream',
                                 headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    return application


app = create_app()
