"""Local FastAPI boundary with explicit conversation state and verified SSE output."""

import json
import threading
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from medkg.config import Settings
from medkg.qa.pipeline import local_pipeline


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

    def ask(request: AskRequest) -> dict:
        if application.state.pipeline is None:
            raise HTTPException(503,'Service configuration is incomplete')
        with lock:
            return application.state.pipeline.ask(request.question,
                [turn.model_dump() for turn in request.history])

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
        def events():
            yield 'event: status\ndata: '+json.dumps({'stage':'processing'})+'\n\n'
            result = ask(request)
            for start in range(0,len(result['answer']),160):
                yield 'event: answer\ndata: '+json.dumps({'trace_id':result['trace_id'],
                    'text':result['answer'][start:start+160]})+'\n\n'
            yield 'event: result\ndata: '+json.dumps(result)+'\n\n'
        return StreamingResponse(events(),media_type='text/event-stream',
                                 headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    return application


app = create_app()
