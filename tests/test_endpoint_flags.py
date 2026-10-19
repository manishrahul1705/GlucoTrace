"""Hand-calculated endpoint labels/metrics and delayed replay regressions; synthetic only."""
from dataclasses import replace
import unittest
import numpy as np
from glucotwin.stage6.endpoint_flags import issued_flags,views,metrics
from glucotwin.stage6.sources import synthetic
from glucotwin.stage6.engine import Session
from glucotwin.stage6.lab import exploration,export_session

class EndpointTests(unittest.TestCase):
 def source(self):
  s=synthetic();return replace(s,readings=tuple(replace(r,value=181.,valid=True) for r in s.readings),reference={t:181. for t in s.reference})
 def test_strict_threshold_equality_and_neighbors(self):
  self.assertEqual(issued_flags(180.,'OK'),((180,False),(250,False)))
  self.assertEqual(issued_flags(180.+1e-8,'OK')[0],(180,True))
  self.assertEqual(issued_flags(180.-1e-8,'OK')[0],(180,False))
  self.assertEqual(issued_flags(250.,'OK')[1],(250,False))
  self.assertEqual(issued_flags(250.+1e-8,'OK')[1],(250,True))
  for i,threshold in enumerate((180,250)):
   self.assertEqual(issued_flags(np.nextafter(float(threshold),-np.inf),'OK')[i],(threshold,False))
   self.assertEqual(issued_flags(np.nextafter(float(threshold),np.inf),'OK')[i],(threshold,True))
 def test_nonfinite_missing_and_unavailable_are_not_negative_flags(self):
  for value,reason in [(None,'OK'),(float('nan'),'OK'),(float('inf'),'OK'),(181.,'INCOMPLETE_HISTORY'),(181.,'BASELINE_UNAVAILABLE')]:
   self.assertEqual(issued_flags(value,reason),((180,None),(250,None)))
 def test_hand_confusion_fixture_and_missing_denominators(self):
  m=metrics([181,181,180,180,np.nan,179],[181,180,181,180,200,np.nan],['OK','OK','OK','OK','INCOMPLETE_HISTORY','OK'],180)
  self.assertEqual([m[k] for k in ['TP','FP','TN','FN']],[1,1,1,1])
  self.assertEqual([m[k] for k in ['scheduled','issued','suppressed','scorable','missing_target','issued_missing_target']],[6,5,1,4,1,1])
  self.assertEqual((m['precision'],m['recall'],m['specificity']),(.5,.5,.5))
  self.assertEqual((m['observed_positive_targets'],m['scorable_positive_targets']),(3,2))
 def test_zero_positive_and_zero_denominators(self):
  m=metrics([],[],[],180);self.assertTrue(all(m[k] is None for k in ['precision','recall','specificity']))
  m=metrics([100,100],[100,100],['OK','OK'],180);self.assertIsNone(m['precision']);self.assertIsNone(m['recall']);self.assertEqual(m['specificity'],1)
 def test_exact_maturity_and_historical_cutoff(self):
  s=Session(self.source());s.advance_to(60);f=s.forecasts[-1]
  self.assertEqual(f.endpoint_flags,((180,True),(250,False)))
  s.advance_to(89);self.assertEqual(views(f,s.scores.get(f.id),89)[0]['status'],'TARGET_PENDING')
  s.advance_to(90);self.assertEqual(views(f,s.scores[f.id],90)[0]['confusion'],'TP')
  historical=next(x for x in exploration(s,89,180)['forecasts'] if x['id']==f.id)
  self.assertTrue(historical['endpoint_flags'][0]['flag']);self.assertIsNone(historical['endpoint_flags'][0]['label']);self.assertIsNone(historical['endpoint_flags'][0]['confusion'])
 def test_missing_target_and_consecutive_flags_are_separate_endpoints(self):
  source=self.source();source.reference[90]=None;s=Session(source);s.advance_to(95)
  a=next(f for f in s.forecasts if f.origin==60);b=next(f for f in s.forecasts if f.origin==65)
  self.assertEqual(views(a,s.scores[a.id],95)[0]['status'],'TARGET_MISSING');self.assertIsNone(views(a,s.scores[a.id],95)[0]['confusion'])
  self.assertTrue(a.endpoint_flags[0][1]);self.assertTrue(b.endpoint_flags[0][1]);self.assertEqual(views(b,s.scores[b.id],95)[0]['confusion'],'TP')
 def test_already_high_does_not_require_recovery_or_episode_logic(self):
  s=Session(self.source());s.advance_to(60);self.assertEqual(s.forecasts[-1].endpoint_flags[0],(180,True))
  source=replace(self.source(),mode='local');source=replace(source,fusion=replace(source,model_family='baseline_sensor',artifact_reason='BASELINE_UNAVAILABLE'))
  s=Session(source);s.advance_to(60);current=s.forecasts[-4:]
  self.assertEqual({f.model_family for f in current},{'sensor_only','baseline_sensor'})
  self.assertTrue(all(flag is None for f in current if f.model_family=='baseline_sensor' for _,flag in f.endpoint_flags))
  with self.assertRaises(PermissionError):export_session(s,'forecasts',60,'private')

if __name__=='__main__':unittest.main()
