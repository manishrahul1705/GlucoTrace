"""Deterministic minute-event engine, immutable forecast/score ledger and SQLite."""
from collections import deque
from dataclasses import dataclass,asdict,replace
from pathlib import Path
import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime,timezone
from glucotwin.stage5.core import Calibration,fit_offset,calibrate,interval_bounds
from .sources import Reading,Source
from .endpoint_flags import issued_flags,views as endpoint_views
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
    model_family: str = 'sensor_only'
    endpoint_flags: tuple = ()


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
        payload=(reading.minute,raw_value,reading.valid,reading.unit,reading.row_present)
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
        if not reading.row_present:
            reading=replace(reading,value=None,valid=False)
        if reading.value is not None and (not math.isfinite(reading.value) or not 40<=reading.value<=400):
            reading=replace(reading,value=None,valid=False)
        if reading.unit!='mg/dL':
            reading=replace(reading,valid=False)
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


def compute_recovery(session):
    m = int(session.virtual_seconds / 60)
    consecutive = 0
    k = m
    while k >= 0:
        reading = session.history.by_time.get(k)
        if reading is not None and reading.valid and reading.value is not None:
            consecutive += 1
            k -= 1
        else:
            break
    required_cells = 61
    required_minutes = 60
    valid_minutes = max(0, consecutive - 1) if consecutive > 0 else 0
    next_issue = ((m // 5) + 1) * 5
    next_issue_time = timestamp(next_issue)
    gap = getattr(session.source, 'gap', None)
    in_gap = bool(gap and gap[0] <= m < gap[1])
    is_suppressed = consecutive < required_cells

    if consecutive >= required_cells:
        suppression_reason = None
        suppression_message = 'History requirement satisfied (61 consecutive minute cells spanning 60 elapsed minutes).'
        conditional_recovery_minute = m
        conditional_recovery_time = timestamp(m)
        conditional_recovery_label = 'Fully recovered: history requirement satisfied.'
        next_issue_eligible = True
    elif consecutive == 0:
        suppression_reason = 'SIMULATED_INPUT_DROPOUT' if in_gap else 'MISSING_CURRENT_READING'
        suppression_message = 'Simulated input dropout active: current reading is missing.' if in_gap else 'Current reading is missing; input stream interrupted.'
        conditional_recovery_minute = None
        conditional_recovery_time = None
        conditional_recovery_label = 'Awaiting continuous valid input arrival (0 of 61 cells). Recovery estimate will be computed once continuous readings begin arriving.'
        next_issue_eligible = False
    else:
        cells_needed = required_cells - consecutive
        ready_minute = m + cells_needed
        rec_min = math.ceil(ready_minute / 5) * 5
        conditional_recovery_minute = rec_min
        conditional_recovery_time = timestamp(rec_min)
        rec_hhmm = conditional_recovery_time[11:16]
        if gap and m >= gap[1]:
            suppression_reason = 'INCOMPLETE_HISTORY'
            suppression_message = f'History recovery in progress: {consecutive} of 61 consecutive minute cells ({valid_minutes} of 60 elapsed minutes) accumulated following simulated input dropout.'
        elif m < 60:
            suppression_reason = 'INSUFFICIENT_HISTORY'
            suppression_message = f'Initial warm-up period: {consecutive} of 61 consecutive minute cells ({valid_minutes} of 60 elapsed minutes) accumulated.'
        else:
            suppression_reason = 'INCOMPLETE_HISTORY'
            suppression_message = f'History rebuilding in progress: {consecutive} of 61 consecutive minute cells ({valid_minutes} of 60 elapsed minutes) accumulated.'
        conditional_recovery_label = f'Earliest eligible issue if readings continue without interruption: Minute {rec_min} ({rec_hhmm} UTC). Requires {cells_needed} more consecutive valid minute readings.'
        next_issue_eligible = (next_issue >= rec_min)

    # Scheduling ends at the last arrived minute, inclusive. Do not alter issue().
    if next_issue > session.end or session.status == 'ended':
        next_issue = None
        next_issue_time = None
        next_issue_eligible = False
    if session.status == 'ended' or (conditional_recovery_minute is not None and conditional_recovery_minute > session.end):
        conditional_recovery_minute = conditional_recovery_time = None
        conditional_recovery_label = ('Session ended; no future issue is scheduled.' if session.status == 'ended'
                                      else 'History cannot recover on the issue grid within this session.')
    available = sum(r is not None and r.valid and r.value is not None
                    for r in (session.history.by_time.get(t) for t in range(max(0,m-60),m+1)))
    return dict(
        required_cells=required_cells,
        required_minutes=required_minutes,
        available_valid_cells=available,
        support_span_minutes=max(0,min(consecutive,required_cells)-1),
        consecutive_valid_cells=consecutive,
        consecutive_valid_minutes=valid_minutes,
        is_suppressed=is_suppressed,
        suppression_reason=suppression_reason,
        suppression_message=suppression_message,
        next_issue_minute=next_issue,
        next_issue_time=next_issue_time,
        next_issue_eligible=next_issue_eligible,
        conditional_recovery_minute=conditional_recovery_minute,
        conditional_recovery_time=conditional_recovery_time,
        conditional_recovery_label=conditional_recovery_label
    )


class Session:

    def variants(self):
        return self.own_variants()+[v for child in self.children for v in child.variants()]

    def own_variants(self):
        return ['persistence'] if self.source.mode=='synthetic' else [self.source.model_family+'_unadapted',self.source.model_family+'_offset24h']

    def calibration(self,variant,alpha):
        return self.quantiles.get((variant,alpha),Calibration(0,0,None,
            'SYNTHETIC_INTERVALS_UNCALIBRATED' if self.source.mode=='synthetic' else 'INSUFFICIENT_CALIBRATION'))

    def availability(self,recovery):
        """Read-only projection; never run a predictor or create a future forecast.

        Current success is known only at an actual issue cutoff. Between issues,
        known blockers are reported; otherwise readiness awaits the next issue.
        Calibration readiness and usable bounds on an issued point are separate.
        """
        latest={f.variant:f for f in self.forecasts}
        views=[]
        for variant in self.own_variants():
            f=latest.get(variant)
            blocker=self.artifact_reason
            if blocker=='OK' and variant.endswith('_offset24h') and self.offset is None:
                blocker=self.offset_reason
            current=blocker
            if self.status=='ended':current='SESSION_ENDED'
            elif self.minute<0:current='SESSION_NOT_STARTED'
            elif current=='OK' and recovery['is_suppressed']:current=recovery['suppression_reason']
            elif current=='OK':
                current=f.reason if f and f.origin*60==self.virtual_seconds else 'AWAITING_NEXT_ISSUE'
            future=('SESSION_ENDED' if recovery['next_issue_minute'] is None else
                    blocker if blocker!='OK' else 'AWAITING_NEXT_ISSUE')
            issued_intervals={a:r for a,lo,hi,r in f.intervals} if f else {}
            levels=[]
            for alpha in ['0.10','0.05']:
                cal=self.calibration(variant,alpha)
                calibration_reason=interval_bounds(0.,cal)[2]
                levels.append(dict(alpha=alpha,calibration_reason=calibration_reason,
                    current_reason=current if current!='OK' else issued_intervals.get(alpha,'NO_FORECAST_ISSUED'),
                    latest_reason=issued_intervals.get(alpha,'NO_FORECAST_ISSUED')))
            views.append(dict(variant=variant,capability_reason=self.artifact_reason,
                current_reason=current,next_issue_reason=future,
                latest_forecast_id=f.id if f else None,
                latest_origin_time=timestamp(f.origin) if f else None,
                latest_point_reason=f.reason if f else 'NO_FORECAST_ISSUED',
                intervals=levels))
        return views+[v for child in self.children for v in child.availability(recovery)]

    def __init__(self,source:Source,store=None,id=None,warm=False):
        self.id=id or str(uuid.uuid4());self.generation=str(uuid.uuid4());self.source=source;self.store=store
        self.predictor=Predictor(source.predictor);self.evaluator=Evaluator(source.reference)
        self.history=History();self.minute=-1;self.virtual_seconds=0.;self.seq=0;self.status='paused';self.speed=60
        self.children=[Session(source.fusion)] if source.fusion is not None else []
        self.child_cursors=[0 for _ in self.children]
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
            for variant in self.own_variants():
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
        variants=self.own_variants()
        for variant in variants:
            intervals=tuple((a,self.calibration(variant,a)) for a in ['0.10','0.05'])
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
            f=Forecast(identity,self.seq,origin,origin+30,variant,self.support_phase(origin),value,reason,bounds,accepted,artifact,
                       'persistence' if self.source.mode=='synthetic' else self.source.model_family,issued_flags(value,reason))
            self.forecasts.append(f);self.pending.setdefault(f.target,[]).append(f)
            if self.store:self.store.event(self,'forecast',f.id,asdict(f))

    def process_minute(self,minute):
        # One authoritative ordering: arrival -> transition -> issue -> target maturity.
        for r in self.arrivals.get(minute,[]):self.last_arrival_reason=self.history.accept(r)
        self.transition(minute)
        if minute%5==0:self.issue(minute)
        for f in self.pending.pop(minute,[]):
            score=self.evaluator.mature(f,minute);self.scores[f.id]=score
            if f.variant==self.source.model_family+'_unadapted' and score.reason=='OK':
                if f.phase=='offset':self.offset_pairs.append((score.observed,f.value))
                elif f.phase=='calibration':self.calibration_pairs.append((score.observed,f.value))
            elif f.variant==self.source.model_family+'_unadapted' and score.observed is not None and f.reason=='INVALID_MODEL_OUTPUT':
                if f.phase=='offset':self.offset_invalid+=1
                elif f.phase=='calibration':self.calibration_invalid+=1
            self.seq+=1
            if self.store:self.store.event(self,'score',f.id,asdict(score))
        for i,child in enumerate(self.children):
            child.advance_to(minute)
            for forecast in child.forecasts[self.child_cursors[i]:]:
                self.seq+=1;forecast=replace(forecast,seq=self.seq);self.forecasts.append(forecast)
                if self.store:self.store.event(self,'forecast',forecast.id,asdict(forecast))
            self.child_cursors[i]=len(child.forecasts)
            for identifier,score in child.scores.items():
                if identifier not in self.scores:
                    self.scores[identifier]=score
                    if self.store:self.store.event(self,'score',identifier,asdict(score))
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
            ledger.append(dict(id=f.id,seq=f.seq,variant=f.variant,model_family=f.model_family,phase=f.phase,
                origin_time=timestamp(f.origin),target_time=timestamp(f.target),value=f.value,point_reason=f.reason,
                history_start=timestamp(f.origin-60),history_end=timestamp(f.origin),history_count=f.history_count,artifact_identity=f.artifact_identity,
                intervals=[dict(alpha=a,lower=l,upper=u,reason=r) for a,l,u,r in f.intervals],endpoint_flags=endpoint_views(f,score,self.minute),
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
        recovery=compute_recovery(self)
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
                    baseline_context=self.source.baseline_context,
                    disclosure=self.source.disclosure,forecast_count=len(self.forecasts),arrival_reason=self.last_arrival_reason,
                    gap=(None if not getattr(self.source,'gap',None) else dict(start_time=timestamp(self.source.gap[0]),end_time=timestamp(self.source.gap[1]),label=f'{self.source.gap[1]-self.source.gap[0]}-minute simulated input dropout')),
                    recovery=recovery,availability=self.availability(recovery))

    def summaries(self):
        variants=self.variants()
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
