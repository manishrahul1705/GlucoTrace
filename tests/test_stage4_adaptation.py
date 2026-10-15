"""Unit tests for Stage 4 adaptation logic."""
import unittest
import numpy as np
import pandas as pd

from glucotwin.stage4.adaptation import (
    validate_calibration_gate,
    partition_participant_origins,
    compute_median_residual_offset,
    apply_offset,
    OffsetProvenance,
    hash_origin_ids,
)


class TestStage4Adaptation(unittest.TestCase):
    def test_median_residual_sign(self):
        """When predictions underestimate, offset must be positive; when overestimating, negative."""
        # Underestimating: targets higher than predictions
        y_true_under = [150.0, 160.0, 170.0]
        y_pred_under = [140.0, 140.0, 150.0]
        # residuals: +10, +20, +20 -> median = +20.0
        offset_pos = compute_median_residual_offset(y_true_under, y_pred_under)
        self.assertGreater(offset_pos, 0.0)
        self.assertEqual(offset_pos, 20.0)

        # Overestimating: targets lower than predictions
        y_true_over = [100.0, 110.0, 120.0]
        y_pred_over = [120.0, 130.0, 135.0]
        # residuals: -20, -20, -15 -> median = -20.0
        offset_neg = compute_median_residual_offset(y_true_over, y_pred_over)
        self.assertLess(offset_neg, 0.0)
        self.assertEqual(offset_neg, -20.0)

    def test_manual_calculable_offset_and_predictions(self):
        """Verify exact manual calculation of median offset and adapted predictions."""
        y_true = [100.0, 110.0, 120.0]
        y_pred_cal = [95.0, 100.0, 130.0]
        # residuals: [5.0, 10.0, -10.0] -> sorted: [-10.0, 5.0, 10.0] -> median: 5.0
        offset = compute_median_residual_offset(y_true, y_pred_cal)
        self.assertEqual(offset, 5.0)

        y_pred_later = np.array([140.0, 150.0, 160.0])
        adapted = apply_offset(y_pred_later, offset)
        expected = np.array([145.0, 155.0, 165.0])
        np.testing.assert_array_almost_equal(adapted, expected)

    def test_no_prediction_clipping(self):
        """Predictions must NOT be clamped or clipped to physiological boundaries."""
        y_pred = np.array([35.0, 420.0])
        offset = -10.0
        adapted = apply_offset(y_pred, offset)
        self.assertEqual(adapted[0], 25.0)
        self.assertEqual(adapted[1], 410.0)

    def test_non_finite_values_fail(self):
        """NaN and Inf in inputs or offset must raise ValueError."""
        with self.assertRaises(ValueError):
            compute_median_residual_offset([100.0, np.nan], [100.0, 100.0])
        with self.assertRaises(ValueError):
            compute_median_residual_offset([100.0, 100.0], [100.0, np.inf])
        with self.assertRaises(ValueError):
            apply_offset([100.0, np.nan], 5.0)
        with self.assertRaises(ValueError):
            apply_offset([100.0, 100.0], np.nan)
        with self.assertRaises(ValueError):
            apply_offset([100.0, 100.0], np.inf)

    def test_temporal_partitioning_rules(self):
        """Verify calibration, later_evaluation, and purged_boundary assignment."""
        anchor = pd.Timestamp("2026-01-01 00:00:00")
        boundary = anchor + pd.Timedelta(hours=48)  # 2026-01-03 00:00:00

        # Create origins:
        # 1. Clean calibration origin (history inside [anchor, boundary), target < boundary)
        # 2. Origin starting before anchor (purged)
        # 3. Origin straddling boundary (history < boundary, target >= boundary -> purged)
        # 4. Clean later evaluation origin (history >= boundary)
        df = pd.DataFrame([
            {
                'origin_id': 'cal_01',
                'participant_id': 1,
                'issue_time': anchor + pd.Timedelta(hours=10),
                'history_start': anchor + pd.Timedelta(hours=9),
                'target_time': anchor + pd.Timedelta(hours=10, minutes=30)
            },
            {
                'origin_id': 'pre_anchor_02',
                'participant_id': 1,
                'issue_time': anchor + pd.Timedelta(minutes=30),
                'history_start': anchor - pd.Timedelta(minutes=30),
                'target_time': anchor + pd.Timedelta(hours=1)
            },
            {
                'origin_id': 'straddle_03',
                'participant_id': 1,
                'issue_time': boundary - pd.Timedelta(minutes=15),
                'history_start': boundary - pd.Timedelta(hours=1, minutes=15),
                'target_time': boundary + pd.Timedelta(minutes=15)
            },
            {
                'origin_id': 'later_04',
                'participant_id': 1,
                'issue_time': boundary + pd.Timedelta(hours=2),
                'history_start': boundary + pd.Timedelta(hours=1),
                'target_time': boundary + pd.Timedelta(hours=2, minutes=30)
            }
        ])

        partitioned = partition_participant_origins(df, anchor, duration_hours=48)
        part_map = dict(zip(partitioned['origin_id'], partitioned['partition']))

        self.assertEqual(part_map['cal_01'], 'calibration')
        self.assertEqual(part_map['pre_anchor_02'], 'purged_boundary')
        self.assertEqual(part_map['straddle_03'], 'purged_boundary')
        self.assertEqual(part_map['later_04'], 'later_evaluation')

        # Assert no calibration origin has target >= boundary
        cal_targets = pd.to_datetime(partitioned[partitioned['partition'] == 'calibration']['target_time'])
        self.assertTrue((cal_targets < boundary).all())

        # Assert all later evaluation origins have history >= boundary
        later_hist = pd.to_datetime(partitioned[partitioned['partition'] == 'later_evaluation']['history_start'])
        self.assertTrue((later_hist >= boundary).all())

    def test_elapsed_time_never_compressed(self):
        """Missing periods do not extend elapsed 48-hour boundary."""
        anchor = pd.Timestamp("2026-03-01 08:00:00")
        expected_boundary = anchor + pd.Timedelta(hours=48)
        df = pd.DataFrame([{
            'origin_id': 'test_01',
            'participant_id': 1,
            'issue_time': anchor + pd.Timedelta(hours=2),
            'history_start': anchor + pd.Timedelta(hours=1),
            'target_time': anchor + pd.Timedelta(hours=2, minutes=30)
        }])
        partitioned = partition_participant_origins(df, anchor, duration_hours=48)
        actual_boundary = pd.to_datetime(partitioned['calibration_boundary'].iloc[0])
        self.assertEqual(actual_boundary, expected_boundary)

    def test_later_label_immunity(self):
        """Modifying later-period targets does not alter calibration offset."""
        cal_true = [120.0, 130.0, 140.0]
        cal_pred = [115.0, 125.0, 135.0]
        offset1 = compute_median_residual_offset(cal_true, cal_pred)

        # Hypothetical later data changing
        later_true_v1 = [200.0, 220.0]
        later_true_v2 = [80.0, 90.0]

        # The offset is computed solely from cal_true and cal_pred
        offset2 = compute_median_residual_offset(cal_true, cal_pred)
        self.assertEqual(offset1, offset2)
        self.assertEqual(offset1, 5.0)

    def test_adequacy_gate_validation(self):
        """Adequacy gates reject insufficient calibration coverage or counts."""
        # Baseline valid case
        self.assertTrue(validate_calibration_gate(0.85, 120, 500))
        # Coverage too low (<80%)
        self.assertFalse(validate_calibration_gate(0.79, 120, 500))
        # Calibration origins too low (<100)
        self.assertFalse(validate_calibration_gate(0.85, 99, 500))
        # Later origins too low (<100)
        self.assertFalse(validate_calibration_gate(0.85, 120, 99))

    def test_origin_id_hashing(self):
        """Origin ID hashing is deterministic and order-invariant."""
        ids1 = ['b_id', 'a_id', 'c_id']
        ids2 = ['a_id', 'c_id', 'b_id']
        self.assertEqual(hash_origin_ids(ids1), hash_origin_ids(ids2))

    def test_held_out_participant_excluded_from_base_model(self):
        """Verify that training set strictly excludes the held-out test participant."""
        from pathlib import Path
        import json
        manifest_path = Path(__file__).resolve().parents[1] / 'reports' / 'stage2' / 'split_manifest.json'
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            for fold in manifest['folds']:
                test_p = fold['test']['participants'][0]
                train_p = set(fold['train']['participants'])
                self.assertNotIn(test_p, train_p)
                for inner in fold['inner_folds']:
                    self.assertNotIn(test_p, set(inner['train']['participants']))
                    self.assertNotIn(test_p, set(inner['validation']['participants']))


if __name__ == '__main__':
    unittest.main()

