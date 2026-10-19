"""Replay metadata regressions; fabricated readings only, no fitting or patient data."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
import pandas as pd
from glucotwin.experiment.common import digest, write
from glucotwin.features import SENSOR_FEATURES
from glucotwin.stage5.core import Calibration
from glucotwin.stage6.engine import History, Session
from glucotwin.stage6.prediction import PredictRequest, Predictor
from glucotwin.stage6.sources import Reading, Registry, synthetic


class RowPresenceTests(unittest.TestCase):
    def prediction(self, history, origin):
        levels = tuple((alpha, Calibration(100, 91 if alpha == '0.10' else 96, 4., 'OK'))
                       for alpha in ('0.10', '0.05'))
        return Predictor(lambda x: x[:, 0]).predict(PredictRequest(origin, history.request(origin),
                    'sensor_only_unadapted', None, levels))

    def test_absent_nonfinite_and_finite_exact_reasons_and_bounds(self):
        cases = [(False, None, False, 'MISSING_CURRENT_READING'),
                 (True, None, False, 'MISSING_CURRENT_READING;NON_FINITE_READING'),
                 (True, float('nan'), False, 'MISSING_CURRENT_READING;NON_FINITE_READING'),
                 (True, float('inf'), False, 'MISSING_CURRENT_READING;NON_FINITE_READING'),
                 (True, 120., True, 'OK')]
        for present, value, valid, reason in cases:
            with self.subTest(present=present, value=value):
                history = History()
                for t in range(60):
                    history.accept(Reading(str(t), t, 120., True))
                history.accept(Reading('current', 60, value, valid, row_present=present))
                self.assertEqual(history.by_time[60].row_present, present)
                result = self.prediction(history, 60)
                self.assertEqual(result.reason, reason)
                self.assertEqual(result.value, 120. if valid else None)
                for alpha, lo, hi, ir in result.intervals:
                    self.assertEqual((lo, hi, ir), (116., 124., 'OK') if valid else (None, None, reason))

    def test_trailing_gaps_staleness_and_first_scheduled_recovery(self):
        for present in (False, True):
            with self.subTest(present=present):
                history = History()
                for t in range(141):
                    missing = 60 <= t < 75
                    history.accept(Reading(str(t), t, None if missing else 120., not missing,
                                           row_present=present if missing else True))
                    if t in (60, 70, 75, 130, 135, 140):
                        result = self.prediction(history, t)
                        if t < 75:
                            expected = 'MISSING_CURRENT_READING' + (';NON_FINITE_READING' if present else '')
                            if t == 70:
                                expected += ';STALE_READING'
                        else:
                            expected = 'INCOMPLETE_HISTORY' if t < 135 else 'OK'
                        self.assertEqual(result.reason, expected)
                        self.assertEqual(result.value, 120. if t >= 135 else None)
                        self.assertEqual(all(i[3] == 'OK' for i in result.intervals), t >= 135)

    def test_presence_survives_normalization_and_serialization(self):
        history = History()
        history.accept(Reading('absent', 0, float('nan'), False, 'wrong-unit', False))
        history.accept(Reading('present', 1, float('inf'), False))
        self.assertFalse(history.by_time[0].row_present)
        self.assertTrue(history.by_time[1].row_present)
        encoded = json.loads(json.dumps([asdict(r) for r in history.request(1)], allow_nan=False))
        self.assertEqual([r['row_present'] for r in encoded], [False, True])

    def test_presence_is_part_of_duplicate_identity(self):
        history = History()
        absent = Reading('a', 0, None, False, row_present=False)
        self.assertEqual(history.accept(absent), 'ACCEPTED')
        self.assertEqual(history.accept(absent), 'IDEMPOTENT')
        self.assertEqual(history.accept(replace(absent, id='b')), 'EQUIVALENT_DUPLICATE')
        self.assertEqual(history.accept(replace(absent, row_present=True)), 'CONFLICTING_DUPLICATE')

    def test_synthetic_injected_loss_is_absent_and_clean_rows_present(self):
        source = synthetic('dropout15')
        self.assertTrue(source.readings[179].row_present)
        self.assertFalse(source.readings[180].row_present)
        self.assertTrue(source.readings[195].row_present)

    def test_session_availability_suppression_and_recovery_do_not_change_values(self):
        absent = synthetic('dropout15')
        present = replace(absent, readings=tuple(replace(r, row_present=True) for r in absent.readings))
        a, b = Session(absent), Session(present)
        for t in (180, 190, 195, 250, 255, 260):
            a.advance_to(t); b.advance_to(t)
            fa, fb = a.forecasts[-1], b.forecasts[-1]
            self.assertEqual((fa.origin, fa.target, fa.value), (fb.origin, fb.target, fb.value))
            self.assertEqual([(x[1],x[2]) for x in fa.intervals], [(x[1],x[2]) for x in fb.intervals])
            self.assertEqual(a.snapshot()['recovery'], b.snapshot()['recovery'])
            expected = ('MISSING_CURRENT_READING' + (';STALE_READING' if t == 190 else '') if t < 195
                        else 'INCOMPLETE_HISTORY' if t < 255 else 'OK')
            self.assertEqual(fa.reason, expected)
            self.assertEqual(a.snapshot()['availability'][0]['current_reason'],
                             'SIMULATED_INPUT_DROPOUT' if t < 195 else expected)
            if t < 195:
                self.assertIn('NON_FINITE_READING', fb.reason)
            else:
                self.assertEqual(fa.reason, fb.reason)

    def test_local_ingestion_retains_original_presence_and_injected_absence(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ROW_METADATA_') as t:
            root = Path(t); project = root / 'project'; runtime = root / 'runtime';runtime.mkdir()
            observations = project / 'data/processed/stage2/observations/p001.csv'
            observations.parent.mkdir(parents=True)
            frame = pd.DataFrame(dict(event_time=pd.date_range('2020-01-01', periods=4501, freq='min'),
                                      glucose_mg_dl=120., valid=True, row_present=True, sensor='Dexcom GL'))
            frame.loc[[100, 105], 'glucose_mg_dl'] = np.nan
            frame.loc[[100, 105], 'valid'] = False
            frame.loc[100, 'row_present'] = False
            frame.to_csv(observations, index=False)
            split = 'reports/stage2/split_manifest.json';proto = 'configs/stage5_protocol.json'
            write(project / split, dict(folds=[dict(test=dict(participants=[1]), train=dict(participants=[2]))]))
            write(project / proto, dict(fixture='SYNTHETIC'))
            write(project / 'reports/stage5/protocol_freeze.json', dict(protocol_sha256=digest(project / proto)))
            local = project / 'data/processed/stage5';local.mkdir(parents=True)
            write(local / 'input_hashes.json', {n: digest(project/n) for n in [split, observations.relative_to(project).as_posix()]})
            write(local / 'calibration_artifacts.json', [dict(participant_id=1, variant=v, alpha=a) for v in
                  ('sensor_only_unadapted','sensor_only_offset24h') for a in ('0.10','0.05')])
            pd.DataFrame([dict(participant_id=1, anchor='2020-01-01')]).to_csv(local/'partition_adequacy.csv', index=False)
            pd.DataFrame([dict(participant_id=1, base_prediction=120., **{f:120. for f in SENSOR_FEATURES})]).to_csv(local/'partition_predictions.csv', index=False)
            write(local/'model_reproduction.json', [dict(participant_id=1)])
            estimator=Mock(n_features_in_=21);estimator.predict.side_effect=lambda x: x[:,0]
            scaler=Mock(n_features_in_=21);scaler.transform.side_effect=lambda x:x
            registry=Registry(project,runtime,True)
            with patch.object(registry,'_check'), patch('joblib.load',return_value=(estimator,scaler)):
                clean=registry.load(next(iter(registry.mapping)), 'clean')
                loss=registry.load(next(iter(registry.mapping)), 'dropout15')
            self.assertFalse(clean.readings[100].row_present)
            self.assertTrue(clean.readings[105].row_present)
            self.assertTrue(clean.readings[110].row_present)
            self.assertFalse(loss.readings[4320].row_present)
            self.assertTrue(loss.readings[4335].row_present)
            self.assertEqual(clean.reference, loss.reference)


if __name__ == '__main__':
    unittest.main()
