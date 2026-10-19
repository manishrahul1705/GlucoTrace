"""Private genuine HTTP acceptance against immutable, independently verified records.

No model is fitted or calibration computed here. Numeric comparisons retain the
bundle verifier's 1e-8 absolute tolerance. All detailed evidence is private.
"""
import hashlib
import hmac
import math
import time
from pathlib import Path
import httpx
import numpy as np
import pandas as pd
from .common import load, write, stamp


def minute(value, epoch):
    return int((pd.Timestamp(value) - pd.Timestamp(epoch)).total_seconds() / 60)


def same(actual, expected):
    if pd.isna(expected):
        assert actual is None, (actual, expected)
    else:
        assert actual is not None and math.isclose(actual, float(expected), rel_tol=0, abs_tol=1e-8), (actual, expected)


class Records:
    def __init__(self, bundle):
        self.project = Path(bundle) / 'project'
        self.protocol = load(self.project / 'configs/stage5_protocol.json')
        self.pids = load(self.project / 'reports/new_experiment/frozen_split.json')['eligible_participants']
        self.adequacy = pd.read_csv(self.project / 'data/processed/stage5/partition_adequacy.csv').set_index('participant_id')
        self.artifacts = load(self.project / 'data/processed/stage5/calibration_artifacts.json')
        self.evaluation = pd.read_csv(self.project / 'data/processed/stage5/evaluation.csv', float_precision='round_trip',
                                     dtype={'alpha': str})

    def participant(self, pid):
        stream = pd.read_csv(self.project / f'data/processed/stage2/observations/p{pid:03d}.csv')
        start = pd.Timestamp(stream.event_time.iloc[0])
        anchor = minute(self.adequacy.loc[pid, 'anchor'], start)
        return start, anchor

    def expected(self, pid, scenario):
        start, _ = self.participant(pid)
        rows = self.evaluation[(self.evaluation.participant_id == pid) & (self.evaluation.scenario == scenario)].copy()
        rows['minute'] = ((pd.to_datetime(rows.issue_time) - start).dt.total_seconds() / 60).astype(int)
        return rows.set_index(['minute', 'variant', 'alpha'])

    def check_forecast(self, f, epoch, rows):
        m = minute(f['origin_time'], epoch)
        for interval in f['intervals']:
            row = rows.loc[(m, f['variant'], interval['alpha'])]
            assert f['point_reason'] == row.point_reason, (m, f['point_reason'], row.point_reason)
            same(f['value'], row.prediction)
            same(interval['lower'], row.lower)
            same(interval['upper'], row.upper)
            assert interval['reason'] == row.interval_reason
        return m


class HTTPAcceptance:
    def __init__(self, url, records, output):
        self.client = httpx.Client(base_url=url + '/api', timeout=120, trust_env=False)
        self.records, self.output = records, Path(output)
        self.counter = 0

    def call(self, method, path, **kwargs):
        r = self.client.request(method, path, **kwargs)
        assert r.status_code == 200, (r.status_code, r.text)
        return r.json()

    def step(self, s):
        self.counter += 1
        return self.call('POST', f"/replay/sessions/{s['session_id']}/control", json=dict(
            generation=s['generation'], request_id=f'acceptance-{self.counter}', action='step'))

    def projection(self, s, cutoff):
        return self.call('GET', f"/replay/sessions/{s['session_id']}/explore", params=dict(end_minute=cutoff, window=180))

    def check_cutoff(self, s):
        assert all(f['origin_time'] <= s['virtual_time'] for f in s['forecasts'])
        assert all(not f['score'] or f['score']['matured_time'] <= s['virtual_time'] for f in s['forecasts'])
        assert all(r['measurement_time'] <= s['virtual_time'] for r in s['history'])

    def clean(self, pid, source):
        record = dict(participant_id=pid, source_id=source, case='clean_full_chronological', status='RUNNING', checks=[])
        path = self.output / f'http-p{pid:03d}-clean.json'
        write(path, record)
        s = None
        try:
            _, anchor = self.records.participant(pid)
            p = self.records.protocol
            cadence, history, horizon = p['issue_cadence_minutes'], p['history_minutes'], p['horizon_minutes']
            expected = self.records.expected(pid, 'clean')
            s = self.call('POST', '/replay/sessions', json=dict(source_id=source, start='full', scenario='clean'))
            assert s['mode'] == 'local' and not s['artifacts_frozen']
            phases, unavailable = set(), set()
            pending = None
            baseline = None
            # First scoreable origin in the frozen evaluation table, not a fixed headline count.
            scoreable = expected.reset_index().query("point_reason == 'OK' and target_reason == 'OK'")
            if scoreable.empty:
                raise AssertionError('No scoreable evaluation origin: cannot demonstrate delayed scoring')
            selected = int(scoreable.minute.min())
            target = selected + horizon
            while s['elapsed_minutes'] < target:
                s = self.step(s)
                self.check_cutoff(s)
                m = int(s['elapsed_minutes'])
                wanted_phase = 'offset' if m < anchor + 1440 else 'calibration' if m < anchor + 2880 else 'evaluation'
                assert s['phase'] == wanted_phase, (m, s['phase'], wanted_phase)
                phases.add(s['phase'])
                assert s['artifacts_frozen'] == (m >= anchor + 2880)
                assert s['artifact_reason'] == 'OK'
                for availability in s['availability']:
                    unavailable.add(availability['current_reason'])
                    for level in availability['intervals']:
                        artifact = next(a for a in self.records.artifacts if a['participant_id'] == pid and
                                        a['variant'] == availability['variant'] and a['alpha'] == level['alpha'])
                        wanted = artifact['reason'] if s['artifacts_frozen'] else 'INSUFFICIENT_CALIBRATION'
                        assert level['calibration_reason'] == wanted
                current = [f for f in s['forecasts'] if minute(f['origin_time'], s['session_epoch']) == m]
                assert {f['variant'] for f in current} == set(p['models'])
                for f in current:
                    unavailable.add(f['point_reason'])
                    if m >= math.ceil((anchor + 2880 + history) / cadence) * cadence:
                        self.records.check_forecast(f, s['session_epoch'], expected)
                if m == selected:
                    pending = current
                    assert all(f['score'] is None for f in pending)
                    baseline = self.projection(s, selected)
                if pending and selected < m < target:
                    assert all(f['score'] is None for f in s['forecasts'] if f['id'] in {x['id'] for x in pending})
            matured = [f for f in s['forecasts'] if f['id'] in {x['id'] for x in pending}]
            assert len(matured) == len(p['models'])
            for f in matured:
                score = f['score']
                assert score is not None and score['matured_time'] == f['target_time']
                row = expected.loc[(selected, f['variant'], p['interval']['alphas'][0])]
                same(score['observed'], row.target)
                same(score['signed_error'], row.prediction - row.target)
            assert self.projection(s, selected) == baseline
            response = self.client.get(f"/replay/sessions/{s['session_id']}/explore", params=dict(end_minute=target + cadence, window=180))
            assert response.status_code == 422
            for kind in ('configuration', 'readings', 'forecasts', 'scores', 'summary'):
                response = self.client.post(f"/replay/sessions/{s['session_id']}/export", json=dict(generation=s['generation'], kind=kind))
                assert response.status_code == 403 and response.json()['detail'] == 'PATIENT_EXPORT_DISABLED'
            assert phases == {'offset', 'calibration', 'evaluation'}
            assert s['phase_counts']['offset'] == int(self.records.adequacy.loc[pid, 'n_offset'])
            assert s['phase_counts']['calibration'] == int(self.records.adequacy.loc[pid, 'n_calibration'])
            record.update(status='PASS', phases=sorted(phases), unavailable_reasons=sorted(unavailable - {'OK'}),
                          selected_origin=selected, exact_maturity=target, checks=[
                              'source creation; both variants at each issue', '24h/48h phase boundaries and frozen counts',
                              '90%/95% per-variant readiness from frozen artifacts', 'selected forecasts/bounds equal frozen evaluation rows',
                              'both variants delayed exact-target scoring', 'historical cutoff isolation and future rejection',
                              'all five export formats rejected'])
        except Exception as exc:
            record.update(status='FAIL', error=repr(exc))
        finally:
            if s:
                self.call('DELETE', f"/replay/sessions/{s['session_id']}")
            write(path, record)
        return record

    def loss(self, pid, source, duration):
        record = dict(participant_id=pid, source_id=source, case=f'dropout{duration}', status='RUNNING',
                      disclosure='Simulated input loss applied to processed patient replay; evaluator retains clean targets')
        path = self.output / f'http-p{pid:03d}-loss{duration}.json'
        write(path, record)
        s = None
        try:
            s = self.call('POST', '/replay/sessions', json=dict(source_id=source, start='warm', scenario=f'dropout{duration}'))
            assert s['gap'] is not None
            begin = minute(s['gap']['start_time'], s['session_epoch'])
            end = minute(s['gap']['end_time'], s['session_epoch'])
            assert end - begin == duration
            expected = self.records.expected(pid, f'input_loss_{duration}m')
            history = self.records.protocol['history_minutes']
            cadence = self.records.protocol['issue_cadence_minutes']
            stop = math.ceil((end + history) / cadence) * cadence
            checked, unavailable, recovered = 0, set(), False
            while s['elapsed_minutes'] < stop:
                s = self.step(s)
                m = int(s['elapsed_minutes'])
                if m < begin - cadence:
                    continue
                for f in s['forecasts']:
                    if minute(f['origin_time'], s['session_epoch']) != m:
                        continue
                    self.records.check_forecast(f, s['session_epoch'], expected)
                    checked += 1
                    unavailable.add(f['point_reason'])
                    if begin <= m < end + history:
                        assert f['value'] is None
                    if m >= end + history and f['point_reason'] == 'OK':
                        recovered = True
                assert s['artifact_reason'] == 'OK' and s['artifacts_frozen']
            record.update(status='PASS', checked_forecasts=checked, reasons=sorted(unavailable), recovered=recovered,
                          recovery_note='Recovery may remain unavailable if original processed data also lacks support')
        except Exception as exc:
            record.update(status='FAIL', error=repr(exc))
        finally:
            if s:
                self.call('DELETE', f"/replay/sessions/{s['session_id']}")
            write(path, record)
        return record


def source_mapping(records, runtime):
    key = (Path(runtime) / 'source-key').read_bytes()
    return {pid: 'local-' + hmac.new(key, str(pid).encode(), hashlib.sha256).hexdigest()[:16] for pid in records.pids}
