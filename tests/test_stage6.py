"""Replay engine and real HTTP schema tests with independent synthetic inputs."""
from dataclasses import asdict,replace
from pathlib import Path
import json
import tempfile
import unittest
import numpy as np
from fastapi.testclient import TestClient
from glucotwin.stage6.sources import synthetic,Reading,Source,Registry
from glucotwin.stage6.prediction import Predictor,PredictRequest
from glucotwin.stage6.engine import Session,History,Store
from glucotwin.stage6.api import create_app,Manager


def event_content(session):
    return ([{k:v for k,v in asdict(f).items() if k!='seq'} for f in session.forecasts],
            [asdict(s) for s in session.scores.values()])


class TestReplay(unittest.TestCase):
    def test_seeded_generator_independent_and_deterministic(self):
        self.assertEqual(synthetic().readings,synthetic().readings)
        self.assertNotEqual(synthetic(seed=2).readings,synthetic(seed=3).readings)
        with tempfile.TemporaryDirectory() as d:
            r=Registry(Path(d),Path(d),False)
            self.assertEqual(r.load('synthetic-dawn','clean').mode,'synthetic')
            self.assertEqual(r.list()['sources'][1]['reason'],'LOCAL_MODE_DISABLED')

    def test_step_and_accelerated_event_equivalence(self):
        a,b=Session(synthetic()),Session(synthetic())
        for _ in range(50):a.step()
        b.speed=300;b.status='running';b.tick(50)
        self.assertEqual(a.minute,b.minute)
        self.assertEqual(event_content(a),event_content(b))

    def test_pause_and_snapshot_are_pure(self):
        s=Session(synthetic(),warm=True);before=s.snapshot();s.tick(60)
        self.assertEqual(before,s.snapshot());self.assertEqual(s.snapshot(),s.snapshot())

    def test_exact_target_pending_disclosure(self):
        s=Session(synthetic());s.advance_to(60)
        f=s.forecasts[-1]
        self.assertEqual(f.target-f.origin,30)
        pending=s.snapshot()['forecasts'][-1];self.assertIsNone(pending['score'])
        self.assertNotIn('observed',pending)
        s.advance_to(90)
        self.assertEqual(s.scores[f.id].observed,s.source.reference[90])

    def test_future_mutation_is_absent_from_prediction_request(self):
        src=synthetic();a=Session(src)
        changed=replace(src,readings=tuple(replace(r,value=333.) if r.minute>100 else r for r in src.readings),
                        reference={k:(333. if k>100 else v) for k,v in src.reference.items()})
        b=Session(changed);a.advance_to(100);b.advance_to(100)
        self.assertEqual(event_content(a),event_content(b))
        self.assertEqual(set(PredictRequest.__dataclass_fields__),{'origin','history','variant','offset','quantiles'})
        with self.assertRaises(ValueError):Predictor(lambda x:x[:,0]).predict(PredictRequest(10,(Reading('future',11,100,True),),'persistence',None,()))

    def test_all_gaps_suppress_and_restore_full_support(self):
        for duration in [15,30,60,120]:
            with self.subTest(duration=duration):
                s=Session(synthetic(f'dropout{duration}'));s.advance_to(180+duration+65)
                bad=[f for f in s.forecasts if 180<=f.origin<180+duration+60]
                self.assertTrue(all(f.value is None for f in bad))
                restored=next(f for f in s.forecasts if f.origin==180+duration+60)
                self.assertEqual(restored.reason,'OK')
                self.assertTrue(s.source.reference[180] is not None)
                self.assertEqual(next(f for f in s.forecasts if f.origin==180+duration+55).reason,'INCOMPLETE_HISTORY')

    def test_history_recovery_calculation_and_gap_label(self):
        s0=Session(synthetic('clean'))
        r0=s0.snapshot()['recovery']
        self.assertEqual(r0['consecutive_valid_cells'],1)
        self.assertEqual(r0['required_cells'],61)
        self.assertEqual(r0['suppression_reason'],'INSUFFICIENT_HISTORY')
        self.assertEqual(r0['conditional_recovery_minute'],60)
        self.assertTrue(r0['is_suppressed'])
        self.assertFalse(r0['next_issue_eligible'])

        s0.advance_to(60)
        r60=s0.snapshot()['recovery']
        self.assertEqual(r60['consecutive_valid_cells'],61)
        self.assertFalse(r60['is_suppressed'])
        self.assertIsNone(r60['suppression_reason'])
        self.assertEqual(r60['conditional_recovery_minute'],60)
        self.assertTrue(r60['next_issue_eligible'])

        s=Session(synthetic('dropout30'))
        snap=s.snapshot()
        self.assertIn('30-minute simulated input dropout',snap['gap']['label'])

        s.advance_to(185)
        r_drop=s.snapshot()['recovery']
        self.assertEqual(r_drop['consecutive_valid_cells'],0)
        self.assertTrue(r_drop['is_suppressed'])
        self.assertEqual(r_drop['suppression_reason'],'SIMULATED_INPUT_DROPOUT')
        self.assertIsNone(r_drop['conditional_recovery_minute'])
        self.assertIsNone(r_drop['conditional_recovery_time'])
        self.assertFalse(r_drop['next_issue_eligible'])

        s.advance_to(210)
        r_post=s.snapshot()['recovery']
        self.assertEqual(r_post['consecutive_valid_cells'],1)
        self.assertTrue(r_post['is_suppressed'])
        self.assertEqual(r_post['suppression_reason'],'INCOMPLETE_HISTORY')
        self.assertEqual(r_post['conditional_recovery_minute'],270)
        self.assertFalse(r_post['next_issue_eligible'])

        s.advance_to(230)
        r_230=s.snapshot()['recovery']
        self.assertEqual(r_230['consecutive_valid_cells'],21)
        self.assertEqual(r_230['conditional_recovery_minute'],270)

        s.advance_to(270)
        r_rec=s.snapshot()['recovery']
        self.assertEqual(r_rec['consecutive_valid_cells'],61)
        self.assertFalse(r_rec['is_suppressed'])
        self.assertIsNone(r_rec['suppression_reason'])

        s.arrivals[275]=[Reading('gap-test',275,None,False)]
        s.advance_to(275)
        r_interrupted=s.snapshot()['recovery']
        self.assertEqual(r_interrupted['consecutive_valid_cells'],0)
        self.assertTrue(r_interrupted['is_suppressed'])
        self.assertIsNone(r_interrupted['conditional_recovery_minute'])

    def test_recovery_off_grid_reconnection_and_anchors(self):
        # 1. Off-grid reconnection at minute 183:
        # Readings are missing for minutes 180, 181, 182; valid readings resume at minute 183.
        src = synthetic('clean')
        readings_183 = tuple(r for r in src.readings if not (180 <= r.minute <= 182))
        s_183 = Session(replace(src, readings=readings_183))

        s_183.advance_to(182)
        r_182 = s_183.snapshot()['recovery']
        self.assertEqual(r_182['consecutive_valid_cells'], 0)
        self.assertTrue(r_182['is_suppressed'])
        self.assertIsNone(r_182['conditional_recovery_minute'])

        # At minute 183, first valid reading arrives
        s_183.advance_to(183)
        r_183 = s_183.snapshot()['recovery']
        self.assertEqual(r_183['consecutive_valid_cells'], 1)
        self.assertTrue(r_183['is_suppressed'])
        # Continuous 61 cells complete at 183 + 60 = 243.
        # Earliest eligible issue-grid anchor (minute % 5 == 0) is 245.
        self.assertEqual(r_183['conditional_recovery_minute'], 245)

        # At minute 240 (scheduled issue): consecutive = 58 cells (< 61) -> suppressed
        s_183.advance_to(240)
        r_240 = s_183.snapshot()['recovery']
        self.assertEqual(r_240['consecutive_valid_cells'], 58)
        self.assertTrue(r_240['is_suppressed'])
        self.assertEqual(r_240['conditional_recovery_minute'], 245)
        f_240 = next(f for f in s_183.forecasts if f.origin == 240)
        self.assertIsNone(f_240.value)
        self.assertEqual(f_240.reason, 'INCOMPLETE_HISTORY')

        # At minute 243: continuous cells = 61. History requirement is satisfied.
        # But minute 243 is not on the issue grid (243 % 5 != 0), so no forecast is issued.
        s_183.advance_to(243)
        r_243 = s_183.snapshot()['recovery']
        self.assertEqual(r_243['consecutive_valid_cells'], 61)
        self.assertFalse(r_243['is_suppressed'])
        self.assertIsNone(r_243['suppression_reason'])
        self.assertEqual(r_243['next_issue_minute'], 245)
        self.assertTrue(r_243['next_issue_eligible'])
        self.assertFalse(any(f.origin == 243 for f in s_183.forecasts))

        # At minute 245: on issue grid (245 % 5 == 0). Consecutive = 63 (>= 61).
        # Trailing 61 cells [185..245] are valid -> Forecast issued with reason OK.
        s_183.advance_to(245)
        f_245 = next(f for f in s_183.forecasts if f.origin == 245)
        self.assertIsNotNone(f_245.value)
        self.assertEqual(f_245.reason, 'OK')

        # 2. Off-grid reconnection at minute 187:
        # Outage from 180 to 186; valid readings resume at 187.
        readings_187 = tuple(r for r in src.readings if not (180 <= r.minute <= 186))
        s_187 = Session(replace(src, readings=readings_187))
        s_187.advance_to(187)
        r_187 = s_187.snapshot()['recovery']
        self.assertEqual(r_187['consecutive_valid_cells'], 1)
        # 187 + 60 = 247. Earliest issue-grid anchor is ceil(247/5)*5 = 250.
        self.assertEqual(r_187['conditional_recovery_minute'], 250)

        s_187.advance_to(245)
        f_245_b = next(f for f in s_187.forecasts if f.origin == 245)
        self.assertIsNone(f_245_b.value)
        self.assertEqual(f_245_b.reason, 'INCOMPLETE_HISTORY')

        s_187.advance_to(250)
        f_250 = next(f for f in s_187.forecasts if f.origin == 250)
        self.assertIsNotNone(f_250.value)
        self.assertEqual(f_250.reason, 'OK')

        # 3. Interrupted recovery:
        # Resume at 183, accumulate 30 cells (minute 212), then drop out at 213.
        s_int = Session(replace(src, readings=readings_183))
        s_int.advance_to(212)
        self.assertEqual(s_int.snapshot()['recovery']['consecutive_valid_cells'], 30)
        s_int.arrivals[213] = [Reading('dropout', 213, None, False)]
        s_int.advance_to(213)
        r_int = s_int.snapshot()['recovery']
        self.assertEqual(r_int['consecutive_valid_cells'], 0)
        self.assertTrue(r_int['is_suppressed'])
        self.assertIsNone(r_int['conditional_recovery_minute'])

        # 4. Already-complete history:
        s_comp = Session(synthetic('clean'))
        s_comp.advance_to(120)
        r_comp = s_comp.snapshot()['recovery']
        self.assertGreaterEqual(r_comp['consecutive_valid_cells'], 61)
        self.assertFalse(r_comp['is_suppressed'])
        self.assertIsNone(r_comp['suppression_reason'])
        self.assertTrue(r_comp['next_issue_eligible'])

        # 5. Warm start:
        s_warm = Session(synthetic('clean'), warm=True)
        self.assertEqual(s_warm.minute, 120)
        r_warm = s_warm.snapshot()['recovery']
        self.assertGreaterEqual(r_warm['consecutive_valid_cells'], 61)
        self.assertFalse(r_warm['is_suppressed'])
        f_120 = next(f for f in s_warm.forecasts if f.origin == 120)
        self.assertEqual(f_120.reason, 'OK')

    def test_duplicates_idempotent_equivalent_conflicting(self):
        h=History();r=Reading('a',0,100,True)
        self.assertEqual(h.accept(r),'ACCEPTED');self.assertEqual(h.accept(r),'IDEMPOTENT')
        self.assertEqual(h.accept(replace(r,id='b')),'EQUIVALENT_DUPLICATE')
        self.assertEqual(h.accept(replace(r,id='c',value=101)),'CONFLICTING_DUPLICATE')
        self.assertFalse(h.by_time[0].valid)
        invalid=History();invalid.accept(Reading('bad1',0,450.,True))
        self.assertEqual(invalid.accept(Reading('bad2',0,460.,True)),'CONFLICTING_DUPLICATE')
        duplicate=Reading('nan',1,float('nan'),True)
        self.assertEqual(invalid.accept(duplicate),'ACCEPTED')
        self.assertEqual(invalid.accept(duplicate),'IDEMPOTENT')
        src=synthetic();a=Session(src);a.advance_to(100);saved=asdict(a.forecasts[-1])
        a.history.accept(Reading('conflict-new',100,200,True))
        self.assertEqual(asdict(a.forecasts[-1]),saved)

    def test_invalid_units_nonfinite_and_missing_current(self):
        rows=tuple(Reading(str(i),i,100.,True) for i in range(61))
        p=Predictor(lambda x:np.full(len(x),np.nan))
        self.assertEqual(p.predict(PredictRequest(60,rows,'persistence',None,())).reason,'INVALID_MODEL_OUTPUT')
        p=Predictor(lambda x:x[:,0])
        invalid=(*rows[:-1],replace(rows[-1],unit='mmol/L'))
        self.assertEqual(p.predict(PredictRequest(60,invalid,'persistence',None,())).reason,'INVALID_UNIT')
        invalid=(*rows[:-1],replace(rows[-1],value=float('nan')))
        self.assertIn('NON_FINITE_READING',p.predict(PredictRequest(60,invalid,'persistence',None,())).reason)

    def test_phase_freezes_are_chronological_and_support_safe(self):
        n=3101;rows=tuple(Reading(str(i),i,100+np.sin(i/80),True) for i in range(n))
        src=Source('test-local','local',rows,{r.minute:r.value for r in rows},0,lambda x:x[:,0])
        s=Session(src);s.advance_to(1439)
        self.assertIsNone(s.offset);self.assertTrue(all(f.origin+30<1440 for f in s.forecasts if f.phase=='offset'))
        s.advance_to(1440);self.assertIsNotNone(s.offset)
        before=s.offset;s.advance_to(2880)
        self.assertTrue(s.frozen);quantiles=s.quantiles.copy()
        self.assertEqual(s.phase,'evaluation');s.advance_to(3000)
        self.assertEqual(s.offset,before);self.assertEqual(s.quantiles,quantiles)
        self.assertEqual(next(f.origin for f in s.forecasts if f.phase=='evaluation'),2940)
        self.assertTrue(all(q.n>=100 for q in quantiles.values()))

    def test_invalid_calibration_score_invalidates_set(self):
        rows=(Reading('initial',0,100.,True),)
        s=Session(Source('local-test','local',rows,{0:100.},0,lambda x:x[:,0]))
        s.offset=0.;s.calibration_pairs=[(100.,100.)]*120;s.calibration_invalid=1
        s.transition(2880)
        self.assertTrue(all(q.reason=='INVALID_CALIBRATION_SCORES' and q.invalid_count==1 for q in s.quantiles.values()))

    def test_missing_exact_target_is_not_nearest_substituted(self):
        src=synthetic();ref=src.reference.copy();ref[90]=None
        s=Session(replace(src,reference=ref));s.advance_to(90)
        f=next(f for f in s.forecasts if f.origin==60)
        self.assertEqual(s.scores[f.id].reason,'TARGET_MISSING')
        self.assertIsNone(s.scores[f.id].observed)

    def test_invalid_interval_keeps_valid_point(self):
        from glucotwin.stage5.core import Calibration
        history=tuple(Reading(str(i),i,100.,True) for i in range(61))
        result=Predictor(lambda x:x[:,0]).predict(PredictRequest(60,history,'persistence',None,
                         (('0.10',Calibration(100,91,-1.,'OK')),)))
        self.assertEqual(result.reason,'OK');self.assertEqual(result.value,100.)
        self.assertEqual(result.intervals[0][3],'INVALID_INTERVAL_ORDER')

    def test_bounded_snapshot_and_pages(self):
        s=Session(synthetic());s.advance_to(400)
        snap=s.snapshot(limit=7,after_seq=0)
        self.assertEqual(len(snap['forecasts']),7);self.assertLessEqual(len(snap['history']),181)
        page=s.snapshot(limit=7,after_seq=snap['next_after_seq'])
        self.assertTrue(set(f['id'] for f in snap['forecasts']).isdisjoint(f['id'] for f in page['forecasts']))
        self.assertTrue(snap['has_more'])


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.app=create_app(root=self.root,runtime=self.root/'runtime',local_enabled=False,run_clock=False)
        self.client=TestClient(self.app);self.client.__enter__()
    def tearDown(self):
        self.client.__exit__(None,None,None);self.temp.cleanup()
    def session(self):
        r=self.client.post('/api/replay/sessions',json={'source_id':'synthetic-dawn','start':'warm'})
        self.assertEqual(r.status_code,200);return r.json()

    def test_synthetic_without_any_patient_artifact(self):
        self.assertFalse((self.root/'data').exists());s=self.session()
        self.assertEqual(s['mode'],'synthetic');self.assertEqual(s['summaries'][0]['interval_available'],0)
        self.assertTrue(all(i['lower'] is None for f in s['forecasts'] for i in f['intervals']))

    def test_controls_reset_stale_generation_idempotency(self):
        s=self.session();id=s['session_id'];body=dict(generation=s['generation'],request_id='step1',action='step')
        a=self.client.post(f'/api/replay/sessions/{id}/control',json=body).json()
        b=self.client.post(f'/api/replay/sessions/{id}/control',json=body).json();self.assertEqual(a,b)
        reset=dict(generation=s['generation'],request_id='reset1')
        n=self.client.post(f'/api/replay/sessions/{id}/reset',json=reset).json()
        self.assertNotEqual(n['generation'],s['generation']);self.assertEqual(n['elapsed_minutes'],120)
        self.assertEqual(n,self.client.post(f'/api/replay/sessions/{id}/reset',json=reset).json())
        self.assertEqual(self.client.post(f'/api/replay/sessions/{id}/control',json={**body,'request_id':'stale'}).status_code,409)
        self.assertEqual(self.client.post(f'/api/replay/sessions/{id}/control',json=body).status_code,409)

    def test_concurrent_duplicate_control_advances_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from glucotwin.stage6.api import Control
        s=self.session();manager=self.app.state.manager
        request=Control(generation=s['generation'],request_id='parallel',action='step')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:manager.command(s['session_id'],request),range(4)))
        self.assertTrue(all(r==results[0] for r in results))
        self.assertEqual(manager.get(s['session_id']).minute,125)

    def test_clock_pause_and_pure_get(self):
        s=self.session();m=self.app.state.manager;session=m.get(s['session_id'])
        wall=[0.];m.clock=lambda:wall[0];m.last_wall=0;session.status='running';session.speed=300
        wall[0]=2;m.advance_wall();self.assertEqual(session.minute,130)
        session.status='paused';wall[0]=100;m.advance_wall();self.assertEqual(session.minute,130)
        a=self.client.get(f"/api/replay/sessions/{s['session_id']}/snapshot").json()
        b=self.client.get(f"/api/replay/sessions/{s['session_id']}/snapshot").json();self.assertEqual(a,b)

    def test_schema_boundaries_missing_artifacts_and_no_paths(self):
        for source in ['../../private','local-unavailable']:
            r=self.client.post('/api/replay/sessions',json={'source_id':source})
            self.assertEqual(r.status_code,409);self.assertNotIn(str(self.root),r.text)
        s=self.session();self.assertEqual(self.client.get(f"/api/replay/sessions/{s['session_id']}/snapshot?limit=101").status_code,422)
        self.assertEqual(self.client.post('/api/replay/sessions',json={'source_id':'synthetic-dawn','file':'private'}).status_code,422)
        body=self.client.get(f"/api/replay/sessions/{s['session_id']}/snapshot").text
        self.assertNotIn('NaN',body);self.assertNotIn('participant_id',body)

    def test_restart_expiry_preserves_events(self):
        s=self.session();id=s['session_id'];m=self.app.state.manager
        count=m.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        other=Manager(self.root,self.root/'runtime',False)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:other.get(id)
        self.assertEqual(caught.exception.status_code,410)
        self.assertEqual(other.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0],count)
        other.store.db.close()

    def test_cors_and_delete(self):
        s=self.session()
        response=self.client.get('/api/health',headers={'Origin':'https://unapproved.example'})
        self.assertNotIn('access-control-allow-origin',response.headers)
        response=self.client.get('/api/health',headers={'Origin':'http://127.0.0.1:15173'})
        self.assertEqual(response.headers['access-control-allow-origin'],'http://127.0.0.1:15173')
        self.assertEqual(self.client.delete(f"/api/replay/sessions/{s['session_id']}").status_code,200)
        self.assertEqual(self.client.get(f"/api/replay/sessions/{s['session_id']}/snapshot").status_code,410)


if __name__=='__main__':unittest.main()
