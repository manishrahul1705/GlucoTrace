"""Production-function Stage 5 tests; no real observations required."""
import unittest
from dataclasses import FrozenInstanceError
import numpy as np
import pandas as pd
from glucotwin.stage5.core import (calibrate,fit_offset,partition_origins,forecast_stream,
    interval_bounds,exact_targets,inject_gap,StreamError)
from glucotwin.stage5.metrics import summarize,slice_masks


def stream(n=400):
    idx = pd.date_range('2020-01-01',periods=n,freq='min')
    return pd.DataFrame(dict(glucose_mg_dl=100+np.arange(n)*0.1, valid=True,
                             row_present=True,sensor='Dexcom GL'),index=idx)


class TestStage5(unittest.TestCase):
    def test_exact_rank_critical_boundaries(self):
        for alpha,n in [('0.10',9),('0.05',19),('0.10',99),('0.05',39)]:
            c = calibrate(np.arange(n),alpha,minimum=1)
            expected = {'0.10': {9:9,99:90},'0.05':{19:19,39:38}}[alpha][n]
            self.assertEqual(c.k,expected)
            self.assertEqual(c.q,expected-1)
        for alpha,n in [('0.10',8),('0.05',18)]:
            self.assertEqual(calibrate(np.arange(n),alpha,1).reason,'INSUFFICIENT_CALIBRATION')

    def test_engineering_minimum_is_separate(self):
        self.assertEqual(calibrate(np.arange(99),'0.10').reason,'INSUFFICIENT_CALIBRATION')
        self.assertEqual(calibrate(np.arange(100),'0.10').k,91)
        self.assertEqual(calibrate([], '0.05').reason,'INSUFFICIENT_CALIBRATION')

    def test_invalid_score_set_not_dropped(self):
        for bad in [np.nan,np.inf,-1]:
            c=calibrate([*range(100),bad],'0.10')
            self.assertIsNone(c.q)
            self.assertEqual(c.invalid_count,1)
            self.assertEqual(c.reason,'INVALID_CALIBRATION_SCORES')
        with self.assertRaises(ValueError): calibrate([1],0)

    def test_median_offset_sign(self):
        b,reason=fit_offset([100,100,100],[110,110,20],minimum=3)
        self.assertEqual((b,reason),(-10,'OK'))
        self.assertEqual(fit_offset([100],[90])[1],'INSUFFICIENT_OFFSET_DATA')
        self.assertEqual(fit_offset([100],[np.nan],1)[1],'INVALID_MODEL_OUTPUT')

    def test_full_support_boundary_purge_and_disjointness(self):
        a=pd.Timestamp('2020-01-01'); b=a+pd.Timedelta(hours=24); c=a+pd.Timedelta(hours=48)
        issue=pd.DatetimeIndex([b-pd.Timedelta(minutes=31),b-pd.Timedelta(minutes=30),
                               b+pd.Timedelta(minutes=59),b+pd.Timedelta(minutes=60),
                               c-pd.Timedelta(minutes=30),c+pd.Timedelta(minutes=60)])
        frame=pd.DataFrame(dict(issue_time=issue,history_start=issue-pd.Timedelta(minutes=60),target_time=issue+pd.Timedelta(minutes=30)))
        out=partition_origins(frame,a)
        self.assertEqual(out.partition.tolist(),['offset','purged','purged','calibration','purged','evaluation'])
        # Changing later residuals cannot affect inputs selected for either early phase.
        out['target']=np.arange(len(out))+100.; out['prediction']=110.
        original=fit_offset(out[out.partition=='offset'].target,out[out.partition=='offset'].prediction,1)
        cal_ids=set(out.index[out.partition=='calibration'])
        self.assertTrue(cal_ids.isdisjoint(out.index[out.partition=='offset']))
        out.loc[out.partition=='evaluation','target']=-999
        self.assertEqual(original,fit_offset(out[out.partition=='offset'].target,out[out.partition=='offset'].prediction,1))
        frame.loc[0,'target_time']+=pd.Timedelta(minutes=1)
        with self.assertRaises(ValueError): partition_origins(frame,a)

    def test_nested_intervals_and_inclusive_coverage(self):
        q90,q95=calibrate(range(100),'0.10'),calibrate(range(100),'0.05')
        l90,u90,_=interval_bounds(100,q90); l95,u95,_=interval_bounds(100,q95)
        self.assertLessEqual(l95,l90);self.assertGreaterEqual(u95,u90)
        rows=self.rows([1,1],[l90,u90],[100,100],[l90,l90],[u90,u90])
        agg,_=summarize(rows,1)
        self.assertTrue(agg.empirical_coverage.eq(1).all())

    def test_point_available_without_intervals(self):
        d=stream(); result=forecast_stream(d,[d.index[60]],lambda x:x[:,0])
        self.assertEqual(result.point_reason.iloc[0],'OK')
        self.assertEqual(interval_bounds(result.prediction.iloc[0],calibrate([],'0.10'))[2],'INSUFFICIENT_CALIBRATION')

    def test_invalid_model_and_interval_output(self):
        d=stream(); result=forecast_stream(d,[d.index[60]],lambda x:np.full(len(x),np.inf))
        self.assertEqual(result.point_reason.iloc[0],'INVALID_MODEL_OUTPUT')
        from glucotwin.stage5.core import Calibration
        self.assertEqual(interval_bounds(100,Calibration(100,91,-1,'OK'))[2],'INVALID_INTERVAL_ORDER')
        with self.assertRaises(FrozenInstanceError):
            calibrate(range(100),'0.10').q=0

    def test_units_duplicates_nonfinite(self):
        d=stream()
        with self.assertRaisesRegex(StreamError,'INVALID_UNIT'):
            forecast_stream(d,[d.index[60]],lambda x:x[:,0],unit='mmol/L')
        duplicate=pd.concat([d.iloc[:61],d.iloc[[60]].assign(glucose_mg_dl=200)])
        with self.assertRaisesRegex(StreamError,'CONFLICTING_DUPLICATE'):
            forecast_stream(duplicate,[d.index[60]],lambda x:x[:,0])
        d.loc[d.index[60],'glucose_mg_dl']=np.nan
        self.assertIn('NON_FINITE_READING',forecast_stream(d,[d.index[60]],lambda x:x[:,0]).point_reason.iloc[0])

    def test_dropout_suppression_rebuild_immutable(self):
        d=stream(); start=d.index[100]
        clean=forecast_stream(d,d.index[90:300:5],lambda x:x[:,0])
        saved=clean.copy(deep=True)
        for duration in [15,30,60,120]:
            changed=inject_gap(d,start,duration)
            issues=pd.DatetimeIndex([start,start+pd.Timedelta(minutes=duration-1),
                                     start+pd.Timedelta(minutes=duration),start+pd.Timedelta(minutes=duration+59),
                                     start+pd.Timedelta(minutes=duration+60)])
            result=forecast_stream(changed,issues,lambda x:x[:,0])
            self.assertTrue(result.point_reason.iloc[0].startswith('MISSING_CURRENT_READING'))
            self.assertIn('STALE_READING',result.point_reason.iloc[1])
            self.assertEqual(result.point_reason.iloc[2],'INCOMPLETE_HISTORY')
            self.assertEqual(result.point_reason.iloc[3],'INCOMPLETE_HISTORY')
            self.assertEqual(result.point_reason.iloc[4],'OK')
            self.assertEqual(exact_targets(d,[start])[0],d.glucose_mg_dl.loc[start+pd.Timedelta(minutes=30)])
        pd.testing.assert_frame_equal(clean,saved)
        self.assertTrue(d.valid.all())

    def test_application_future_access_isolation(self):
        # Tests the actual replay/feature/predict path, not upstream interpolation.
        d=stream(); t=d.index[100]
        predictor=lambda x: x[:,0]+2*x[:,1]+x[:,-1]
        earlier=forecast_stream(d,[t],predictor)
        altered=d.copy(); altered.loc[altered.index>t,'glucose_mg_dl']=-999
        altered.loc[altered.index>t,'valid']=False
        pd.testing.assert_frame_equal(earlier,forecast_stream(altered,[t],predictor))

    def test_exact_target_and_history_missingness(self):
        d=stream(); t=d.index[100]
        d=d.drop(t+pd.Timedelta(minutes=30))
        self.assertTrue(np.isnan(exact_targets(d,[t])[0]))
        self.assertEqual(forecast_stream(d,[t],lambda x:x[:,0]).point_reason.iloc[0],'OK')
        d=d.drop(t-pd.Timedelta(minutes=1))
        self.assertEqual(forecast_stream(d,[t],lambda x:x[:,0]).point_reason.iloc[0],'INCOMPLETE_HISTORY')
        self.assertEqual(forecast_stream(d,[d.index[1]],lambda x:x[:,0]).point_reason.iloc[0],'INSUFFICIENT_HISTORY')

    @staticmethod
    def rows(pids,targets,predictions,lower,upper):
        return pd.DataFrame(dict(participant_id=pids,target=targets,prediction=predictions,lower=lower,upper=upper,
                                 point_reason='OK',interval_reason='OK',clean_eligible=True))

    def test_participant_weighting_and_absent_slices(self):
        rows=self.rows([1,2,2,2],[70,180,200,200],[71,190,210,210],[60]*4,[220]*4)
        agg,per=summarize(rows,3)
        equal=agg[agg.weighting=='equal_participant'].iloc[0]
        pooled=agg[agg.weighting=='pooled_window'].iloc[0]
        self.assertEqual(equal.mae,5.5);self.assertEqual(pooled.mae,7.75)
        self.assertEqual(equal.absent_point_participants,1)
        masks=slice_masks(rows)
        self.assertEqual(int(masks['70to180'].sum()),2)
        empty,_=summarize(rows[masks['below70']],3)
        self.assertTrue(empty.mae.isna().all());self.assertTrue(empty.n_point_scored.eq(0).all())


if __name__=='__main__':
    unittest.main()
