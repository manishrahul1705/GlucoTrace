"""Explicit synthetic zero-fit pipeline fixture; cannot pass production parent gates."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from glucotwin.experiment import endpoints
from glucotwin.experiment.common import ROOT,digest,write,hashes,source_files,runtime,load

class EndpointExperimentTests(unittest.TestCase):
 def test_zero_fit_fixture_and_independent_confusion_verification(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);sensor=root/'sensor';fusion=root/'fusion';fusion.mkdir();path=sensor/'project/data/processed/stage5';path.mkdir(parents=True)
   rows=[]
   variants=['sensor_only_unadapted','sensor_only_offset24h','baseline_sensor_unadapted','baseline_sensor_offset24h']
   for pid in range(1,15):
    for variant in variants:
     for scenario in ['clean','input_loss_15m','input_loss_30m','input_loss_60m','input_loss_120m']:
      for alpha in ['0.05','0.10']:
       for minute,pred,target in [(0,181.,181.),(5,179.,179.),(10,179.,np.nan)]:
        rows.append(dict(participant_id=pid,variant=variant,scenario=scenario,alpha=alpha,issue_time=f'2026-01-01T00:{minute:02d}:00+00:00',prediction=pred,target=target,point_reason='OK',clean_eligible=np.isfinite(target)))
   rows=pd.DataFrame(rows)
   rows[rows.variant.str.startswith('sensor_only')].to_csv(path/'evaluation.csv',index=False)
   rows[rows.variant.str.startswith('baseline_sensor')].to_csv(fusion/'evaluation.csv',index=False)
   f=dict(kind='ENDPOINT_RESEARCH_FREEZE',fits=0,synthetic_fixture=True,sensor_bundle=str(sensor),fusion_bundle=str(fusion),protocol=dict(thresholds_mg_dl=[180,250],primary_variant=variants[0],secondary_variants=variants[1:]),source_sha256=hashes(ROOT,source_files()),runtime=runtime(),input_sha256={k:digest(p) for k,p in endpoints.inputs(sensor,fusion).items()})
   freeze=root/'freeze';freeze.mkdir();write(freeze/'freeze.json',f);out=root/'out'
   # Python-only fixture seam; the CLI has no flag to bypass genuine parent gates.
   with patch.object(endpoints,'check_parents',return_value=None):
    trusted=endpoints.execute(freeze/'freeze.json',digest(freeze/'freeze.json'),out)
    result=endpoints.verify(out,trusted)
   self.assertEqual(result['fits'],0);self.assertEqual(result['participant_model_scenario_threshold_cases'],560)
   per=pd.read_csv(out/'participants.csv');above=per[per.threshold_mg_dl.eq(180)]
   self.assertTrue((above.TP==1).all());self.assertTrue((above.TN==1).all());self.assertTrue((above.FP==0).all());self.assertTrue((above.FN==0).all());self.assertTrue((above.missing_target==1).all())
   high=per[per.threshold_mg_dl.eq(250)];self.assertTrue(high.precision.isna().all());self.assertTrue(high.recall.isna().all());self.assertTrue((high.specificity==1).all())
   with self.assertRaises((ValueError,FileNotFoundError,KeyError)):endpoints.verify(out,trusted)
   # Exact hash gate catches changed output rather than accepting changed references.
   with (out/'participants.csv').open('a') as stream:stream.write('tampered')
   with self.assertRaises(ValueError):endpoints.verify(out,trusted)
