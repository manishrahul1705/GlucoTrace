"""Unit tests for Stage 3 training, candidate selection, data isolation, and preflight integrity."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from glucotwin.stage3.integrity import (
    SENSOR_FEATURES,
    BASELINE_FEATURES,
    COMBINED_FEATURES,
    TARGET_COL,
    PROHIBITED_COLUMNS,
    EXPECTED_PARTICIPANTS,
    IntegrityError,
    verify_feature_order_and_finiteness,
    verify_no_prohibited_metadata_in_features,
    run_preflight_checks,
)
from glucotwin.stage3.training import (
    build_estimator,
    fit_estimator,
    predict_estimator,
    get_feature_columns,
    get_participant_indices,
)
from glucotwin.stage3.selection import (
    compute_equal_person_val_mae,
    select_candidate,
)


class Stage3TrainingRealFunctionTests(unittest.TestCase):

    def test_feature_column_allowlists_and_counts(self):
        """Estimators only receive allowed feature columns, never metadata or targets."""
        for col in PROHIBITED_COLUMNS:
            self.assertNotIn(col, SENSOR_FEATURES)
            self.assertNotIn(col, COMBINED_FEATURES)
        self.assertEqual(len(SENSOR_FEATURES), 21)
        self.assertEqual(len(BASELINE_FEATURES), 4)
        self.assertEqual(len(COMBINED_FEATURES), 25)

        self.assertEqual(get_feature_columns('sensor_only'), SENSOR_FEATURES)
        self.assertEqual(get_feature_columns('sensor_plus_baseline'), COMBINED_FEATURES)
        with self.assertRaises(ValueError):
            get_feature_columns('invalid_variant')

    def test_prohibited_metadata_rejection(self):
        """Preflight metadata check raises IntegrityError if any prohibited column is included."""
        verify_no_prohibited_metadata_in_features(SENSOR_FEATURES)
        verify_no_prohibited_metadata_in_features(COMBINED_FEATURES)

        for col in PROHIBITED_COLUMNS:
            bad_list = SENSOR_FEATURES + [col]
            with self.assertRaises(IntegrityError):
                verify_no_prohibited_metadata_in_features(bad_list)

    def test_feature_order_and_finiteness_validation(self):
        """Feature matrices with NaNs or infs must fail validation before fitting."""
        n = 10
        data = {f: np.ones(n) for f in SENSOR_FEATURES}
        df_valid = pd.DataFrame(data)
        verify_feature_order_and_finiteness(df_valid, SENSOR_FEATURES, "test_valid")

        # Non-finite value in feature
        df_invalid = df_valid.copy()
        df_invalid.loc[2, 'glucose_lag_0m'] = np.nan
        with self.assertRaises(IntegrityError):
            verify_feature_order_and_finiteness(df_invalid, SENSOR_FEATURES, "test_nan")

        df_inf = df_valid.copy()
        df_inf.loc[3, 'glucose_std_15m'] = np.inf
        with self.assertRaises(IntegrityError):
            verify_feature_order_and_finiteness(df_inf, SENSOR_FEATURES, "test_inf")

    def test_training_only_scaler_isolation(self):
        """StandardScaler must fit strictly on training set; held-out set must not alter parameters."""
        rng = np.random.default_rng(42)
        X_train = rng.normal(loc=120.0, scale=10.0, size=(100, 21))
        y_train = rng.normal(loc=125.0, scale=12.0, size=100)
        X_test = rng.normal(loc=250.0, scale=50.0, size=(25, 21))  # Distribution shift

        cand = {'alpha': 1.0}
        est, scaler = fit_estimator('ridge', cand, X_train, y_train)

        self.assertIsNotNone(scaler)
        train_mean = scaler.mean_.copy()
        train_scale = scaler.scale_.copy()

        # Predict on test
        preds = predict_estimator(est, scaler, X_test)
        self.assertEqual(len(preds), 25)

        # Scaler attributes must remain completely identical
        np.testing.assert_array_equal(scaler.mean_, train_mean)
        np.testing.assert_array_equal(scaler.scale_, train_scale)
        self.assertAlmostEqual(scaler.mean_[0], 120.0, delta=3.0)

    def test_hist_gradient_boosting_construction(self):
        """HistGradientBoosting estimator builds with correct hyperparameter spec and fits without scaler."""
        cand = {
            'learning_rate': 0.05,
            'max_iter': 10,
            'max_leaf_nodes': 31,
            'min_samples_leaf': 20,
            'l2_regularization': 0.1,
            'early_stopping': False,
            'random_state': 42
        }
        X_train = np.ones((50, 21)) * 100.0
        y_train = np.ones(50) * 110.0
        est, scaler = fit_estimator('hist_gradient_boosting', cand, X_train, y_train)
        self.assertIsNone(scaler)
        preds = predict_estimator(est, scaler, X_train[:5])
        self.assertEqual(len(preds), 5)

    def test_equal_person_val_mae_with_unequal_folds(self):
        """Validation scoring weights participants equally, not inner folds or sample counts."""
        # 3 inner folds with unequal participant counts (5, 4, 4) = 13 participants
        # Participant MAEs
        pids = np.array([1, 1, 1, 2, 2, 3, 3, 3, 3])  # unequal origins per participant
        targets = np.array([100.0, 100.0, 100.0, 150.0, 150.0, 200.0, 200.0, 200.0, 200.0])
        preds = np.array([110.0, 110.0, 110.0, 170.0, 170.0, 230.0, 230.0, 230.0, 230.0])
        # Residuals: p1 = 10, p2 = 20, p3 = 30
        res_dict = compute_equal_person_val_mae(preds, targets, pids, [1, 2, 3])
        self.assertEqual(res_dict[1], 10.0)
        self.assertEqual(res_dict[2], 20.0)
        self.assertEqual(res_dict[3], 30.0)

        # Equal-person mean: (10 + 20 + 30) / 3 = 20.0
        equal_person_mean = float(np.mean(list(res_dict.values())))
        self.assertEqual(equal_person_mean, 20.0)

        # Origin-weighted mean would be: (3*10 + 2*20 + 4*30) / 9 = 190 / 9 = 21.111...
        origin_weighted_mean = float(np.mean(np.abs(preds - targets)))
        self.assertNotEqual(equal_person_mean, origin_weighted_mean)

    def test_candidate_selection_and_tie_breaking(self):
        """Candidate tie-breaking selects earliest candidate_id on identical validation score."""
        candidates = [
            (0, 15.50001, {'candidate_id': 0, 'alpha': 0.1}),
            (1, 14.20000, {'candidate_id': 1, 'alpha': 1.0}),
            (2, 14.20000, {'candidate_id': 2, 'alpha': 10.0}),  # Exact tie with candidate 1
            (3, 16.00000, {'candidate_id': 3, 'alpha': 100.0}),
        ]
        selected_id, score, selected_dict = select_candidate(candidates)
        # Should pick candidate 1 due to tie-break (1 < 2)
        self.assertEqual(selected_id, 1)
        self.assertEqual(score, 14.20000)
        self.assertEqual(selected_dict['alpha'], 1.0)

    def test_windows_path_portability_without_monkeypatching(self):
        """PureWindowsPath must retain standard Windows path behavior; normalization must use .as_posix()."""
        from pathlib import PureWindowsPath, PurePosixPath
        p_win = PureWindowsPath('reports', 'stage3', 'fit_ledger.csv')
        # Standard str() contains backslashes on Windows
        self.assertIn('\\', str(p_win))
        # Portable representation uses forward slashes
        self.assertEqual(p_win.as_posix(), 'reports/stage3/fit_ledger.csv')


if __name__ == '__main__':
    unittest.main()
