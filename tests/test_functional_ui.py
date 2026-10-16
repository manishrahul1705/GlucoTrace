"""User-facing name validation through the production API, no private artifacts."""
import tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from glucotwin.stage6.api import create_app

class FunctionalUI(unittest.TestCase):
    def test_name_rejects_blank_input_without_changing_printable_user_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with TestClient(create_app(root=root,runtime=root/'runtime',run_clock=False,local_enabled=False)) as client:
                session=client.post('/api/replay/sessions',json={'source_id':'synthetic-dawn','start':'full'}).json()
                url='/api/replay/library/'+session['session_id']+'/rename'
                for name in ['', '   ', '\t', 'a\nb', 'x'*81]:
                    with self.subTest(name=name):
                        self.assertEqual(client.post(url,json={'name':name}).status_code,422)
                for name in ['  +name', '=Formula, "quoted"', 'x'*80]:
                    response=client.post(url,json={'name':name})
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(response.json()['name'],name)
