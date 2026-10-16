"""Release boundary regressions against production API, no private input files."""
import unittest,tempfile,csv,io,json
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
from fastapi.testclient import TestClient
from glucotwin.stage6.api import create_app

class ReleaseReadiness(unittest.TestCase):
 def test_actual_restart_rename_summary_and_recreation(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);runtime=root/'runtime'
   with TestClient(create_app(root=root,runtime=runtime,run_clock=False,local_enabled=False)) as c:
    original=c.post('/api/replay/sessions',json=dict(source_id='synthetic-dawn',scenario='meal',seed=42,start='warm')).json()
    sid=original['session_id'];url='/api/replay/library/'+sid
    self.assertEqual(c.post(url+'/rename',json={'name':'Retained "meal", =42'}).status_code,200)
    for name in ['', 'x'*81,'bad\nname']:
     self.assertEqual(c.post(url+'/rename',json={'name':name}).status_code,422)
    saved=c.get(url).json()
   with TestClient(create_app(root=root,runtime=runtime,run_clock=False,local_enabled=False)) as c:
    item=c.get(url).json();self.assertEqual(item['status'],'expired')
    self.assertEqual(item['name'],saved['name']);self.assertEqual(item['summary'],saved['summary'])
    self.assertEqual(c.get('/api/replay/sessions/'+sid+'/snapshot').status_code,410)
    response=c.post(url+'/recreate',json={'start':'warm'});self.assertEqual(response.status_code,200)
    new=response.json();self.assertNotEqual(new['session_id'],sid);self.assertNotEqual(new['generation'],original['generation'])
    self.assertEqual(new['configuration'],original['configuration']);self.assertEqual(new['history'],original['history'])
    self.assertEqual([f['value'] for f in new['forecasts']],[f['value'] for f in original['forecasts']])
 def test_running_export_cutoff_size_and_private_backend_rejection(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);app=create_app(root=root,runtime=root/'runtime',run_clock=False,local_enabled=False)
   with TestClient(app) as c:
    s=c.post('/api/replay/sessions',json={'source_id':'synthetic-dawn'}).json();base='/api/replay/sessions/'+s['session_id']
    c.post(base+'/control',json=dict(generation=s['generation'],request_id='start',action='start'))
    before=c.get(base+'/snapshot').json()
    for kind in ['configuration','readings','forecasts','scores','summary']:
     r=c.post(base+'/export',json=dict(generation=s['generation'],kind=kind));self.assertEqual(r.status_code,200)
     self.assertLessEqual(len(r.content),2_000_000);self.assertEqual(r.headers['x-content-type-options'],'nosniff')
     self.assertEqual(r.headers['content-disposition'],f'attachment; filename="glucotwin-synthetic-{kind}.{"json" if kind in ["configuration","summary"] else "csv"}"')
     rows=[json.loads(r.text)] if kind in ['configuration','summary'] else list(csv.DictReader(io.StringIO(r.text)))
     for row in rows:
      self.assertEqual(row['export_schema_version'],'glucotwin-synthetic-export-v1');self.assertEqual(str(row['seed']),'1705')
      self.assertEqual(row['virtual_cutoff'],s['virtual_time']);self.assertEqual(row['units'],'mg/dL')
      if kind=='forecasts' and row['target_time']>s['virtual_time']:self.assertEqual(row['observed_target'],'')
    self.assertEqual(c.get(base+'/snapshot').json(),before)
    with patch('glucotwin.stage6.api.export_session',return_value=('x'*2_000_001,'text/csv')):
     self.assertEqual(c.post(base+'/export',json=dict(generation=s['generation'],kind='readings')).status_code,413)
    manager=app.state.manager
    manager.sessions[s['session_id']].source=replace(manager.sessions[s['session_id']].source,mode='local')
    for kind in ['configuration','readings','forecasts','scores','summary']:
     self.assertEqual(c.post(base+'/export',json=dict(generation=s['generation'],kind=kind)).status_code,403)
