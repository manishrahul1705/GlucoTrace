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
from fastapi.responses import JSONResponse,Response
from pydantic import BaseModel,ConfigDict,Field
from .sources import Registry,SourceUnavailable
from .engine import Session,Store
from .scenarios import CATALOG,make_scenario
from .lab import exploration,export_session,library_item,LIBRARY_COLUMNS
from pydantic import field_validator


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Create(Input):
    source_id:str=Field(min_length=1,max_length=64)
    scenario:Literal['clean','steady','meal','activity','noisy','dropout15','dropout30','dropout60','dropout120']='clean'
    start:Literal['full','warm']='warm'
    seed:int=Field(default=1705,ge=0,le=2147483647,strict=True)
    duration_minutes:int=Field(default=720,ge=360,le=1440,multiple_of=5,strict=True)
class ScenarioConfiguration(BaseModel):
    scenario:str
    name:str
    description:str
    seed:int
    generator_version:str
    duration_minutes:int
    input_loss_minutes:int
    predictor:str
    provenance:str
    units:str
class Rename(Input):
    name:str=Field(min_length=1,max_length=80,pattern=r'^[^\x00-\x1f\x7f]+$')
    @field_validator('name')
    @classmethod
    def visible_name(cls,value):
        if not value.strip():
            raise ValueError('Enter a session name containing a visible character.')
        return value
class Recreate(Input):
    start:Literal['full','warm']='warm'
class Export(Input):
    generation:str
    kind:Literal['configuration','readings','forecasts','scores','summary']
    cutoff_minute:int|None=Field(default=None,ge=0,le=1440,strict=True)
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
    model_family:str='sensor_only'
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
    history_start:str
    history_end:str
    history_count:int
    artifact_identity:str
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
    pending:int
    missing_targets:int
    coverage_denominators:dict[str,int]
    interval_available:int
    mae:float|None
    mean_signed_error:float|None
    forecast_availability:float|None
    scoring_availability:float|None
    empirical_coverage:dict[str,float|None]
class GapView(BaseModel):
    start_time:str
    end_time:str
    label:str
class RecoveryView(BaseModel):
    required_cells:int=61
    required_minutes:int=60
    available_valid_cells:int=Field(ge=0,le=61)
    support_span_minutes:int=Field(ge=0,le=60)
    consecutive_valid_cells:int
    consecutive_valid_minutes:int
    is_suppressed:bool
    suppression_reason:str|None
    suppression_message:str
    next_issue_minute:int|None
    next_issue_time:str|None
    next_issue_eligible:bool=Field(description='Legacy history-only condition under uninterrupted inputs; not predictor readiness.')
    conditional_recovery_minute:int|None
    conditional_recovery_time:str|None
    conditional_recovery_label:str
class IntervalReadiness(BaseModel):
    alpha:str
    calibration_reason:str
    current_reason:str
    latest_reason:str
class VariantAvailability(BaseModel):
    variant:str
    capability_reason:str
    current_reason:str
    next_issue_reason:str
    latest_forecast_id:str|None
    latest_origin_time:str|None
    latest_point_reason:str
    intervals:list[IntervalReadiness]
class Snapshot(BaseModel):
    baseline_context:dict|None=None
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
    recovery:RecoveryView
    availability:list[VariantAvailability]
    configuration:ScenarioConfiguration|None
class Exploration(BaseModel):
    virtual_time:str
    history:list[ReadingView]
    forecasts:list[ForecastView]
class RetainedSummary(BaseModel):
    virtual_cutoff:str
    mode:str
    summaries:list[Summary]
class LibraryItem(BaseModel):
    id:str
    generation:str
    name:str
    created_at:str|None
    status:str
    mode:str
    configuration:ScenarioConfiguration|None
    recreatable:bool
    summary:RetainedSummary|None
class Library(BaseModel):
    sessions:list[LibraryItem]
class ScenarioDescription(BaseModel):
    id:str
    name:str
    description:str
class Catalog(BaseModel):
    scenarios:list[ScenarioDescription]
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
    def __init__(self,root,runtime,local_enabled=False,clock=time.monotonic,fusion_root=None):
        runtime.mkdir(parents=True,exist_ok=True)
        self.store=Store(runtime/'replay.sqlite3');self.registry=Registry(root,runtime,local_enabled,fusion_root)
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


def create_app(root=None,runtime=None,local_enabled=None,run_clock=True,fusion_root=None):
    root=Path(root or Path(__file__).resolve().parents[3])
    runtime=Path(runtime or root/'data/runtime/stage6')
    enabled=(os.getenv('GLUCOTWIN_LOCAL_REPLAY','0')=='1') if local_enabled is None else local_enabled
    manager=Manager(root,runtime,enabled,fusion_root=fusion_root)

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
            try:
                if request.source_id=='synthetic-dawn':source=make_scenario(request.scenario,request.seed,request.duration_minutes)
                else:
                    if request.seed!=1705 or request.duration_minutes!=720 or request.scenario not in ['clean','dropout15','dropout30','dropout60','dropout120']:
                        raise SourceUnavailable('PRIVATE_CONFIGURATION_FIXED')
                    source=manager.registry.load(request.source_id,request.scenario)
            except SourceUnavailable as exc:raise HTTPException(409,str(exc)+': select synthetic mode or restore the matching local Stage 5 artifacts') from None
            session=Session(source,manager.store,warm=request.start=='warm')
            manager.sessions[session.id]=session
            return session.snapshot()
    @app.get('/api/replay/scenarios',response_model=Catalog)
    def scenarios():return dict(scenarios=[dict(id=k,name=v[0],description=v[1]) for k,v in CATALOG.items()])
    @app.get('/api/replay/library',response_model=Library)
    def library(limit:int=Query(20,ge=1,le=50)):
        with manager.lock:
            rows=manager.store.db.execute(f'SELECT {LIBRARY_COLUMNS} FROM sessions ORDER BY rowid DESC LIMIT ?',(limit,)).fetchall()
            return dict(sessions=[library_item(manager.store,r,manager.sessions) for r in rows])
    def retained(id):
        row=manager.store.db.execute(f'SELECT {LIBRARY_COLUMNS} FROM sessions WHERE id=?',(id,)).fetchone()
        if row is None:raise HTTPException(404,'SESSION_NOT_FOUND')
        return library_item(manager.store,row,manager.sessions)
    @app.get('/api/replay/library/{id}',response_model=LibraryItem)
    def library_summary(id:str):
        with manager.lock:return retained(id)
    @app.post('/api/replay/library/{id}/rename',response_model=LibraryItem)
    def rename(id:str,request:Rename):
        with manager.lock:
            retained(id)
            manager.store.db.execute('UPDATE sessions SET display_name=? WHERE id=?',(request.name,id));manager.store.db.commit()
            return retained(id)
    @app.post('/api/replay/library/{id}/recreate',response_model=Snapshot)
    def recreate(id:str,request:Recreate):
        with manager.lock:
            item=retained(id)
            if not item['recreatable']:raise HTTPException(409,'RECREATION_UNAVAILABLE: select a new source; legacy/private runtime is not resumed')
            config=item['configuration']
            return create(Create(source_id='synthetic-dawn',scenario=config['scenario'],seed=config['seed'],duration_minutes=config['duration_minutes'],start=request.start))
    @app.get('/api/replay/sessions/{id}/explore',response_model=Exploration)
    def explore(id:str,end_minute:int=Query(ge=0),window:int=Query(180)):
        with manager.lock:
            try:return exploration(manager.get(id),end_minute,window)
            except ValueError as exc:raise HTTPException(422,str(exc)) from None
    @app.post('/api/replay/sessions/{id}/export')
    def export(id:str,request:Export):
        with manager.lock:
            s=manager.get(id)
            if s.generation!=request.generation:raise HTTPException(409,'STALE_GENERATION')
            try:content,mime=export_session(s,request.kind,s.minute if request.cutoff_minute is None else request.cutoff_minute,retained(id)['name'])
            except PermissionError as exc:raise HTTPException(403,str(exc)) from None
            except ValueError as exc:raise HTTPException(422,str(exc)) from None
            if len(content.encode('utf-8'))>2_000_000:raise HTTPException(413,'EXPORT_SIZE_LIMIT')
            extension='json' if mime=='application/json' else 'csv'
            return Response(content,media_type=mime,headers={'Content-Disposition':f'attachment; filename="glucotwin-synthetic-{request.kind}.{extension}"','X-Content-Type-Options':'nosniff'})
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
