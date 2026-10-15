import unittest
import numpy as np
import pandas as pd
from glucotwin.stage4.evaluation import reconcile_glycemic_mae
from glucotwin.stage4.adaptation import compute_median_residual_offset, apply_offset


class TestReconciliation(unittest.TestCase):
    def test_unequal_slice_mix_endpoints_empty_and_delta(self):
        df = pd.DataFrame(dict(participant_id=[1, 1, 1, 2],
                               target_mg_dl=[70., 180., 200., 100.],
                               un=[72., 184., 210., 120.], ad=[71., 183., 209., 119.]))
        details, people, agg = reconcile_glycemic_mae(df, ['un', 'ad'])
        self.assertTrue(details.query("slice_name == 'below70'").slice_mae.isna().all())
        self.assertEqual(details.query("slice_name == 'below70'").weighted_contribution.sum(), 0)
        self.assertEqual(details.query("participant_id == 1 and method == 'un' and slice_name == '70to180'").n_origins.iloc[0], 2)
        np.testing.assert_allclose(people.direct_mae, people.reconstructed_mae)
        a = agg.set_index('method')
        self.assertAlmostEqual(a.loc['un', 'direct_mae'], (16/3 + 20)/2)
        self.assertAlmostEqual(a.loc['ad', 'reconstructed_mae']-a.loc['un', 'reconstructed_mae'], -1)

    def test_invalid_inputs(self):
        for df in [pd.DataFrame(columns=['participant_id', 'target_mg_dl', 'm']),
                   pd.DataFrame(dict(participant_id=[1], target_mg_dl=[np.nan], m=[1]))]:
            with self.assertRaises(ValueError):
                reconcile_glycemic_mae(df, ['m'])

    def test_offset_sign_and_later_signed_error_identity(self):
        offset = compute_median_residual_offset([100, 100, 100], [110, 110, 80])
        self.assertEqual(offset, -10)
        target, base = np.array([200., 100.]), np.array([190., 110.])
        adapted = apply_offset(base, offset)
        np.testing.assert_allclose(adapted-target, base-target+offset)
        self.assertAlmostEqual(np.mean(adapted-target), np.mean(base-target)+offset)
