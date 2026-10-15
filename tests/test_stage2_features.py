import unittest
from stage2_fixture import *
from glucotwin.features import features_at,paired_features,SENSOR_FEATURES,BASELINE_FEATURES,persistence_formula,trend_formula
from glucotwin.preprocessing import construct_origins
class FeatureTests(unittest.TestCase):
 def test_manually_calculated_endpoints_std_and_slopes(self):
  d=observed(100,100+2*np.arange(100));f=features_at(d,d.index[60])
  for m in range(0,61,5):self.assertEqual(f[f'glucose_lag_{m}m'],220-2*m)
  self.assertEqual(f.glucose_mean_15m,205);self.assertEqual(f.glucose_mean_30m,190);self.assertEqual(f.glucose_mean_60m,160)
  self.assertAlmostEqual(f.glucose_std_15m,np.sqrt(85),places=10);self.assertAlmostEqual(f.glucose_slope_15m,2,places=10);self.assertAlmostEqual(f.glucose_slope_30m,2,places=10)
 def test_future_mutation_pipeline_only_not_source_preprocessing(self):
  """Proves only our builder's time boundary, not the release's interpolation causality."""
  d=observed(150,100+.2*np.arange(150));f=features_at(d,d.index[60]);mut=d.copy();mut.loc[mut.index>d.index[60],'glucose_mg_dl']=390
  pd.testing.assert_series_equal(f,features_at(mut,mut.index[60]))
 def test_missing_required_history_cell_excludes(self):
  d=observed();d.loc[d.index[30],'valid']=False;o,_=construct_origins(d,baseline());self.assertFalse(o.eligible.iloc[60]);self.assertIn('history_missing_or_invalid',o.exclusion_reason.iloc[60])
 def test_exact_target_no_nearest_substitution(self):
  raw=raw_fixture();raw=raw.drop(index=90);d=prepare_observations(raw,1,'s','p');o,_=construct_origins(d,baseline());self.assertFalse(o.eligible.loc[pd.Timestamp('2020-01-01 01:00')]);self.assertTrue(pd.isna(o.target_mg_dl.loc[pd.Timestamp('2020-01-01 01:00')]))
 def test_primary_grid_anchored_first_parsed_not_valid(self):
  d=observed();d.loc[d.index[:3],'valid']=False;o,_=construct_origins(d,baseline());self.assertTrue(o.is_primary_grid.iloc[0]);self.assertTrue(o.is_primary_grid.iloc[65]);self.assertFalse(o.is_primary_grid.iloc[63])
 def test_variants_share_ids_and_sensor_values(self):
  d=observed();o,_=construct_origins(d,baseline());s,c=paired_features(d,o,baseline());self.assertTrue(s.origin_id.equals(c.origin_id));pd.testing.assert_frame_equal(s,c[s.columns]);self.assertEqual(len(SENSOR_FEATURES),21);self.assertEqual(len(BASELINE_FEATURES),4);self.assertNotIn('participant_id',SENSOR_FEATURES+BASELINE_FEATURES)
 def test_baseline_attrition_applies_identically(self):
  d=observed();b=baseline(np.nan);o,_=construct_origins(d,b);s,c=paired_features(d,o,b);self.assertEqual((len(s),len(c)),(0,0))
 def test_baseline_formulas_only_on_synthetic_fixture(self):
  a=100+2*np.arange(16);self.assertEqual(persistence_formula(a),130);self.assertAlmostEqual(trend_formula(a),190)
