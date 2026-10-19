"""Approved source loading. Synthetic mode never reads patient artifacts."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import hmac
import json
import math
import numpy as np
import pandas as pd
from glucotwin.features import SENSOR_FEATURES

SYNTHETIC_DISCLOSURE = ('Synthetic scenario demonstration. No real patient readings. '
                        'Not a validated physiological simulator.')
LOCAL_DISCLOSURE = ('Retrospective replay of processed data. Arrival times are assumed. '
                   'Released values include upstream interpolation. Not a live sensor connection.')
SCENARIOS = ['clean','dropout15','dropout30','dropout60','dropout120']


@dataclass(frozen=True)
class Reading:
    id: str
    minute: int
    value: float | None
    valid: bool
    unit: str = 'mg/dL'
    row_present: bool = True


@dataclass
class Source:
    id: str
    mode: str
    readings: tuple[Reading, ...]
    reference: dict[int, float | None]
    anchor: int
    predictor: object
    expected: dict | None = None
    disclosure: str = SYNTHETIC_DISCLOSURE
    source_timezone: str = 'not_applicable'
    gap: tuple[int,int] | None = None
    artifact_reason: str = 'OK'
    configuration: dict | None = None


class SourceUnavailable(ValueError):
    pass


def synthetic(scenario='clean', seed=1705, length=721):
    """Hand-authored pulses and seeded noise; no dataset or learned parameters."""
    if scenario not in SCENARIOS:
        raise SourceUnavailable('UNKNOWN_SCENARIO')
    rng=np.random.default_rng(seed)
    t=np.arange(length,dtype=float)
    correlated=np.zeros(length)
    for i in range(1,length): correlated[i]=.92*correlated[i-1]+rng.normal(0,.3)
    glucose=108+7*np.sin(2*np.pi*t/360)+correlated+rng.normal(0,.6,length)
    # Scripted generic meal/activity pulses, not physiological parameter estimates.
    for start,height,width in [(75,57,32),(335,72,43),(435,-23,45)]:
        pulse=np.maximum(t-start,0)/width
        glucose+=height*pulse*np.exp(1-pulse)*(t>=start)
    reference={i:float(v) for i,v in enumerate(glucose)}
    gap=None if scenario=='clean' else (180,180+int(scenario.removeprefix('dropout')))
    readings=tuple(Reading(f'syn-{i:05d}',i,None if gap and gap[0]<=i<gap[1] else float(v),
                           not (gap and gap[0]<=i<gap[1]),
                           row_present=not (gap and gap[0]<=i<gap[1])) for i,v in enumerate(glucose))
    return Source('synthetic-dawn','synthetic',readings,reference,0,lambda x:x[:,0],gap=gap)


class Registry:
    def __init__(self, root: Path, runtime: Path, local_enabled=False):
        self.root,self.runtime,self.local_enabled=root,runtime,local_enabled
        self.mapping={}
        self.local_error=None
        if local_enabled:
            try:
                keypath=runtime/'source-key'
                if not keypath.exists():
                    import secrets
                    keypath.write_bytes(secrets.token_bytes(32))
                key=keypath.read_bytes()
                artifacts=json.loads((root/'data/processed/stage5/calibration_artifacts.json').read_text())
                if (not isinstance(artifacts,list) or not artifacts or
                    any(not isinstance(a,dict) or type(a.get('participant_id')) is not int or a['participant_id']<1 for a in artifacts)):
                    raise ValueError('Invalid local artifact schema')
                for pid in sorted({a['participant_id'] for a in artifacts}):
                    identifier='local-'+hmac.new(key,str(pid).encode(),hashlib.sha256).hexdigest()[:16]
                    self.mapping[identifier]=pid
            except (OSError,ValueError,KeyError): self.local_error='LOCAL_ARTIFACTS_UNAVAILABLE'

    def list(self):
        items=[dict(id='synthetic-dawn',mode='synthetic',label='Scripted day / independent synthetic',
                    available=True,reason=None,disclosure=SYNTHETIC_DISCLOSURE)]
        if not self.local_enabled or self.local_error:
            items.append(dict(id='local-unavailable',mode='local',label='Local processed-data replay',available=False,
                         reason=self.local_error or 'LOCAL_MODE_DISABLED',disclosure=LOCAL_DISCLOSURE))
        else:
            for identifier in sorted(self.mapping):
                try: self._check(self.mapping[identifier]);reason=None
                except SourceUnavailable as exc: reason=str(exc)
                items.append(dict(id=identifier,mode='local',label='Local processed stream '+identifier[-4:],
                                  available=reason is None,reason=reason,disclosure=LOCAL_DISCLOSURE))
        return dict(sources=items,scenarios=SCENARIOS)

    def _check(self,pid):
        required=[f'data/processed/stage2/observations/p{pid:03d}.csv',
                  f'data/processed/stage5/model_{pid:03d}.joblib','data/processed/stage5/model_reproduction.json',
                  'data/processed/stage5/calibration_artifacts.json','data/processed/stage5/partition_adequacy.csv',
                  'reports/stage2/split_manifest.json','configs/stage5_protocol.json',
                  'reports/stage5/protocol_freeze.json','data/processed/stage5/input_hashes.json',
                  'data/processed/stage5/partition_predictions.csv']
        if any(not (self.root/p).is_file() for p in required):
            raise SourceUnavailable('LOCAL_ARTIFACTS_UNAVAILABLE')

    def load(self,identifier,scenario):
        if scenario not in SCENARIOS: raise SourceUnavailable('UNKNOWN_SCENARIO')
        if identifier=='synthetic-dawn': return synthetic(scenario)
        if identifier not in self.mapping:
            if not self.local_enabled: raise SourceUnavailable('LOCAL_MODE_DISABLED')
            if self.local_error: raise SourceUnavailable(self.local_error)
            raise SourceUnavailable('SOURCE_UNAVAILABLE')
        pid=self.mapping[identifier];self._check(pid)
        try:
            import joblib
            root=self.root
            proto=root/'configs/stage5_protocol.json'
            expected_hash=json.loads((root/'reports/stage5/protocol_freeze.json').read_text())['protocol_sha256']
            if hashlib.sha256(proto.read_bytes()).hexdigest()!=expected_hash:
                raise SourceUnavailable('INCOMPATIBLE_ARTIFACTS')
            inputs=json.loads((root/'data/processed/stage5/input_hashes.json').read_text())
            observation_path=f'data/processed/stage2/observations/p{pid:03d}.csv'
            for rel in [observation_path,'reports/stage2/split_manifest.json']:
                if hashlib.sha256((root/rel).read_bytes()).hexdigest()!=inputs[rel]:
                    raise SourceUnavailable('INCOMPATIBLE_ARTIFACTS')
            split=json.loads((root/'reports/stage2/split_manifest.json').read_text())
            fold=next(f for f in split['folds'] if f['test']['participants']==[pid])
            if pid in fold['train']['participants']:raise SourceUnavailable('INCOMPATIBLE_ARTIFACTS')
            est,scaler=joblib.load(root/f'data/processed/stage5/model_{pid:03d}.joblib')
            if scaler.n_features_in_!=len(SENSOR_FEATURES) or est.n_features_in_!=len(SENSOR_FEATURES):
                raise SourceUnavailable('INCOMPATIBLE_ARTIFACTS')
            frame=pd.read_csv(root/observation_path,parse_dates=['event_time'])
            if not frame.sensor.eq('Dexcom GL').all(): raise SourceUnavailable('INVALID_SENSOR')
            times=pd.DatetimeIndex(frame.event_time);start=times[0]
            if times.tz is not None or not times.equals(pd.date_range(start,periods=len(frame),freq='min')):
                raise SourceUnavailable('INCOMPATIBLE_ARTIFACTS')
            adequacy=pd.read_csv(root/'data/processed/stage5/partition_adequacy.csv')
            anchor_time=pd.Timestamp(adequacy[adequacy.participant_id==pid].anchor.iloc[0])
            anchor=int((anchor_time-start).total_seconds()/60)
            artifacts=json.loads((root/'data/processed/stage5/calibration_artifacts.json').read_text())
            expected={f"{a['variant']}:{a['alpha']}":a for a in artifacts if a['participant_id']==pid}
            if len(expected)!=4:raise SourceUnavailable('INCOMPATIBLE_ARTIFACTS')
            predict=lambda x:est.predict(scaler.transform(x))
            # Verification-only stored predictions pin model identity. They are never
            # used to generate a replay forecast or passed to the predictor component.
            frozen=pd.read_csv(root/'data/processed/stage5/partition_predictions.csv')
            frozen=frozen[frozen.participant_id==pid]
            actual=predict(frozen[SENSOR_FEATURES].to_numpy())
            if not np.allclose(actual,frozen.base_prediction.to_numpy(),rtol=0,atol=1e-8):
                raise SourceUnavailable('INCOMPATIBLE_ARTIFACTS')
            reproduction=json.loads((root/'data/processed/stage5/model_reproduction.json').read_text())
            if not any(r['participant_id']==pid for r in reproduction):raise SourceUnavailable('INCOMPATIBLE_ARTIFACTS')
            ref={i:float(v) if bool(valid) and math.isfinite(v) else None
                 for i,(v,valid) in enumerate(zip(frame.glucose_mg_dl,frame.valid))}
            gap=None
            if scenario!='clean':
                begin=math.ceil((anchor+72*60)/5)*5
                gap=(begin,begin+int(scenario.removeprefix('dropout')))
            readings=tuple(Reading(f'local-{i:05d}',i,None if gap and gap[0]<=i<gap[1] else ref[i],
                                   ref[i] is not None and not(gap and gap[0]<=i<gap[1]),
                                   row_present=bool(frame.row_present.iloc[i]) and not(gap and gap[0]<=i<gap[1])) for i in ref)
            return Source(identifier,'local',readings,ref,anchor,predict,expected,LOCAL_DISCLOSURE,'unknown',gap)
        except SourceUnavailable:raise
        except Exception:raise SourceUnavailable('INCOMPATIBLE_ARTIFACTS') from None
