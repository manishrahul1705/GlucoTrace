"""Start isolated loopback services, verify a trusted bundle and accept patient replay.

Reports/runtime/screenshots must remain private and outside source/evidence packages.
No training, replacement execution, or production API changes are performed.
"""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import traceback
import httpx

sys.dont_write_bytecode = True
for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS'):
    os.environ[name] = '1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from glucotwin.experiment.common import separate, load, write, stamp, hashes, source_files, digest
from glucotwin.experiment.verify import check_hashes
from glucotwin.experiment.acceptance import Records, HTTPAcceptance, source_mapping


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def wait_ready(url, process, seconds=600):
    deadline = time.monotonic() + seconds
    with httpx.Client(trust_env=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Service exited before ready: ' + str(process.returncode))
            try:
                if client.get(url, timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(.5)
    raise TimeoutError('Loopback service readiness timeout')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--manifest-sha256', required=True, help='Previously trusted digest; never infer trust from current bundle')
    p.add_argument('--output', type=Path, required=True, help='Fresh isolated private report/runtime directory')
    p.add_argument('--browser', action='store_true')
    p.add_argument('--browser-only', action='store_true', help='Fresh browser rerun; HTTP/loss cases explicitly not repeated')
    a = p.parse_args()
    bundle, output = a.bundle.resolve(), a.output.resolve()
    separate(output, bundle, ROOT)
    check_hashes(bundle, a.manifest_sha256)
    output.mkdir(parents=True)
    result = dict(kind='NEW_EXPERIMENT_REPLAY_ACCEPTANCE', started_at=stamp(), status='RUNNING',
                  bundle=str(bundle), artifact_manifest_sha256=a.manifest_sha256,
                  http=[], browser=None, input_loss=[], training_fits=0)
    result['http_scope'] = 'NOT_RUN_BROWSER_ONLY' if a.browser_only else 'ALL_FROZEN_PARTICIPANTS'
    revision = dict(kind='REPLAY_IMPLEMENTATION_REVISION', revision='row-presence-v1',
                    recorded_at_utc=stamp(), artifact_manifest_sha256=a.manifest_sha256,
                    generation_amendment_sha256=load(bundle/'artifact-manifest.json')['amendment_sha256'],
                    scope='Replay metadata correction; no new training execution or calibration artifacts',
                    source_sha256=hashes(ROOT, source_files(ROOT)), training_fits=0)
    write(output / 'replay-implementation.json', revision)
    result['replay_implementation_sha256'] = digest(output / 'replay-implementation.json')
    services, logs = [], []
    try:
        api_port, web_port = free_port(), free_port()
        api = f'http://127.0.0.1:{api_port}'
        log = (output / 'server.log').open('w', encoding='utf-8'); logs.append(log)
        server = subprocess.Popen([sys.executable, '-B', str(ROOT / 'scripts/serve_new_experiment.py'),
            '--bundle', str(bundle), '--manifest-sha256', a.manifest_sha256,
            '--runtime', str(output / 'runtime'), '--port', str(api_port)], stdout=log, stderr=subprocess.STDOUT)
        services.append(server)
        wait_ready(api + '/api/health', server)
        result['bundle_verification'] = 'PASS: launcher independent verification completed before serving'
        records = Records(bundle)
        mapping = source_mapping(records, output / 'runtime')
        runner = HTTPAcceptance(api, records, output)
        discovered = runner.call('GET', '/replay/sources')['sources']
        available = {s['id'] for s in discovered if s['mode'] == 'local' and s['available']}
        assert available == set(mapping.values()), 'Frozen cohort/source discovery mismatch'
        write(output / 'browser-input.json', dict(sources=[dict(participant_id=pid, source_id=source) for pid, source in mapping.items()],
              durations=records.protocol['dropout']['durations_minutes']))
        for pid, source in ([] if a.browser_only else mapping.items()):
            outcome = runner.clean(pid, source)
            result['http'].append(outcome)
            write(output / 'acceptance.json', result)
            print(f'HTTP participant {pid}: {outcome["status"]}', flush=True)
        # Representative patient, all protocol-supported durations. Report scope explicitly.
        pid = records.pids[0]
        for duration in ([] if a.browser_only else records.protocol['dropout']['durations_minutes']):
            outcome = runner.loss(pid, mapping[pid], duration)
            result['input_loss'].append(outcome)
            write(output / 'acceptance.json', result)
            print(f'Simulated input loss {duration}m participant {pid}: {outcome["status"]}', flush=True)
        runner.client.close()
        if a.browser or a.browser_only:
            log = (output / 'frontend.log').open('w', encoding='utf-8'); logs.append(log)
            env = dict(os.environ, GLUCOTWIN_API_PORT=str(api_port), GLUCOTWIN_WEB_PORT=str(web_port))
            web = subprocess.Popen([shutil.which('node'), str(ROOT / 'frontend/node_modules/vite/bin/vite.js'),
                '--host', '127.0.0.1', '--configLoader', 'runner'], cwd=ROOT / 'frontend', env=env, stdout=log, stderr=subprocess.STDOUT)
            services.append(web)
            wait_ready(f'http://127.0.0.1:{web_port}', web, seconds=60)
            browser_run = subprocess.run([shutil.which('node'), str(ROOT / 'scripts/verify_patient_replay_browser.mjs'),
                '--url', f'http://127.0.0.1:{web_port}', '--input', str(output / 'browser-input.json'),
                '--output', str(output)], check=False)
            result['browser'] = load(output / 'browser-acceptance.json')
            if browser_run.returncode:
                result['browser_exit_code'] = browser_run.returncode
        result['status'] = 'PASS' if all(r['status'] == 'PASS' for r in result['http'] + result['input_loss']) else 'FAIL'
        if (a.browser or a.browser_only) and (result['browser']['status'] != 'PASS' or result.get('browser_exit_code', 0)):
            result['status'] = 'FAIL'
        check_hashes(bundle, a.manifest_sha256)
        assert hashes(ROOT, revision['source_sha256']) == revision['source_sha256'], 'Replay revision source changed during acceptance'
    except Exception:
        result['status'], result['error'] = 'FAIL', traceback.format_exc()
        print(result['error'], flush=True)
    finally:
        for service in reversed(services):
            service.terminate()
            try:
                service.wait(timeout=10)
            except subprocess.TimeoutExpired:
                service.kill(); service.wait()
        for log in logs:
            log.close()
        result['finished_at'] = stamp()
        write(output / 'acceptance.json', result)
    print('Private replay acceptance:', result['status'])
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
