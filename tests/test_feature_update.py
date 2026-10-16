"""Scenario/library/inspection/export tests through production functions and API."""
from pathlib import Path
from dataclasses import replace,asdict
import tempfile,unittest,json,csv,io,sqlite3
from fastapi.testclient import TestClient
from glucotwin.stage6.scenarios import make_scenario,CATALOG
from glucotwin.stage6.engine import Session,Store
from glucotwin.stage6.lab import export_session,exploration
from glucotwin.stage6.api import create_app,Manager

class FeatureFunctions(unittest.TestCase):
    def test_all_scenarios_reproduce_across_playback_speed(self):
        for name in CATALOG:
            with self.subTest(scenario=name):
                src=make_scenario(name,42,360);a=Session(src);b=Session(make_scenario(name,42,360))
                a.advance_to(360);b.speed=300;b.status='running';b.tick(72)
                self.assertEqual(a.forecasts,b.forecasts);self.assertEqual(a.scores,b.scores)
                self.assertEqual(src.readings,make_scenario(name,42,360).readings)
        self.assertNotEqual(make_scenario('noisy',1).readings,make_scenario('noisy',2).readings)

    def test_export_cutoff_deterministic_and_does_not_reveal_future(self):
        s=Session(make_scenario('meal',7));s.advance_to(85)
        before={kind:export_session(s,kind,85,'=unsafe,"name"')[0] for kind in ['configuration','readings','forecasts','scores','summary']}
        s.advance_to(160)
        self.assertEqual(before,{kind:export_session(s,kind,85,'=unsafe,"name"')[0] for kind in before})
        forecasts=list(csv.DictReader(io.StringIO(before['forecasts'])))
        pending=next(f for f in forecasts if f['origin_time'].endswith('09:00:00+00:00'))
        self.assertEqual(pending['observed_target'],'');self.assertEqual(pending['score_status'],'PENDING')
        self.assertTrue(all(row['session_name'].startswith("'=unsafe,") for row in forecasts))
        self.assertTrue(all(row['virtual_cutoff'].endswith('09:25:00+00:00') for row in forecasts))
        self.assertEqual(len(list(csv.DictReader(io.StringIO(before['readings'])))),86)
        for content in before.values():self.assertNotIn('NaN',content)

    def test_inspection_history_and_scores_respect_historical_cutoff(self):
        s=Session(make_scenario());s.advance_to(120)
        view=exploration(s,60,60);self.assertEqual(len(view['history']),61)
        self.assertTrue(all(f['score'] is None for f in view['forecasts'] if f['origin_time'].endswith('09:00:00+00:00')))
        f=view['forecasts'][-1];self.assertEqual(f['history_count'],61);self.assertEqual(f['artifact_identity'],'persistence/scripted-v1')
        with self.assertRaises(ValueError):exploration(s,121,60)
        with self.assertRaises(ValueError):exploration(s,60,10000)
        self.assertIsNone(s.snapshot()['gap'])

    def test_patient_export_blocked_even_with_synthetic_like_fixture(self):
        s=Session(replace(make_scenario(),mode='local'))
        for kind in ['configuration','readings','forecasts','scores','summary']:
            with self.assertRaises(PermissionError):export_session(s,kind,0,'test')

    def test_summary_empty_missing_target_and_variant_denominators(self):
        src=make_scenario();ref=dict(src.reference);ref.pop(90);s=Session(replace(src,reference=ref))
        self.assertIsNone(s.summaries()[0]['mean_signed_error'])
        s.advance_to(95);a=s.summaries()[0]
        self.assertEqual(a['issued'],a['scored']+a['missing_targets']+a['pending']);self.assertEqual(a['missing_targets'],1)
        export=json.loads(export_session(s,'summary',95,'x')[0])['summary']
        for field in ['scheduled','issued','scored','pending','missing_targets','mae','mean_signed_error']:
            self.assertEqual(export[field],a[field])
        local=Session(replace(src,mode='local'));local.advance_to(95)
        self.assertEqual([x['scheduled'] for x in local.summaries()],[0,0])

    def test_migration_backs_up_and_preserves_old_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'old.sqlite3';db=sqlite3.connect(p)
            db.executescript('CREATE TABLE sessions(id TEXT PRIMARY KEY,generation TEXT,metadata TEXT,expired INTEGER DEFAULT 0); CREATE TABLE events(session TEXT,generation TEXT,id TEXT,kind TEXT,payload TEXT,PRIMARY KEY(session,generation,id,kind));')
            db.execute('INSERT INTO sessions VALUES(?,?,?,0)',('old','g',json.dumps(dict(source_id='opaque',mode='synthetic',minute=10,status='paused'))))
            db.execute('INSERT INTO events VALUES(?,?,?,?,?)',('old','g','f','forecast','{}'));db.commit();db.close()
            store=Store(p);self.assertEqual(store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
            self.assertEqual(store.db.execute('SELECT expired FROM sessions').fetchone()[0],1)
            backup=sqlite3.connect(str(p)+'.before-library-v0.sqlite3');self.assertEqual(backup.execute('SELECT expired FROM sessions').fetchone()[0],0);backup.close();store.db.close()

class FeatureAPI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.app=create_app(root=self.root,runtime=self.root/'runtime',run_clock=False,local_enabled=False)
        self.client=TestClient(self.app);self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None);self.temp.cleanup()
    def create(self,**extra):
        r=self.client.post('/api/replay/sessions',json=dict(source_id='synthetic-dawn',**extra));self.assertEqual(r.status_code,200);return r.json()
    def test_invalid_configuration_and_request_bounds(self):
        for extra in [dict(seed=-1),dict(seed=True),dict(seed=1.2),dict(duration_minutes=359),dict(duration_minutes=361),dict(scenario='../../file'),dict(expression='x')]:
            self.assertEqual(self.client.post('/api/replay/sessions',json=dict(source_id='synthetic-dawn',**extra)).status_code,422)
        self.assertEqual(self.client.get('/api/replay/library?limit=51').status_code,422)
    def test_rename_recreate_summary_and_restart_expiry(self):
        s=self.create(scenario='steady',seed=123,start='full');identity=(s['session_id'],s['generation'])
        item=self.client.post(f"/api/replay/library/{identity[0]}/rename",json={'name':'A harmless name'}).json()
        self.assertEqual((item['id'],item['generation']),identity)
        recreated=self.client.post(f"/api/replay/library/{identity[0]}/recreate",json={'start':'full'}).json()
        self.assertNotEqual(recreated['session_id'],identity[0]);self.assertNotEqual(recreated['generation'],identity[1]);self.assertEqual(recreated['configuration'],s['configuration'])
        self.assertEqual(recreated['history'],s['history'])
        self.client.delete('/api/replay/sessions/'+identity[0]);item=self.client.get('/api/replay/library/'+identity[0]).json()
        self.assertEqual(item['status'],'expired');self.assertTrue(item['recreatable']);self.assertIsNotNone(item['summary'])
        other=Manager(self.root,self.root/'runtime',False);self.assertFalse(other.sessions);other.store.db.close()
    def test_inspector_and_export_api_validation(self):
        s=self.create(start='warm');base='/api/replay/sessions/'+s['session_id']
        self.assertEqual(s['forecasts'][-1]['history_count'],61);self.assertIsNone(s['forecasts'][-1]['score'])
        for kind in ['configuration','readings','forecasts','scores','summary']:
            r=self.client.post(base+'/export',json=dict(generation=s['generation'],kind=kind,cutoff_minute=60));self.assertEqual(r.status_code,200);self.assertIn('glucotwin-synthetic-',r.headers['content-disposition'])
        self.assertEqual(self.client.post(base+'/export',json=dict(generation='expired',kind='summary')).status_code,409)
        self.assertEqual(self.client.post(base+'/export',json=dict(generation=s['generation'],kind='bad')).status_code,422)
        self.assertEqual(self.client.post(base+'/export',json=dict(generation=s['generation'],kind='summary',cutoff_minute=121)).status_code,422)
        self.assertEqual(self.client.get(base+'/explore?end_minute=121').status_code,422)
        self.assertEqual(self.client.get('/api/replay/library/missing').status_code,404)
    def test_reset_retains_config_and_rename(self):
        s=self.create(scenario='activity',seed=777);id=s['session_id']
        self.client.post(f'/api/replay/library/{id}/rename',json={'name':'Keep me'})
        n=self.client.post(f'/api/replay/sessions/{id}/reset',json=dict(generation=s['generation'],request_id='reset')).json()
        self.assertEqual(s['configuration'],n['configuration']);self.assertNotEqual(s['generation'],n['generation'])
        self.assertEqual(self.client.get(f'/api/replay/library/{id}').json()['name'],'Keep me')
