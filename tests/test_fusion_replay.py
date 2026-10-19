"""Independent fabricated baseline and multi-family replay regressions."""
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
import numpy as np
from unittest.mock import Mock,patch
from glucotwin.experiment.common import write,digest,load
from glucotwin.experiment.fusion import FEATURES
from glucotwin.contracts import BASE_UNITS
from glucotwin.features import BASELINE_FEATURES
from glucotwin.experiment.fusion import validate_baseline
from glucotwin.stage6.fusion import attach_fusion
from glucotwin.stage6.sources import synthetic
from glucotwin.stage6.engine import Session
from glucotwin.stage6.lab import exploration,export_session
from glucotwin.stage5.core import Calibration

class FusionContracts(unittest.TestCase):
    def baseline(self):return dict(schema=1,participant_id=1,features=BASELINE_FEATURES,units=BASE_UNITS,values=[50.,25.,7.,110.],valid=True)

    def test_valid_baseline_exact_order(self):
        np.testing.assert_array_equal(validate_baseline(self.baseline(),1),[50,25,7,110])

    def test_missing_nonfinite_units_schema_mapping_order(self):
        for field,value,reason in [('values',[50,25,float('nan'),110],'BASELINE_NONFINITE'),
            ('units',{},'BASELINE_UNITS'),('schema',2,'BASELINE_SCHEMA'),('participant_id',2,'BASELINE_PARTICIPANT'),
            ('features',list(reversed(BASELINE_FEATURES)),'BASELINE_SCHEMA'),('valid',False,'BASELINE_NONFINITE')]:
            record=self.baseline();record[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,reason):validate_baseline(record,1)
        with self.assertRaisesRegex(ValueError,'BASELINE_UNAVAILABLE'):validate_baseline(None,1)

    def local(self):
        base=replace(synthetic(),mode='local',anchor=0)
        child=replace(base,model_family='baseline_sensor',predictor=lambda x:x[:,0]+5)
        return replace(base,fusion=child)

    def test_independent_families_numeric_sensor_invariant_and_history(self):
        source=self.local();s=Session(source);original=Session(replace(source,fusion=None))
        for t in [60,90,120]:
            s.advance_to(t);original.advance_to(t)
            own=[f for f in s.forecasts if f.model_family=='sensor_only']
            self.assertEqual([(f.id,f.value,f.reason,f.intervals) for f in own],[(f.id,f.value,f.reason,f.intervals) for f in original.forecasts])
        child=s.children[0];self.assertEqual(child.forecasts[-2].value-original.forecasts[-2].value,5)
        fs=exploration(s,90,180)['forecasts']
        self.assertEqual({f['model_family'] for f in fs},{'sensor_only','baseline_sensor'})
        self.assertTrue(all(not f['score'] or f['score']['matured_time']<=exploration(s,90,180)['virtual_time'] for f in fs))
        self.assertEqual(len({f.seq for f in s.forecasts}),len(s.forecasts))

    def test_missing_combined_does_not_disable_sensor_and_exports_forbidden(self):
        base=replace(synthetic(),mode='local')
        with tempfile.TemporaryDirectory() as t:child=attach_fusion(base,1,Path(t))
        s=Session(replace(base,fusion=child));s.advance_to(120)
        values={f.variant:f for f in s.forecasts[-4:]}
        self.assertIsNotNone(values['sensor_only_unadapted'].value)
        self.assertIsNone(values['baseline_sensor_unadapted'].value)
        self.assertEqual(values['baseline_sensor_unadapted'].reason,'COMBINED_ARTIFACTS_UNAVAILABLE')
        with self.assertRaisesRegex(PermissionError,'PATIENT_EXPORT_DISABLED'):export_session(s,'summary',120,'private')

    def test_loaded_artifact_dimensions_order_mapping_and_baseline_reject(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);base=replace(synthetic(),mode='local')
            baseline=self.baseline();baseline.update(source_file='fabricated.csv',source_row=1,provenance='fixture',availability_assumption='fabricated')
            freeze=dict(feature_order=FEATURES,protocol=load(Path(__file__).resolve().parents[1]/'configs/fusion_protocol.json'))
            cal=[dict(participant_id=1,variant=v,alpha=a) for v in ('baseline_sensor_unadapted','baseline_sensor_offset24h') for a in ('0.10','0.05')]
            write(root/'baseline_001.json',baseline);write(root/'freeze.json',freeze);write(root/'calibration.json',cal);write(root/'paired_summary.json',[])
            (root/'model_001.joblib').write_bytes(b'FABRICATED NOT DESERIALIZED')
            def manifest():write(root/'manifest.json',dict(files={p.name:digest(p) for p in root.iterdir() if p.name!='manifest.json'}))
            manifest();model=Mock(n_features_in_=25);model.predict.side_effect=lambda x:x[:,0];scaler=Mock(n_features_in_=25);scaler.transform.side_effect=lambda x:x
            with patch('joblib.load',return_value=(model,scaler)):
                self.assertEqual(attach_fusion(base,1,root).artifact_reason,'OK')
                model.n_features_in_=24
                self.assertEqual(attach_fusion(base,1,root).artifact_reason,'COMBINED_DIMENSION_MISMATCH')
                model.n_features_in_=25;freeze['feature_order']=list(reversed(FEATURES));write(root/'freeze.json',freeze);manifest()
                self.assertEqual(attach_fusion(base,1,root).artifact_reason,'COMBINED_FEATURE_ORDER_INVALID')
                freeze['feature_order']=FEATURES;write(root/'freeze.json',freeze);baseline['participant_id']=2;write(root/'baseline_001.json',baseline);manifest()
                self.assertEqual(attach_fusion(base,1,root).artifact_reason,'BASELINE_PARTICIPANT_MISMATCH')

    def test_mixed_readiness_reverse_order_and_input_loss(self):
        source=self.local();source=replace(source,readings=synthetic('dropout15').readings,gap=(180,195))
        source=replace(source,fusion=replace(source.fusion,readings=source.readings,gap=source.gap))
        s=Session(source);s.advance_to(120)
        s.children[0].quantiles={('baseline_sensor_unadapted','0.05'):Calibration(100,96,7.,'OK')}
        before={x['variant']:x for x in s.summaries()};s.variants=lambda:list(reversed(list(before)))
        self.assertEqual({x['variant']:x for x in s.summaries()},before)
        s.advance_to(180);self.assertTrue(all(f.value is None for f in s.forecasts[-4:]))
        self.assertTrue(all(f.reason==('MISSING_CURRENT_READING' if f.variant.endswith('unadapted') else 'INSUFFICIENT_OFFSET_DATA') for f in s.forecasts[-4:]))
        s.advance_to(255);self.assertIsNotNone(s.forecasts[-4].value);self.assertIsNotNone(s.forecasts[-2].value)
        child=s.children[0];self.assertEqual(child.calibration('baseline_sensor_unadapted','0.05').reason,'OK')
        self.assertEqual(child.calibration('baseline_sensor_unadapted','0.10').reason,'INSUFFICIENT_CALIBRATION')

if __name__=='__main__':unittest.main()
