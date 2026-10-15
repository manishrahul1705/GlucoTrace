import unittest
from stage2_fixture import *
from glucotwin.labels import event_labels,future_any_crossing
class LabelTests(unittest.TestCase):
 def event(self,n=160,length=15,start=80):
  y=np.full(n,100.);y[start:min(n,start+length)]=200.;return observed(n,y)
 def test_onset_at_horizon_requires_t_plus44(self):
  d=self.event();l,e=event_labels(d,180);row=l.iloc[50];self.assertEqual(row.event_label,1);self.assertEqual(row.confirmed_onset_time,d.index[80]);self.assertEqual(row.actual_decision_information_end,d.index[94]);self.assertEqual(row.max_label_information_end,d.index[94]);self.assertEqual(row.label_information_start,d.index[21]);self.assertEqual(len(e),1)
 def test_14_cells_not_sustained_15_cells_are(self):
  a,_=event_labels(self.event(length=14),180);b,_=event_labels(self.event(length=15),180);self.assertEqual(a.event_label.iloc[50],0);self.assertEqual(b.event_label.iloc[50],1)
 def test_recovery_boundary_29_vs30_cells(self):
  d=observed(160);d.loc[d.index[:51],'glucose_mg_dl']=200;d.loc[d.index[80:95],'glucose_mg_dl']=200;l,e=event_labels(d,180);self.assertNotIn(d.index[80],set(e.onset_time));d.loc[d.index[50],'glucose_mg_dl']=100;l,e=event_labels(d,180);self.assertIn(d.index[80],set(e.onset_time))
 def test_already_high_is_separate(self):
  l,_=event_labels(self.event(),180);self.assertEqual(l.origin_state.iloc[80],'currently_above');self.assertEqual(l.outcome.iloc[80],'excluded');self.assertTrue(pd.isna(l.event_label.iloc[80]))
 def test_incomplete_confirmation_censored_not_negative(self):
  d=self.event(n=94);l,e=event_labels(d,180);self.assertEqual(l.outcome.iloc[50],'censored');self.assertTrue(pd.isna(l.event_label.iloc[50]));self.assertEqual(len(e),0);self.assertEqual(l.max_label_information_end.iloc[50],pd.Timestamp('2020-01-01 01:34'))
 def test_gap_breaks_recovery_and_confirmation(self):
  for i in [70,90]:
   d=self.event();d.loc[d.index[i],'valid']=False;l,e=event_labels(d,180);self.assertEqual(len(e),0);self.assertEqual(l.outcome.iloc[50],'censored')
 def test_early_known_positive_does_not_need_later_unrelated_data(self):
  d=self.event(start=70);d.loc[d.index[90],'valid']=False;l,_=event_labels(d,180);self.assertEqual(l.event_label.iloc[60],1);self.assertEqual(l.actual_decision_information_end.iloc[60],d.index[84]);self.assertEqual(l.max_label_information_end.iloc[60],d.index[104])
 def test_any_crossing_differs_from_sustained(self):
  d=self.event(length=1);l,_=event_labels(d,180);a=future_any_crossing(d,180);self.assertTrue(a.iloc[50]);self.assertEqual(l.event_label.iloc[50],0)
 def test_strict_threshold_and_non_high_recovery(self):
  d=observed(160,np.full(160,180.));l,e=event_labels(d,180);self.assertEqual(len(e),0);self.assertEqual(l.origin_state.iloc[29],'eligible_at_risk');self.assertEqual(l.origin_state.iloc[28],'below_insufficient_recovery');self.assertEqual(l.event_label.iloc[50],0)
 def test_onset_at_issue_not_future_onset(self):
  l,_=event_labels(self.event(),180);self.assertEqual(l.outcome.iloc[80],'excluded');self.assertEqual(l.event_label.iloc[49],0)
