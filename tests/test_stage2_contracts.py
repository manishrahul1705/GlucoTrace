import unittest,copy
from stage2_fixture import *
from glucotwin.contracts import ContractError,require_join,access_history,baseline_contract
from glucotwin.preprocessing import construct_origins
class ContractTests(unittest.TestCase):
 def test_duplicate_and_nonmonotonic_timestamps_rejected(self):
  for stamps in [['2020-01-01','2020-01-01'],['2020-01-01 00:01','2020-01-01 00:00']]:
   with self.subTest(stamps=stamps),self.assertRaises(ContractError):prepare_observations(pd.DataFrame({'Timestamp':stamps,'Dexcom GL':[100,100]}),1,'s','p')
 def test_parse_and_off_grid_rejected(self):
  for stamps in [['bad'],['2020-01-01 00:00:00','2020-01-01 00:00:30']]:
   with self.subTest(stamps=stamps),self.assertRaises(ContractError):prepare_observations(pd.DataFrame({'Timestamp':stamps,'Dexcom GL':[100]*len(stamps)}),1,'s','p')
 def test_nonfinite_and_out_of_range_glucose(self):
  for x in [np.nan,np.inf,-np.inf,39,401,'bad']:
   with self.subTest(value=x):
    raw=raw_fixture();raw['Dexcom GL']=raw['Dexcom GL'].astype(object);raw.loc[30,'Dexcom GL']=x;d=prepare_observations(raw,1,'s','p');o,_=construct_origins(d,baseline());self.assertFalse(o.eligible.iloc[60]);self.assertFalse(d.valid.iloc[30])
 def test_valid_range_inclusive(self):
  d=observed(2,[40.,400.]);self.assertTrue(d.valid.all())
 def test_join_duplicates_and_missing_rejected(self):
  with self.assertRaises(ContractError):require_join([1,1],{1:baseline()})
  with self.assertRaises(ContractError):require_join([1,2],{1:baseline()})
 def test_baseline_duplicate_or_missing_key_rejected(self):
  for ids in [[1,1],[1,None]]:
   b=pd.DataFrame({'subject':ids,'Age':[50,50],'BMI':[30,30],'A1c PDL (Lab)':[7,7],'Fasting GLU - PDL (Lab)':[150,150]})
   with self.assertRaises(ContractError):baseline_contract(b,config(),'s','p')
 def test_exact_units_and_columns_checked(self):
  b=pd.DataFrame({'subject':[1],'Age':[50],'BMI':[30],'A1c PDL (Lab)':[7],'Fasting GLU - PDL (Lab)':[150]});c=config();c['baseline']['units']['hba1c']='mmol/mol'
  with self.assertRaises(ContractError):baseline_contract(b,c,'s','p')
  with self.assertRaises(ContractError):baseline_contract(b.rename(columns={'Age':'age'}),config(),'s','p')
 def test_invalid_baseline_not_clipped(self):
  b=baseline(999);self.assertEqual(b.bmi,999);self.assertFalse(b.baseline_valid)
 def test_unknown_availability_stays_unknown_and_fails_closed(self):
  d=observed();self.assertTrue(d.actual_available_at.isna().all())
  self.assertEqual(len(access_history(d,d.index[60],mode='retrospective')),61)
  with self.assertRaises(ContractError):access_history(d,d.index[60],mode='causal')
 def test_causal_requires_verified_not_later(self):
  d=observed();d['actual_available_at']=d.index;d['availability_verified']=True
  self.assertEqual(len(access_history(d,d.index[60],mode='causal')),61)
  d.loc[d.index[60],'actual_available_at']=d.index[61]
  with self.assertRaises(ContractError):access_history(d,d.index[60],mode='causal')
