"""Deterministic minute-event engine, immutable forecast/score ledger and SQLite."""
from collections import deque
from dataclasses import dataclass,asdict
from pathlib import Path
import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime,timezone
from glucotwin.stage5.core import Calibration,fit_offset,calibrate
from .sources import Reading,Source
from .prediction import PredictRequest,Predictor,timestamp


@dataclass(frozen=True)
class Forecast:
    id: str
    seq: int
    origin: int
    target: int
    variant: str
    phase: str
    value: float | None
    reason: str
    intervals: tuple
    history_count: int = 0
    artifact_identity: str = 'legacy-unrecorded'


@dataclass(frozen=True)
class Score:
    forecast_id: str
    matured: int
    observed: float | None
    signed_error: float | None
    reason: str
    coverage: tuple


class Store:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,check_same_thread=False)
        exists=self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone()
        if exists and 'configuration' not in {r[1] for r in self.db.execute('PRAGMA table_info(sessions)')}:
            backup=Path(str(path)+'.before-library-v0.sqlite3')
            if backup.exists():backup=Path(str(path)+'.before-library-'+uuid.uuid4().hex+'.sqlite3')
            destination=sqlite3.connect(backup)
            try:self.db.backup(destination)
            finally:destination.close()
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,generation TEXT,metadata TEXT,expired INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS events(session TEXT,generation TEXT,id TEXT,kind TEXT,payload TEXT,
          PRIMARY KEY(session,generation,id,kind));
        ''')
        columns={r[1] for r in self.db.execute('PRAGMA table_info(sessions)')}
        for name,kind in [('display_name','TEXT'),('created_at','TEXT'),('configuration','TEXT'),('summary','TEXT')]:
            if name not in columns:self.db.execute(f'ALTER TABLE sessions ADD COLUMN {name} {kind}')
        self.db.execute('PRAGMA user_version=1')
        # Recovery is deliberately not implemented. Preserve evidence, expire sessions.
        self.db.execute('UPDATE sessions SET expired=1');self.db.commit()

    def metadata(self,session):
        payload=json.dumps(dict(source_id=session.source.id,mode=session.source.mode,minute=session.minute,status=session.status))
        config=json.dumps(session.source.configuration) if session.source.configuration else None
        summary=json.dumps(dict(virtual_cutoff=timestamp(session.minute),summaries=session.summaries(),mode=session.source.mode),allow_nan=False)
        self.db.execute('INSERT INTO sessions(id,generation,metadata,expired,display_name,created_at,configuration,summary) VALUES(?,?,?,0,?,?,?,?) ON CONFLICT(id) DO UPDATE SET generation=excluded.generation,metadata=excluded.metadata,expired=0,configuration=excluded.configuration,summary=excluded.summary',
                        (session.id,session.generation,payload,'Untitled replay',datetime.now(timezone.utc).isoformat(),config,summary));self.db.commit()

    def event(self,session,kind,id,payload):
        self.db.execute('INSERT INTO events VALUES(?,?,?,?,?)',(session.id,session.generation,id,kind,json.dumps(payload,allow_nan=False)))

    def expire(self,id):
        self.db.execute('UPDATE sessions SET expired=1 WHERE id=?',(id,));self.db.commit()

    def exists(self,id):return self.db.execute('SELECT 1 FROM sessions WHERE id=?',(id,)).fetchone() is not None


class History:
    def __init__(self):
        self.by_time={};self.ids={};self.payloads={};self.conflicts=set();self.recent=deque(maxlen=181)

    def accept(self,reading):
        raw_value=repr(reading.value) if reading.value is not None and not math.isfinite(reading.value) else reading.value
        payload=(reading.minute,raw_value,reading.valid,reading.unit)
        if reading.id in self.ids:
            if self.ids[reading.id]==payload:return 'IDEMPOTENT'
            for minute in {reading.minute,self.ids[reading.id][0]}:
                self.conflicts.add(minute)
                self.by_time[minute]=Reading('conflict',minute,None,False)
            return 'CONFLICTING_DUPLICATE'
        self.ids[reading.id]=payload
        if reading.minute in self.payloads:
            if self.payloads[reading.minute]==payload:return 'EQUIVALENT_DUPLICATE'
            self.conflicts.add(reading.minute)
            self.by_time[reading.minute]=Reading('conflict',reading.minute,None,False)
            return 'CONFLICTING_DUPLICATE'
        self.payloads[reading.minute]=payload
        if reading.value is not None and (not math.isfinite(reading.value) or not 40<=reading.value<=400):
            reading=Reading(reading.id,reading.minute,None,False,reading.unit)
        if reading.unit!='mg/dL':
            reading=Reading(reading.id,reading.minute,reading.value,False,reading.unit)
        self.by_time[reading.minute]=reading
        self.recent.append(reading.minute)
        return 'ACCEPTED'

    def request(self,origin):
        # Keep the last earlier valid cell only for staleness metadata, never as a fill.
        start=max(0,origin-60)
        keys=[k for k in self.by_time if start<=k<=origin]
        past=[k for k,r in self.by_time.items() if k<start and r.valid]
        if past:keys.insert(0,max(past))
        return tuple(self.by_time[k] for k in sorted(set(keys)))


class Evaluator:
    def __init__(self,reference):self._reference=reference
    def mature(self,forecast,now):
        if now<forecast.target:raise ValueError('Premature score request')
        target=self._reference.get(forecast.target)
        if target is None or not math.isfinite(target):return Score(forecast.id,now,None,None,'TARGET_MISSING',())
        if forecast.value is None:return Score(forecast.id,now,target,None,forecast.reason,())
        coverage=tuple((a,lo<=target<=hi if reason=='OK' else None) for a,lo,hi,reason in forecast.intervals)
        return Score(forecast.id,now,target,target is not None and forecast.value-target,'OK',coverage)


class Session:
    def __init__(self,source:Source,store=None,id=None,warm=False):
        self.id=id or str(uuid.uuid4());self.generation=str(uuid.uuid4());self.source=source;self.store=store
        self.predictor=Predictor(source.predictor);self.evaluator=Evaluator(source.reference)
        self.history=History();self.minute=-1;self.virtual_seconds=0.;self.seq=0;self.status='paused';self.speed=60
        self.offset=None;self.offset_reason='INSUFFICIENT_OFFSET_DATA';self.offset_pairs=[];self.calibration_pairs=[]
        self.offset_invalid=0;self.calibration_invalid=0
        self.quantiles={};self.frozen=False;self.artifact_reason=source.artifact_reason
        self.forecasts=[];self.scores={};self.pending={};self.phase='synthetic' if source.mode=='synthetic' else 'offset'
        self.warm=warm;self.last_arrival_reason='OK';self.arrivals={}
        for reading in source.readings:self.arrivals.setdefault(reading.minute,[]).append(reading)
        self.end=max(self.arrivals)
        self.advance_to(0)
        if warm:self.advance_to(120 if source.mode=='synthetic' else math.ceil((source.anchor+48*60+60)/5)*5)
        if self.store:self.store.metadata(self)

    def support_phase(self,origin):
        if self.source.mode=='synthetic':return 'synthetic'
        start,target=origin-60,origin+30;a=self.source.anchor
        if start>=a and target<a+1440:return 'offset'
        if start>=a+1440 and target<a+2880:return 'calibration'
        if start>=a+2880:return 'evaluation'
        return 'purged'

    def transition(self,minute):
        if self.source.mode=='synthetic':return
        a=self.source.anchor
        if minute==a+1440:
            self.offset,self.offset_reason=fit_offset([t for t,p in self.offset_pairs],[p for t,p in self.offset_pairs])
            if self.offset_invalid:self.offset,self.offset_reason=None,'INVALID_MODEL_OUTPUT'
            self.phase='calibration'
        if minute==a+2880:
            for variant in ['sensor_only_unadapted','sensor_only_offset24h']:
                for alpha in ['0.10','0.05']:
                    if variant.endswith('offset24h') and self.offset is None:
                        c=Calibration(len(self.calibration_pairs),0,None,'INSUFFICIENT_OFFSET_DATA')
                    else:
                        delta=self.offset if variant.endswith('offset24h') else 0
                        c=calibrate([abs(t-p-delta) for t,p in self.calibration_pairs]+[float('nan')]*self.calibration_invalid,alpha)
                    self.quantiles[(variant,alpha)]=c
            self.frozen=True;self.phase='evaluation'
            # Validate chronological reconstruction against the pinned Stage 5 artifacts.
            if self.source.expected:
                for key,expected in self.source.expected.items():
                    variant,alpha=key.split(':');actual=self.quantiles[(variant,alpha)]
                    off=self.offset if variant.endswith('offset24h') else 0
                    if (actual.reason!=expected['reason'] or actual.n!=expected['n'] or actual.k!=expected['k'] or
                        actual.q is None or abs(actual.q-expected['q'])>1e-8 or off is None or abs(off-expected['offset'])>1e-8):
                        self.artifact_reason='INCOMPATIBLE_ARTIFACTS'

    def issue(self,origin):
        variants=['persistence'] if self.source.mode=='synthetic' else ['sensor_only_unadapted','sensor_only_offset24h']
        for variant in variants:
            intervals=tuple((a,self.quantiles.get((variant,a),Calibration(0,0,None,
                            'SYNTHETIC_INTERVALS_UNCALIBRATED' if self.source.mode=='synthetic' else 'INSUFFICIENT_CALIBRATION')))
                            for a in ['0.10','0.05'])
            result=self.predictor.predict(PredictRequest(origin,self.history.request(origin),variant,self.offset,intervals))
            reason=result.reason
            if any(origin-60<=k<=origin for k in self.history.conflicts):reason='CONFLICTING_DUPLICATE'
            if self.artifact_reason!='OK':reason=self.artifact_reason
            value=result.value if reason=='OK' else None
            bounds=result.intervals if reason=='OK' else tuple((a,None,None,reason) for a in ['0.10','0.05'])
            identity=hashlib.sha256(f'{self.source.id}|{variant}|{origin}'.encode()).hexdigest()[:20]
            self.seq+=1
            accepted=sum(r.valid and r.value is not None and origin-60<=r.minute<=origin for r in self.history.request(origin))
            artifact=('persistence/'+(self.source.configuration or {}).get('generator_version','scripted-v1') if self.source.mode=='synthetic' else
                      'stage5-pinned/'+hashlib.sha256(json.dumps(self.source.expected,sort_keys=True).encode()).hexdigest()[:12]+('/intervals-frozen' if self.frozen else '/intervals-pending'))
            f=Forecast(identity,self.seq,origin,origin+30,variant,self.support_phase(origin),value,reason,bounds,accepted,artifact)
            self.forecasts.append(f);self.pending.setdefault(f.target,[]).append(f)
            if self.store:self.store.event(self,'forecast',f.id,asdict(f))

    def process_minute(self,minute):
        # One authoritative ordering: arrival -> transition -> issue -> target maturity.
        for r in self.arrivals.get(minute,[]):self.last_arrival_reason=self.history.accept(r)
        self.transition(minute)
        if minute%5==0:self.issue(minute)
        for f in self.pending.pop(minute,[]):
            score=self.evaluator.mature(f,minute);self.scores[f.id]=score
            if f.variant=='sensor_only_unadapted' and score.reason=='OK':
                if f.phase=='offset':self.offset_pairs.append((score.observed,f.value))
                elif f.phase=='calibration':self.calibration_pairs.append((score.observed,f.value))
            elif f.variant=='sensor_only_unadapted' and score.observed is not None and f.reason=='INVALID_MODEL_OUTPUT':
                if f.phase=='offset':self.offset_invalid+=1
                elif f.phase=='calibration':self.calibration_invalid+=1
            self.seq+=1
            if self.store:self.store.event(self,'score',f.id,asdict(score))
        self.seq+=1

    def advance_to(self,minute):
        target=min(int(minute),self.end)
        if target<self.minute:raise ValueError('Clock cannot go backwards; reset instead')
        for n in range(self.minute+1,target+1):self.process_minute(n)
        self.minute=target;self.virtual_seconds=float(target*60)
        if target>=self.end:self.status='ended'
        if self.store:self.store.metadata(self)

    def tick(self,elapsed_seconds):
        if self.status!='running':return
        target=min(self.end*60,self.virtual_seconds+elapsed_seconds*self.speed)
        whole=int(target//60)
        if whole>self.minute:self.advance_to(whole)
        self.virtual_seconds=target

    def step(self):
        if self.status=='running':raise ValueError('PAUSE_BEFORE_STEP')
        self.advance_to((self.minute//5+1)*5)

    def snapshot(self,limit=30,after_seq=None):
        if not 1<=limit<=100:raise ValueError('INVALID_PAGE_LIMIT')
        forecasts=[f for f in self.forecasts if after_seq is None or f.seq>after_seq]
        selected=forecasts[-limit:] if after_seq is None else forecasts[:limit]
        ledger=[]
        for f in selected:
            score=self.scores.get(f.id)
            ledger.append(dict(id=f.id,seq=f.seq,variant=f.variant,phase=f.phase,
                origin_time=timestamp(f.origin),target_time=timestamp(f.target),value=f.value,point_reason=f.reason,
                history_start=timestamp(f.origin-60),history_end=timestamp(f.origin),history_count=f.history_count,artifact_identity=f.artifact_identity,
                intervals=[dict(alpha=a,lower=l,upper=u,reason=r) for a,l,u,r in f.intervals],
                score=None if score is None else dict(observed=score.observed,signed_error=score.signed_error,
                    reason=score.reason,matured_time=timestamp(score.matured),coverage=dict(score.coverage))))
        displayed=[]
        for minute in range(max(0,self.minute-180),self.minute+1):
            r=self.history.by_time.get(minute)
            displayed.append(dict(id=r.id if r else f'missing-{minute}',measurement_time=timestamp(minute),
                                  assumed_arrival_time=timestamp(minute),value=r.value if r and r.valid else None))
        last=next((self.history.by_time[k] for k in sorted(self.history.by_time,reverse=True)
                   if self.history.by_time[k].valid and self.history.by_time[k].value is not None),None)
        summaries=self.summaries()
        return dict(session_id=self.id,generation=self.generation,sequence=self.seq,source_id=self.source.id,mode=self.source.mode,
                    provenance='independent hand-authored generator / seeded persistence' if self.source.mode=='synthetic' else 'local pinned Stage 5 artifacts',
                    source_timezone=self.source.source_timezone,session_epoch=timestamp(0),arrival_assumption='zero simulated delay; artificial UTC epoch',
                    virtual_time=timestamp(self.virtual_seconds/60),elapsed_minutes=self.virtual_seconds/60,end_minutes=self.end,
                    status=self.status,speed=self.speed,phase=self.phase,phase_counts=dict(offset=len(self.offset_pairs),calibration=len(self.calibration_pairs),offset_invalid=self.offset_invalid,calibration_invalid=self.calibration_invalid),
                    artifacts_frozen=self.frozen,artifact_reason=self.artifact_reason,warm_start=self.warm,
                    history=displayed,latest_reading=None if last is None else dict(value=last.value,measurement_time=timestamp(last.minute),age_minutes=self.virtual_seconds/60-last.minute),
                    forecasts=ledger,next_after_seq=selected[-1].seq if selected else after_seq,
                    has_more=bool(selected and any(f.seq>selected[-1].seq for f in forecasts)),summaries=summaries,
                    configuration=self.source.configuration,
                    disclosure=self.source.disclosure,forecast_count=len(self.forecasts),arrival_reason=self.last_arrival_reason,
                    gap=(None if not getattr(self.source,'gap',None) else dict(start_time=timestamp(self.source.gap[0]),end_time=timestamp(self.source.gap[1]),label=f'{self.source.gap[1]-self.source.gap[0]}-minute sensor dropout')))

    def summaries(self):
        variants=['persistence'] if self.source.mode=='synthetic' else ['sensor_only_unadapted','sensor_only_offset24h']
        summaries=[]
        for variant in variants:
            fs=[f for f in self.forecasts if f.variant==variant and f.phase in ('synthetic','evaluation')]
            scored=[self.scores[f.id] for f in fs if f.id in self.scores and self.scores[f.id].reason=='OK']
            errors=[s.signed_error for s in scored]
            coverage={a:[dict(s.coverage).get(a) for s in scored if dict(s.coverage).get(a) is not None] for a in ['0.10','0.05']}
            summaries.append(dict(variant=variant,scheduled=len(fs),issued=sum(f.value is not None for f in fs),
                matured=sum(f.id in self.scores for f in fs),scored=len(scored),
                pending=sum(f.value is not None and f.id not in self.scores for f in fs),
                missing_targets=sum(f.value is not None and f.id in self.scores and self.scores[f.id].reason=='TARGET_MISSING' for f in fs),
                coverage_denominators={a:len(vals) for a,vals in coverage.items()},
                interval_available=sum(any(i[3]=='OK' for i in f.intervals) for f in fs),
                mae=sum(abs(e) for e in errors)/len(errors) if errors else None,
                mean_signed_error=sum(errors)/len(errors) if errors else None,
                forecast_availability=sum(f.value is not None for f in fs)/len(fs) if fs else None,
                scoring_availability=len(scored)/sum(f.value is not None for f in fs) if any(f.value is not None for f in fs) else None,
                empirical_coverage={a:sum(vals)/len(vals) if vals else None for a,vals in coverage.items()}))
        return summaries
