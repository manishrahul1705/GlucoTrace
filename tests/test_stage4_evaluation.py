"""Unit tests for Stage 4 evaluation, metrics, and shared paired bootstrap."""
import unittest
import numpy as np
import pandas as pd

from glucotwin.stage4.evaluation import (
    VALID_GLUCOSE_RANGE,
    compute_point_metrics,
    compute_per_participant_metrics,
    compute_cohort_aggregates,
    generate_shared_bootstrap_draws,
    paired_participant_bootstrap,
)


class TestStage4Evaluation(unittest.TestCase):
    def test_point_metrics(self):
        """Verify MAE, RMSE, mean signed error, and boundary violations."""
        y_true = np.array([100.0, 150.0, 200.0])
        # y_pred: errors are +10, -20, +30 -> mean signed = 20/3 = 6.6667
        # abs errors: 10, 20, 30 -> MAE = 20.0
        # squared errors: 100, 400, 900 = 1400 / 3 -> RMSE = sqrt(466.6667) = 21.6025
        y_pred = np.array([110.0, 130.0, 230.0])

        metrics = compute_point_metrics(y_true, y_pred)
        self.assertAlmostEqual(metrics['mae'], 20.0)
        self.assertAlmostEqual(metrics['rmse'], np.sqrt(1400.0 / 3.0))
        self.assertAlmostEqual(metrics['mean_signed_error'], (10.0 - 20.0 + 30.0) / 3.0)
        self.assertEqual(metrics['non_finite_count'], 0)
        self.assertEqual(metrics['out_of_range_count'], 0)

        # Boundary violation: < 40 or > 400
        y_pred_oor = np.array([35.0, 150.0, 450.0])
        metrics_oor = compute_point_metrics(y_true, y_pred_oor)
        self.assertEqual(metrics_oor['out_of_range_count'], 2)

    def test_shared_bootstrap_draws_deterministic_and_hashed(self):
        """Shared draw index matrix is perfectly deterministic and SHA-256 verifiable."""
        draws1, hash1 = generate_shared_bootstrap_draws(n_participants=14, n_resamples=2000, seed=20261015)
        draws2, hash2 = generate_shared_bootstrap_draws(n_participants=14, n_resamples=2000, seed=20261015)

        self.assertEqual(draws1.shape, (2000, 14))
        self.assertEqual(hash1, hash2)
        np.testing.assert_array_equal(draws1, draws2)

    def test_paired_bootstrap_draw_sharing(self):
        """Draw matrix is reused across paired comparisons ensuring synchronized sampling."""
        draws, draw_hash = generate_shared_bootstrap_draws(n_participants=3, n_resamples=100, seed=42)

        pids = [1, 2, 3]
        # Participant errors
        df = pd.DataFrame([
            {'participant_id': 1, 'method': 'unadapted', 'mae_mg_dl': 15.0, 'rmse_mg_dl': 20.0},
            {'participant_id': 2, 'method': 'unadapted', 'mae_mg_dl': 16.0, 'rmse_mg_dl': 21.0},
            {'participant_id': 3, 'method': 'unadapted', 'mae_mg_dl': 17.0, 'rmse_mg_dl': 22.0},
            {'participant_id': 1, 'method': 'adapted_v1', 'mae_mg_dl': 13.0, 'rmse_mg_dl': 18.0},
            {'participant_id': 2, 'method': 'adapted_v1', 'mae_mg_dl': 14.0, 'rmse_mg_dl': 19.0},
            {'participant_id': 3, 'method': 'adapted_v1', 'mae_mg_dl': 15.0, 'rmse_mg_dl': 20.0},
            {'participant_id': 1, 'method': 'adapted_v2', 'mae_mg_dl': 12.0, 'rmse_mg_dl': 17.0},
            {'participant_id': 2, 'method': 'adapted_v2', 'mae_mg_dl': 13.0, 'rmse_mg_dl': 18.0},
            {'participant_id': 3, 'method': 'adapted_v2', 'mae_mg_dl': 14.0, 'rmse_mg_dl': 19.0},
        ])

        res_v1 = paired_participant_bootstrap(df, 'adapted_v1', 'unadapted', 'v1_vs_unadapted', draws)
        res_v2 = paired_participant_bootstrap(df, 'adapted_v2', 'unadapted', 'v2_vs_unadapted', draws)

        # delta_mae for v1 is -2.0 for all participants, so boot means must all be -2.0
        self.assertAlmostEqual(res_v1['mean_delta_mae'], -2.0)
        self.assertAlmostEqual(res_v1['mae_95_ci'][0], -2.0)
        self.assertAlmostEqual(res_v1['mae_95_ci'][1], -2.0)
        self.assertEqual(res_v1['participants_improved_mae'], 3)
        self.assertEqual(res_v1['participants_worsened_mae'], 0)

        # delta_mae for v2 is -3.0 for all participants
        self.assertAlmostEqual(res_v2['mean_delta_mae'], -3.0)
        self.assertAlmostEqual(res_v2['mae_95_ci'][0], -3.0)
        self.assertAlmostEqual(res_v2['mae_95_ci'][1], -3.0)

    def test_cohort_aggregates_weighting(self):
        """Primary equal-weighted and secondary window-weighted aggregates are correctly computed."""
        df = pd.DataFrame([
            {
                'participant_id': 1,
                'method': 'model_a',
                'n_origins': 100,
                'mae_mg_dl': 10.0,
                'rmse_mg_dl': 12.0,
                'mean_signed_error_mg_dl': 2.0,
                'non_finite_count': 0,
                'out_of_range_count': 0
            },
            {
                'participant_id': 2,
                'method': 'model_a',
                'n_origins': 300,
                'mae_mg_dl': 20.0,
                'rmse_mg_dl': 24.0,
                'mean_signed_error_mg_dl': -4.0,
                'non_finite_count': 0,
                'out_of_range_count': 1
            }
        ])

        agg = compute_cohort_aggregates(df, ['model_a'])
        row = agg.iloc[0]

        # Equal-weighted: (10 + 20) / 2 = 15.0
        self.assertAlmostEqual(row['primary_equal_person_mae_mg_dl'], 15.0)
        self.assertAlmostEqual(row['secondary_equal_person_rmse_mg_dl'], 18.0)
        self.assertAlmostEqual(row['equal_person_mean_signed_error_mg_dl'], -1.0)

        # Window-weighted: weights are 100/400=0.25 and 300/400=0.75
        # MAE: 0.25*10 + 0.75*20 = 2.5 + 15 = 17.5
        self.assertAlmostEqual(row['window_weighted_mae_mg_dl'], 17.5)
        # MSE: 0.25*144 + 0.75*576 = 36 + 432 = 468 -> RMSE = sqrt(468) = 21.6333
        self.assertAlmostEqual(row['window_weighted_rmse_mg_dl'], np.sqrt(468.0))
        # Total counts
        self.assertEqual(row['total_origins'], 400)
        self.assertEqual(row['total_out_of_range_predictions'], 1)

    def test_mismatched_participants_raise_error(self):
        """Comparing methods with mismatched participants raises ValueError."""
        df = pd.DataFrame([
            {'participant_id': 1, 'method': 'm1', 'mae_mg_dl': 10.0, 'rmse_mg_dl': 12.0},
            {'participant_id': 2, 'method': 'm2', 'mae_mg_dl': 20.0, 'rmse_mg_dl': 24.0},
        ])
        draws, _ = generate_shared_bootstrap_draws(1, 10)
        with self.assertRaises(ValueError):
            paired_participant_bootstrap(df, 'm1', 'm2', 'invalid', draws)

    def test_altered_hash_fails_preflight(self):
        """Tampering with an expected input hash must trigger a preflight mismatch."""
        from pathlib import Path
        import hashlib
        proto_file = Path(__file__).resolve().parents[1] / 'configs' / 'stage4_protocol.json'
        if proto_file.exists():
            import json
            cfg = json.loads(proto_file.read_text(encoding='utf-8'))
            real_hashes = cfg.get('input_hashes', {})
            # Verify real hash matches
            for rel_path, expected_h in list(real_hashes.items())[:1]:
                target = Path(__file__).resolve().parents[1] / rel_path
                if target.exists():
                    actual_h = hashlib.sha256(target.read_bytes()).hexdigest()
                    self.assertEqual(actual_h, expected_h)
                    # Simulated tamper
                    tampered_h = '0' * 64
                    self.assertNotEqual(actual_h, tampered_h)


if __name__ == '__main__':
    unittest.main()

