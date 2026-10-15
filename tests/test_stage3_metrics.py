"""Unit tests for Stage 3 metric calculations, full floating-point precision, and bootstrap."""
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

from glucotwin.stage3.metrics import (
    compute_point_metrics,
    compute_persistence_predictions,
    compute_trend_predictions,
    compute_per_participant_metrics,
    compute_aggregate_metrics,
    compute_paired_participant_bootstrap,
    VALID_GLUCOSE_RANGE,
)


class Stage3MetricsRealFunctionTests(unittest.TestCase):

    def test_point_metrics_formulas_and_full_precision(self):
        """Verify MAE, RMSE, MSE formulas retain full float64 precision without premature rounding."""
        y_true = np.array([100.0, 150.0, 200.0, 120.0], dtype=np.float64)
        y_pred = np.array([110.0, 140.0, 210.0, 120.0], dtype=np.float64)

        metrics = compute_point_metrics(y_true, y_pred)
        self.assertAlmostEqual(metrics['mae'], 7.5, places=10)
        self.assertAlmostEqual(metrics['rmse'], np.sqrt(75.0), places=10)
        self.assertAlmostEqual(metrics['mean_signed_error'], 2.5, places=10)
        self.assertEqual(metrics['non_finite_count'], 0)
        self.assertEqual(metrics['out_of_range_count'], 0)

        # Full precision check: 1/3 residual
        y_true_fp = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        y_pred_fp = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        fp_res = compute_point_metrics(y_true_fp, y_pred_fp)
        # Should not be rounded to 4 decimals (0.3333)
        self.assertNotEqual(fp_res['mae'], 0.3333)
        self.assertAlmostEqual(fp_res['mae'], 1.0 / 3.0, places=14)

    def test_persistence_and_trend_baselines(self):
        """Baselines match deterministic formulas."""
        df_sensor = pd.DataFrame({
            'glucose_lag_0m': [100.0, 180.0],
            'glucose_slope_15m': [0.5, -1.0]
        })
        pers = compute_persistence_predictions(df_sensor)
        trend = compute_trend_predictions(df_sensor)

        np.testing.assert_array_equal(pers, [100.0, 180.0])
        np.testing.assert_array_equal(trend, [115.0, 150.0])

    def test_window_weighted_vs_equal_person_metrics(self):
        """Aggregate metrics properly distinguish primary equal-person and secondary window-weighted."""
        pred_data = {
            'participant_id': [1]*10 + [2]*90,
            'target_mg_dl': [100.0]*100,
            'persistence': [110.0]*10 + [120.0]*90,  # pers error: p1=10, p2=20 -> eq=15, ww=19
            'trend': [105.0]*10 + [115.0]*90,        # trend error: p1=5, p2=15 -> eq=10, ww=14
            'model_a': [106.0]*10 + [114.0]*90       # model_a error: p1=6, p2=14 -> eq=10, ww=13.2
        }
        df_preds = pd.DataFrame(pred_data)
        methods = ['persistence', 'trend', 'model_a']
        per_person = compute_per_participant_metrics(df_preds, methods, [1, 2])
        agg = compute_aggregate_metrics(per_person, df_preds, methods)

        m_a_agg = agg[agg['method'] == 'model_a'].iloc[0]
        self.assertAlmostEqual(m_a_agg['primary_equal_person_mae_mg_dl'], 10.0, places=10)
        self.assertAlmostEqual(m_a_agg['window_weighted_mae_mg_dl'], 13.2, places=10)

        # Skill relative to persistence: (15 - 10) / 15 * 100% = 33.333%
        self.assertAlmostEqual(m_a_agg['persistence_relative_skill_pct'], 100.0 / 3.0, places=4)

    def test_paired_bootstrap_sign_convention_and_reproducibility(self):
        """Paired bootstrap follows sign convention (delta = combined - sensor) and fixed seed."""
        # Setup synthetic per-person df where combined is better by 2.0 mg/dL for all participants
        records = []
        for pid in range(14):
            records.append({'participant_id': pid, 'method': 'ridge_sensor_only', 'mae_mg_dl': 20.0, 'rmse_mg_dl': 25.0})
            records.append({'participant_id': pid, 'method': 'ridge_sensor_plus_baseline', 'mae_mg_dl': 18.0, 'rmse_mg_dl': 23.0})
        df_pp = pd.DataFrame(records)

        boot = compute_paired_participant_bootstrap(df_pp, 'ridge', seed=42, n_resamples=500)
        self.assertEqual(boot['seed'], 42)
        self.assertEqual(boot['resamples'], 500)
        self.assertAlmostEqual(boot['mean_delta_mae'], -2.0, places=10)
        self.assertAlmostEqual(boot['mae_95_ci'][0], -2.0, places=10)
        self.assertAlmostEqual(boot['mae_95_ci'][1], -2.0, places=10)
        self.assertEqual(boot['participants_improved_mae'], 14)
        self.assertEqual(boot['participants_worsened_mae'], 0)

    def test_out_of_range_and_non_finite_tracking(self):
        """Point metrics count values outside [40, 400] and non-finite values without clipping."""
        y_true = np.array([100.0, 100.0, 100.0])
        y_pred = np.array([30.0, 150.0, 450.0])
        metrics = compute_point_metrics(y_true, y_pred)
        self.assertEqual(metrics['out_of_range_count'], 2)
        self.assertEqual(metrics['non_finite_count'], 0)

        y_pred_nan = np.array([30.0, np.nan, 450.0])
        metrics_nan = compute_point_metrics(y_true, y_pred_nan)
        self.assertEqual(metrics_nan['non_finite_count'], 1)


if __name__ == '__main__':
    unittest.main()
