"""Acceptance guard tests use fabricated messages, never private data or models."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from glucotwin.experiment.acceptance import Records, HTTPAcceptance, same, minute, source_mapping
from glucotwin.experiment.common import write

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preservation', ROOT / 'scripts/preserve_new_experiment.py')
preservation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preservation)


class AcceptanceGuards(unittest.TestCase):
    def test_missing_value_and_numeric_corruption_rejected(self):
        same(None, float('nan'))
        same(120., 120.)
        for actual, expected in [(120., float('nan')), (None, 120.), (120.001, 120.)]:
            with self.subTest(actual=actual, expected=expected), self.assertRaises(AssertionError):
                same(actual, expected)

    def test_epoch_translation_retains_elapsed_minutes(self):
        self.assertEqual(minute('2020-01-03T01:00:00', '2020-01-01T00:00:00'), 2940)
        self.assertEqual(minute('2026-01-03T09:00:00Z', '2026-01-01T08:00:00Z'), 2940)

    def test_frozen_bound_and_reason_mutations_are_detected(self):
        records = Records.__new__(Records)
        rows = pd.DataFrame([dict(minute=0, variant='unadapted', alpha='0.10', prediction=120.,
                                point_reason='OK', lower=100., upper=140., interval_reason='OK')]).set_index(['minute','variant','alpha'])
        f = dict(origin_time='2020-01-01', variant='unadapted', value=120., point_reason='OK',
                 intervals=[dict(alpha='0.10', lower=100., upper=140., reason='OK')])
        records.check_forecast(f, '2020-01-01', rows)
        f['intervals'][0]['upper'] = 141.
        with self.assertRaises(AssertionError):
            records.check_forecast(f, '2020-01-01', rows)
        f['intervals'][0]['upper'] = 140.
        f['point_reason'] = 'INCOMPLETE_HISTORY'
        with self.assertRaises(AssertionError):
            records.check_forecast(f, '2020-01-01', rows)

    def test_future_score_or_reading_rejected(self):
        runner = HTTPAcceptance.__new__(HTTPAcceptance)
        s = dict(virtual_time='2020-01-01T00:10:00', forecasts=[dict(origin_time='2020-01-01T00:05:00', score=None)], history=[])
        runner.check_cutoff(s)
        s['forecasts'][0]['score'] = dict(matured_time='2020-01-01T00:35:00')
        with self.assertRaises(AssertionError):
            runner.check_cutoff(s)
        s['forecasts'][0]['score'] = None
        s['history'] = [dict(measurement_time='2020-01-01T00:11:00')]
        with self.assertRaises(AssertionError):
            runner.check_cutoff(s)

    def test_source_mapping_uses_actual_runtime_key(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'source-key';p.write_bytes(b'fixture-key-one')
            records = type('R', (), dict(pids=[1,2]))()
            first = source_mapping(records, t)
            p.write_bytes(b'fixture-key-two')
            second = source_mapping(records, t)
            self.assertEqual(len(set(first.values())), 2)
            self.assertNotEqual(first, second)

    def test_inventory_tracks_empty_dirs_bytes_and_corruption(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t);(root / 'empty').mkdir();(root / 'file').write_bytes(b'fixture')
            before = preservation.inventory(root)
            self.assertIn('empty/', before)
            self.assertEqual(before['file']['size'], 7)
            (root / 'file').write_bytes(b'changed')
            self.assertNotEqual(preservation.inventory(root), before)

    def test_preservation_refuses_overwrite_and_preserves_failure_record(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t);src = root / 'source';src.mkdir()
            write(src / 'run-manifest.json', dict(artifact_manifest_sha256='trusted', fits_completed=14))
            dst = root / 'destination'
            with patch.object(preservation, 'check_hashes'), patch.object(preservation, 'verify', side_effect=ValueError('fixture verifier failure')):
                with self.assertRaisesRegex(ValueError, 'fixture verifier failure'):
                    preservation.preserve(src, dst, 'trusted')
            self.assertEqual(preservation.load(dst / 'migration.json')['status'], 'FAIL')
            self.assertEqual(preservation.inventory(dst / 'bundle'), preservation.inventory(src))
            with self.assertRaisesRegex(ValueError, 'Existing'):
                preservation.preserve(src, dst, 'trusted')


if __name__ == '__main__':
    unittest.main()
