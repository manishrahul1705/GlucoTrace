"""Synthetic end-to-end fusion rehearsal, never a production patient bundle."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from glucotwin.experiment import fusion
from glucotwin.experiment.common import write,digest,runtime

class FusionExperiment(unittest.TestCase):
    def test_synthetic_generation_and_independent_verification(self):
        import test_new_experiment as fixtures
        c=fixtures.BundleFixtures;c.setUpClass()
        try:
            with tempfile.TemporaryDirectory(prefix='SYNTHETIC_FUSION_REHEARSAL_') as t:
                p=Path(t);root=Path(__file__).resolve().parents[1]
                f=dict(parent_bundle=str(c.bundle),parent_manifest_sha256=c.trusted,
                    source_sha256={'src/glucotwin/experiment/fusion.py':digest(root/'src/glucotwin/experiment/fusion.py')},runtime=runtime(),
                    feature_order=fusion.FEATURES,protocol=json.loads((root/'configs/fusion_protocol.json').read_text()),inputs={},
                    selected=[dict(outer_fold=x['outer_fold'],selected_candidate_spec='{"alpha":1.0}') for x in c.split['folds']])
                write(p/'freeze/freeze.json',f)
                # Explicitly bypass only the production patient-bundle gate for this fabricated fixture.
                with patch.object(fusion,'check_hashes',return_value=(c.project,{},{})):
                    result=fusion.execute(p/'freeze/freeze.json',digest(p/'freeze/freeze.json'),p/'output')
                    self.assertEqual(result['fits'],14)
                    self.assertEqual(fusion.verify(p/'output',result['artifact_manifest_sha256'])['status'],'PASS')
        finally:c.tearDownClass()

if __name__=='__main__':unittest.main()
