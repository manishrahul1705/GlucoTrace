"""Exercise the real loopback HTTP server, using independent synthetic inputs only."""
from pathlib import Path
import json
import time
import uuid
from datetime import datetime
import httpx


def main():
    checks=[]
    with httpx.Client(base_url='http://127.0.0.1:18060',timeout=30) as client:
        def get(path):
            r=client.get(path);r.raise_for_status();return r.json()
        def post(path,body):
            r=client.post(path,json=body);r.raise_for_status();return r.json()
        assert get('/api/health')['status']=='ok';checks.append('health')
        assert any(s['id']=='synthetic-dawn' and s['available'] for s in get('/api/replay/sources')['sources'])
        s=post('/api/replay/sessions',dict(source_id='synthetic-dawn',scenario='dropout15',start='full'))
        id=s['session_id'];generation=s['generation']
        try:
            def control(action,**extra):
                return post(f'/api/replay/sessions/{id}/control',dict(generation=generation,request_id=str(uuid.uuid4()),action=action,**extra))
            assert s['forecasts'][0]['score'] is None
            assert all(i['lower'] is None for f in s['forecasts'] for i in f['intervals'])
            checks.append('synthetic point/interval distinction and pending target omission')
            control('speed',speed=300);control('start');time.sleep(.4);control('pause')
            a=get(f'/api/replay/sessions/{id}/snapshot');time.sleep(.25);b=get(f'/api/replay/sessions/{id}/snapshot')
            assert a==b and a['elapsed_minutes']>0;checks.append('start, speed, pause and read-only snapshot')
            s=post(f'/api/replay/sessions/{id}/reset',dict(generation=generation,request_id=str(uuid.uuid4())))
            old=generation;generation=s['generation']
            assert generation!=old and s['elapsed_minutes']==0 and s['forecast_count']==1
            r=client.post(f'/api/replay/sessions/{id}/control',json=dict(generation=old,request_id='old',action='step'))
            assert r.status_code==409;checks.append('reset generation and stale rejection')
            for _ in range(52):
                s=control('step')
                if s['elapsed_minutes']==90:
                    f=next(f for f in s['forecasts'] if f['origin_time'].endswith('09:00:00+00:00'))
                    assert f['score'] is not None and f['score']['reason']=='OK'
                    assert datetime.fromisoformat(f['target_time'])-datetime.fromisoformat(f['origin_time'])==__import__('datetime').timedelta(minutes=30)
                    checks.append('exact target maturity and delayed scoring')
                if s['elapsed_minutes']==180:
                    assert s['forecasts'][-1]['value'] is None;checks.append('input-loss suppression')
                if s['elapsed_minutes']==250:
                    assert s['forecasts'][-1]['point_reason']=='INCOMPLETE_HISTORY'
                if s['elapsed_minutes']==255:
                    assert s['forecasts'][-1]['point_reason']=='OK';checks.append('complete 61-cell / 60-elapsed-minute recovery')
            assert client.get(f'/api/replay/sessions/{id}/snapshot?limit=101').status_code==422
            assert len(s['history'])<=181 and len(s['forecasts'])<=30
            json.dumps(s,allow_nan=False);checks.append('bounded snapshots and JSON nulls')
            assert 'participant_id' not in json.dumps(s) and 'C:\\Users' not in json.dumps(s)
        finally:client.delete(f'/api/replay/sessions/{id}')
        assert client.get(f'/api/replay/sessions/{id}/snapshot').status_code==410;checks.append('deleted session expiry')
    page=httpx.get('http://127.0.0.1:15173/',timeout=20)
    assert page.status_code==200 and 'id="root"' in page.text;checks.append('frontend HTTP availability (not visual verification)')
    result=dict(status='PASS',scope='Network API integration; synthetic data only; no browser or layout verification',checks=checks)
    root=Path(__file__).resolve().parents[1]
    (root/'reports/stage6/api_integration.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
