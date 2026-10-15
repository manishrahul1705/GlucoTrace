"""Loopback-only development API with explicit schemas and one clock task."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import os
import threading
import time
from typing import Literal
from uuid import uuid4
from fastapi import FastAPI,HTTPException,Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field
from .sources import Registry,SourceUnavailable
from .engine import Session,Store


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Create(Input):
    source_id:str=Field(min_length=1,max_length=64)
    scenario:Literal['clean','dropout15','dropout30','dropout60','dropout120']='clean'
    start:Literal['full','warm']='warm'
class Control(Input):
    generation:str
    request_id:str=Field(min_length=1,max_length=80)
    action:Literal['start','pause','step','speed']
    speed:Literal[1,60,300]|None=None
class Reset(Input):
    generation:str
    request_id:str=Field(min_length=1,max_length=80)
class Interval(BaseModel):
    alpha:str
    lower:float|None
    upper:float|None
    reason:str
class MaturedScore(BaseModel):
    observed:float|None
    signed_error:float|None
    reason:str
    matured_time:str
    coverage:dict[str,bool|None]
class ForecastView(BaseModel):
    id:str
    seq:int
    variant:str
    phase:str
    origin_time:str
    target_time:str
    value:float|None
    point_reason:str
    intervals:list[Interval]
    score:MaturedScore|None
class ReadingView(BaseModel):
    id:str
    measurement_time:str
    assumed_arrival_time:str
    value:float|None
class LatestReading(BaseModel):
    value:float
    measurement_time:str
    age_minutes:float
class Summary(BaseModel):
    variant:str
    scheduled:int
    issued:int
    matured:int
    scored:int
    interval_available:int
    mae:float|None
    empirical_coverage:dict[str,float|None]
class GapView(BaseModel):
    start_time:str
    end_time:str
    label:str
class Snapshot(BaseModel):
    session_id:str
    generation:str
    sequence:int
    source_id:str
    mode:Literal['synthetic','local']
    provenance:str
    source_timezone:str
    session_epoch:str
    arrival_assumption:str
    virtual_time:str
    elapsed_minutes:float
    end_minutes:int
    status:str
    speed:int
    phase:str
    phase_counts:dict[str,int]
    artifacts_frozen:bool
    artifact_reason:str
    warm_start:bool
    history:list[ReadingView]
    latest_reading:LatestReading|None
    forecasts:list[ForecastView]
    next_after_seq:int|None
    has_more:bool
    summaries:list[Summary]
    disclosure:str
    forecast_count:int
    arrival_reason:str
    gap:GapView|None
class SourceView(BaseModel):
    id:str
    mode:str
    label:str
    available:bool
    reason:str|None
    disclosure:str
class SourcesView(BaseModel):
    sources:list[SourceView]
    scenarios:list[str]
class Health(BaseModel):
    status:str
    local_replay_enabled:bool
    persistence:str
class Deleted(BaseModel):
    status:str


class Manager:
    def __init__(self,root,runtime,local_enabled=False,clock=time.monotonic):
        runtime.mkdir(parents=True,exist_ok=True)
        self.store=Store(runtime/'replay.sqlite3');self.registry=Registry(root,runtime,local_enabled)
        self.sessions={};self.lock=threading.RLock();self.requests={};self.clock=clock;self.last_wall=clock()

    def get(self,id):
        if id in self.sessions:return self.sessions[id]
        if self.store.exists(id):raise HTTPException(410,'SESSION_EXPIRED: create a new replay; persisted events are retained locally')
        raise HTTPException(404,'SESSION_NOT_FOUND')

    def advance_wall(self):
        with self.lock:
            now=self.clock();elapsed=max(0,now-self.last_wall);self.last_wall=now
            for session in self.sessions.values():
                session.tick(elapsed)

    def command(self,id,request,reset=False):
        with self.lock:
            session=self.get(id)
            cache_key=(id,request.request_id)
            fingerprint=request.model_dump_json()+str(reset)
            if cache_key in self.requests:
                previous,result=self.requests[cache_key]
                if previous!=fingerprint:raise HTTPException(409,'REQUEST_ID_REUSED')
                if result['generation']!=session.generation:raise HTTPException(409,'STALE_GENERATION')
                return result
            if session.generation!=request.generation:raise HTTPException(409,'STALE_GENERATION')
            if reset:
                session=Session(session.source,self.store,id=id,warm=session.warm);self.sessions[id]=session
            elif request.action=='start':session.status='running' if session.minute<session.end else 'ended'
            elif request.action=='pause':session.status='paused' if session.minute<session.end else 'ended'
            elif request.action=='step':
                try:session.step()
                except ValueError as exc:raise HTTPException(409,str(exc)) from None
            elif request.action=='speed':
                if request.speed is None:raise HTTPException(422,'SPEED_REQUIRED')
                session.speed=request.speed
            self.last_wall=self.clock() # re-anchor controls; snapshots never drive clock
            session.seq+=1;self.store.metadata(session)
            result=session.snapshot()
            self.requests[cache_key]=(fingerprint,result)
            if len(self.requests)>2000:self.requests.pop(next(iter(self.requests)))
            return result


def create_app(root=None,runtime=None,local_enabled=None,run_clock=True):
    root=Path(root or Path(__file__).resolve().parents[3])
    runtime=Path(runtime or root/'data/runtime/stage6')
    enabled=(os.getenv('GLUCOTWIN_LOCAL_REPLAY','0')=='1') if local_enabled is None else local_enabled
    manager=Manager(root,runtime,enabled)

    @asynccontextmanager
    async def lifespan(app):
        async def clock_loop():
            while True:
                await asyncio.sleep(.1)
                await asyncio.to_thread(manager.advance_wall)
        task=asyncio.create_task(clock_loop()) if run_clock else None
        try:yield
        finally:
            if task:
                task.cancel()
                try:await task
                except asyncio.CancelledError:pass
            manager.store.db.close()

    app=FastAPI(title='GlucoTwin local research replay',lifespan=lifespan)
    app.state.manager=manager
    origins=os.getenv('GLUCOTWIN_FRONTEND_ORIGINS','http://127.0.0.1:15173,http://localhost:15173').split(',')
    if any(o not in ['http://127.0.0.1:15173','http://localhost:15173'] for o in origins):
        raise ValueError('Only configured local frontend origins are supported')
    app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=['GET','POST','DELETE'],allow_headers=['Content-Type'])

    @app.exception_handler(Exception)
    async def sanitized_error(request,exc):
        return JSONResponse(status_code=500,content={'detail':'REPLAY_ERROR: session unavailable; create a new session or inspect local diagnostics'})

    @app.get('/api/health',response_model=Health)
    def health():return dict(status='ok',local_replay_enabled=enabled,persistence='events retained; sessions expire on server restart')
    @app.get('/api/replay/sources',response_model=SourcesView)
    def sources():
        with manager.lock:return manager.registry.list()
    @app.post('/api/replay/sessions',response_model=Snapshot)
    def create(request:Create):
        with manager.lock:
            if len(manager.sessions)>=12:raise HTTPException(409,'SESSION_LIMIT: close an existing session')
            try:source=manager.registry.load(request.source_id,request.scenario)
            except SourceUnavailable as exc:raise HTTPException(409,str(exc)+': select synthetic mode or restore the matching local Stage 5 artifacts') from None
            session=Session(source,manager.store,warm=request.start=='warm')
            manager.sessions[session.id]=session
            return session.snapshot()
    @app.post('/api/replay/sessions/{id}/control',response_model=Snapshot)
    def control(id:str,request:Control):return manager.command(id,request)
    @app.get('/api/replay/sessions/{id}/snapshot',response_model=Snapshot)
    def snapshot(id:str,limit:int=Query(30,ge=1,le=100),after_seq:int|None=Query(None,ge=0)):
        with manager.lock:return manager.get(id).snapshot(limit,after_seq)
    @app.post('/api/replay/sessions/{id}/reset',response_model=Snapshot)
    def reset(id:str,request:Reset):return manager.command(id,request,reset=True)
    @app.delete('/api/replay/sessions/{id}',response_model=Deleted)
    def delete(id:str):
        with manager.lock:
            manager.get(id);manager.store.expire(id);manager.sessions.pop(id)
            return dict(status='expired; immutable events retained locally')
    return app
