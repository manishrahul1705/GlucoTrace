"""Availability projections only; local-mode inputs below are synthetic fixtures."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from glucotwin.stage5.core import Calibration
from glucotwin.stage6.api import create_app
from glucotwin.stage6.engine import Session
from glucotwin.stage6.lab import exploration
from glucotwin.stage6.sources import synthetic


class AvailabilityTests(unittest.TestCase):
    def local(self):
        s=Session(replace(synthetic(length=361),mode='local'))
        s.advance_to(120)
        return s

    def by_variant(self,s):
        return {v['variant']:v for v in s.snapshot()['availability']}

    def test_complete_history_does_not_hide_incompatible_artifacts(self):
        s=Session(replace(synthetic(),artifact_reason='INCOMPATIBLE_ARTIFACTS'),warm=True)
        x=s.snapshot()
        self.assertFalse(x['recovery']['is_suppressed'])
        self.assertEqual(x['availability'][0]['current_reason'],'INCOMPATIBLE_ARTIFACTS')
        self.assertIsNone(x['forecasts'][-1]['value'])

    def test_variant_results_survive_reverse_order(self):
        s=self.local()
        before=self.by_variant(s)
        self.assertEqual(before['sensor_only_unadapted']['current_reason'],'OK')
        self.assertEqual(before['sensor_only_offset24h']['current_reason'],'INSUFFICIENT_OFFSET_DATA')
        s.variants=lambda:['sensor_only_offset24h','sensor_only_unadapted']
        self.assertEqual(self.by_variant(s),before)

    def test_frozen_insufficient_calibration_is_unavailable(self):
        s=self.local();s.transition(1440);s.transition(2880)
        self.assertTrue(s.frozen)
        views=self.by_variant(s)
        self.assertTrue(all(i['calibration_reason']=='INSUFFICIENT_CALIBRATION' for i in views['sensor_only_unadapted']['intervals']))
        self.assertTrue(all(i['calibration_reason']=='INSUFFICIENT_OFFSET_DATA' for i in views['sensor_only_offset24h']['intervals']))

    def test_calibration_levels_and_issued_bounds_are_separate(self):
        s=self.local();s.offset=2.;s.offset_reason='OK';s.frozen=True
        s.quantiles={('sensor_only_unadapted','0.10'):Calibration(100,91,4.,'OK'),
                     ('sensor_only_offset24h','0.05'):Calibration(100,96,7.,'OK')}
        s.advance_to(125)
        views=self.by_variant(s)
        self.assertEqual([i['calibration_reason'] for i in views['sensor_only_unadapted']['intervals']],['OK','INSUFFICIENT_CALIBRATION'])
        self.assertEqual([i['latest_reason'] for i in views['sensor_only_offset24h']['intervals']],['INSUFFICIENT_CALIBRATION','OK'])
        self.assertEqual(s.forecasts[-1].value-s.forecasts[-2].value,2.)
        bounds=s.forecasts[-1].intervals[-1]
        self.assertAlmostEqual(bounds[2]-bounds[1],14.)

    def test_synthetic_intervals_and_bounded_support(self):
        x=Session(synthetic(),warm=True).snapshot();r=x['recovery']
        self.assertEqual((r['available_valid_cells'],r['support_span_minutes']), (61,60))
        self.assertEqual((r['consecutive_valid_cells'],r['consecutive_valid_minutes']), (121,120))
        self.assertTrue(all(i['calibration_reason']=='SYNTHETIC_INTERVALS_UNCALIBRATED' for i in x['availability'][0]['intervals']))

    def test_between_issues_no_fresh_success_claim_or_mutation(self):
        s=Session(synthetic(),warm=True);s.advance_to(121)
        forecasts=list(s.forecasts);scores=dict(s.scores)
        x=s.snapshot();v=x['availability'][0]
        self.assertEqual(v['current_reason'],'AWAITING_NEXT_ISSUE')
        self.assertEqual(v['latest_point_reason'],'OK')
        self.assertEqual(v['next_issue_reason'],'AWAITING_NEXT_ISSUE')
        self.assertEqual((s.forecasts,s.scores),(forecasts,scores))

    def test_initial_issue_and_no_issue_projection(self):
        s=Session(synthetic());self.assertIsNone(s.forecasts[0].value)
        self.assertEqual(s.snapshot()['availability'][0]['current_reason'],'INSUFFICIENT_HISTORY')
        # Normal construction processes issue0 immediately. Exercise the explicit
        # not-started projection without changing this existing engine behavior.
        s.forecasts=[];s.minute=-1
        v=s.snapshot()['availability'][0]
        self.assertEqual(v['current_reason'],'SESSION_NOT_STARTED')
        self.assertEqual(v['latest_point_reason'],'NO_FORECAST_ISSUED')

    def test_final_issue_is_preserved_and_no_future_schedule(self):
        s=Session(synthetic(length=361));s.advance_to(355)
        self.assertEqual(s.snapshot()['recovery']['next_issue_minute'],360)
        s.advance_to(360);x=s.snapshot()
        self.assertEqual(s.forecasts[-1].origin,360)
        self.assertIsNotNone(s.forecasts[-1].value)
        self.assertIsNone(s.scores.get(s.forecasts[-1].id))
        self.assertIsNone(x['recovery']['next_issue_minute'])
        self.assertIsNone(x['recovery']['conditional_recovery_minute'])
        self.assertFalse(x['recovery']['next_issue_eligible'])
        self.assertEqual(x['availability'][0]['current_reason'],'SESSION_ENDED')
        self.assertEqual(x['availability'][0]['latest_point_reason'],'OK')

    def test_non_grid_end_does_not_advertise_issue_after_end(self):
        s=Session(synthetic(length=364));s.advance_to(361)
        self.assertIsNone(s.snapshot()['recovery']['next_issue_minute'])
        self.assertEqual(s.forecasts[-1].origin,360)

    def test_recovery_inside_and_beyond_session(self):
        s=Session(synthetic('dropout30',length=271));s.advance_to(210)
        self.assertEqual(s.snapshot()['recovery']['conditional_recovery_minute'],270)
        s.advance_to(270);self.assertIsNotNone(s.forecasts[-1].value)
        short=Session(synthetic('dropout30',length=261));short.advance_to(210)
        r=short.snapshot()['recovery']
        self.assertIsNone(r['conditional_recovery_minute'])
        self.assertIn('within this session',r['conditional_recovery_label'])

    def test_historical_evidence_and_latest_issue_counts_stay_fixed(self):
        s=Session(synthetic('dropout30'));s.advance_to(210)
        # Accepted cells include valid cells before the gap in the trailing
        # window; continuous-run length is a different current-state quantity.
        f=s.forecasts[-1];self.assertEqual(f.history_count,31)
        s.advance_to(212);self.assertEqual(s.snapshot()['recovery']['consecutive_valid_cells'],3)
        self.assertEqual(s.snapshot()['forecasts'][-1]['history_count'],31)
        early=exploration(s,210,180)['forecasts'][-1];s.advance_to(270)
        self.assertEqual(exploration(s,210,180)['forecasts'][-1],early)
        self.assertIsNone(early['score'])
        self.assertIsNotNone(s.scores[f.id])

    def test_api_schema_preserves_variant_and_nullable_schedule(self):
        with tempfile.TemporaryDirectory() as d:
            with TestClient(create_app(root=Path(d),runtime=Path(d)/'run',run_clock=False)) as c:
                manager=c.app.state.manager;s=self.local();manager.sessions[s.id]=s
                r=c.get(f'/api/replay/sessions/{s.id}/snapshot');self.assertEqual(r.status_code,200)
                self.assertEqual(len(r.json()['availability']),2)
                s.advance_to(s.end)
                x=c.get(f'/api/replay/sessions/{s.id}/snapshot').json()
                self.assertIsNone(x['recovery']['next_issue_minute'])
