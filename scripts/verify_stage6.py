"""Stage 6 read-only agreement and isolation checks; does not alter Stage 5."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from glucotwin.stage6.sources import Registry,synthetic
from glucotwin.stage6.engine import Session


def run():
    out=ROOT/'reports/stage6';out.mkdir(parents=True,exist_ok=True)
    initial=json.loads((ROOT/'data/runtime/stage6/starting_state.json').read_text())
    # Byte preservation, including the Stage 5 frozen config and all reports.
    preserved={name:value for name,value in initial['hashes'].items()
               if name.startswith(('reports/stage4/','reports/stage5/','data/processed/stage5/')) or name=='configs/stage5_protocol.json'}
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in preserved.items())
    synthetic_checks=[]
    for minutes in [0,15,30,60,120]:
        scenario='clean' if not minutes else f'dropout{minutes}'
        a,b=Session(synthetic(scenario)),Session(synthetic(scenario))
        for _ in range(100):a.step()
        b.status='running';b.speed=300;b.tick(100)
        assert a.forecasts==b.forecasts
        assert a.scores==b.scores
        json.dumps(a.snapshot(),allow_nan=False)
        synthetic_checks.append(dict(scenario=scenario,identical_ledger=True,scheduled=len(a.forecasts)))
    rows=[];blockers=[]
    with tempfile.TemporaryDirectory(dir=ROOT/'data/runtime/stage6') as directory:
        registry=Registry(ROOT,Path(directory),True)
        if not registry.mapping:blockers.append('Local Stage 5 artifacts unavailable')
        else:
            # Stored predictions are verification-only. Replay never reads them as forecasts.
            frozen=pd.read_csv(ROOT/'data/processed/stage5/partition_predictions.csv')
            for identifier,pid in registry.mapping.items():
                source=registry.load(identifier,'clean')
                session=Session(source,warm=True)
                assert session.artifact_reason=='OK'
                # 120 minutes after the first support-safe evaluation issue; all earlier
                # history/labels traverse the same arrival/transition/maturity engine.
                session.advance_to(session.minute+120)
                p=frozen[(frozen.participant_id==pid)&(frozen.partition=='evaluation')]
                original=pd.read_csv(ROOT/f'data/processed/stage2/observations/p{pid:03d}.csv',nrows=1)
                start=pd.Timestamp(original.event_time.iloc[0])
                by_minute={int((pd.Timestamp(r.issue_time)-start).total_seconds()/60):r for r in p.itertuples()}
                count=0;max_error=0.
                for f in session.forecasts:
                    if f.phase!='evaluation' or f.origin not in by_minute:continue
                    r=by_minute[f.origin]
                    expected=r.base_prediction+(session.offset if f.variant.endswith('offset24h') else 0)
                    assert f.value is not None
                    error=abs(f.value-expected);assert error<1e-8
                    max_error=max(max_error,error);count+=1
                    for alpha,lo,hi,reason in f.intervals:
                        a=source.expected[f'{f.variant}:{alpha}']
                        assert reason=='OK' and abs(lo-(expected-a['q']))<1e-8 and abs(hi-(expected+a['q']))<1e-8
                assert count>0
                rows.append(dict(n_matched_forecasts=count,max_abs_error=max_error))
                print(f'Local chronological agreement checked ({len(rows)}/{len(registry.mapping)})',flush=True)
    browser_path=out/'browser_verification.json'
    browser=json.loads(browser_path.read_text()) if browser_path.exists() else {}
    browser_ok=browser.get('status')=='PASS' and bool(browser.get('tested_source_sha256')) and all(
        hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in browser.get('tested_source_sha256',{}).items())
    browser_blockers=[] if browser_ok else ['Current browser verification evidence missing or stale; run node scripts/verify_stage6_browser.mjs']
    result=dict(status='PASS' if browser_ok and not blockers else 'PARTIAL_BROWSER_BLOCKED',
                implementation_checks='PASS',synthetic_scenarios=synthetic_checks,
                local_sources_checked=len(rows),matched_forecasts=sum(x['n_matched_forecasts'] for x in rows),
                max_prediction_abs_difference=max((r['max_abs_error'] for r in rows),default=None),
                local_agreement_scope='First 120 elapsed evaluation minutes per available source, plus full chronological early-phase reconstruction; not a new full-cohort performance study',
                historical_stage4_stage5_preserved=True,
                browser_verified=browser_ok,screenshots=browser.get('screenshots',[]) if browser_ok else [],
                blockers=[*browser_blockers,*blockers],
                independence='Uses Stage 6 production engine and Stage 5 frozen evidence; this is agreement testing, not wholly independent scientific verification',
                scientific_limitations=['Exploratory processed-data replay; original arrivals and upstream interpolation unresolved',
                    'Nominal Stage 5 coverage not fully achieved; high-glucose deterioration and sparse below70 evidence remain',
                    'No clinical/live validation or guaranteed coverage; permissions unresolved'])
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':run()
