"""Synthetic orchestration fixtures ONLY: no patient files, fits or model loads.

Placeholder model files below are never deserialized. The injected executor
tests commands/guards, not scientific correctness of the existing pipeline.
"""
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('regeneration', Path(__file__).resolve().parents[1] / 'scripts/regenerate_replay.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RegenerationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic_regeneration_fixture_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'input'
        self.output = Path(self.temp.name) / 'new-run'
        self.root.mkdir()
        self.pids = list(range(1, 15))  # Synthetic identifiers, not real participants.
        self.split = {'eligible_participants': self.pids, 'folds': []}
        for pid in self.pids:
            train = [p for p in self.pids if p != pid]
            inners = []
            for n in range(3):
                val = train[n::3]
                inners.append({'train': {'participants': [p for p in train if p not in val]},
                               'validation': {'participants': val}})
            self.split['folds'].append({'outer_fold': f'synthetic_fold_{pid}',
                'test': {'participants': [pid]}, 'train': {'participants': train}, 'inner_folds': inners})
        self.put('reports/stage2/split_manifest.json', self.split)
        self.put('synthetic/raw.txt', 'synthetic raw placeholder')
        self.put('synthetic/provenance.json', {'extracted': [{'path': 'synthetic/raw.txt', 'sha256': self.hash('synthetic/raw.txt')}], 'downloads': []})
        self.put('configs/stage2_protocol.json', {'dataset': {'provenance_manifest': 'synthetic/provenance.json', 'provenance_sha256': self.hash('synthetic/provenance.json')}})
        self.put('configs/stage3_run.json', {'checkpoint_references': {'split_manifest_sha256': self.hash('reports/stage2/split_manifest.json'), 'stage2_protocol_sha256': self.hash('configs/stage2_protocol.json')}})
        self.put('configs/stage5_protocol.json', {'protocol': 'SYNTHETIC ORCHESTRATION FIXTURE ONLY'})
        stage1 = {}
        for path in runner.COMPARISONS:
            self.put(path, 'synthetic comparison placeholder')
            stage1[path] = self.hash(path)
        self.put('reports/stage2/stage1_preservation_manifest.json', stage1)
        self.prepared = ['data/processed/stage2/sensor_only.csv', 'data/processed/stage2/sensor_plus_baseline.csv',
                         'reports/stage2/personalization_coverage.csv', 'reports/stage2/split_manifest.json']
        self.prepared += [f'data/processed/stage2/{family}/p{p:03d}.csv'
                          for family in ['observations', 'personalization'] for p in self.pids]
        for path in self.prepared:
            if not (self.root / path).exists():
                self.put(path, 'synthetic prepared placeholder')
        self.put('reports/stage2/freeze_manifest.json', {'files': {p: self.hash(p) for p in self.prepared}})
        for path in runner.REFERENCES:
            self.put(path, 'synthetic historical reference placeholder')
        selections = self.root / runner.REFERENCES[0]
        with selections.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['family', 'variant', 'outer_fold', 'held_out_pid', 'selected_candidate_spec'], lineterminator='\n')
            writer.writeheader()
            writer.writerows(dict(family='ridge', variant='sensor_only', outer_fold=f['outer_fold'],
                held_out_pid=f['test']['participants'][0], selected_candidate_spec='{"alpha": 1.0}') for f in self.split['folds'])
        self.put('configs/stage4_protocol.json', {'input_hashes': {p: self.hash(p) for p in [
            'configs/stage2_protocol.json', 'configs/stage3_run.json', 'reports/stage2/split_manifest.json',
            'reports/stage2/personalization_coverage.csv', runner.REFERENCES[0], runner.REFERENCES[1],
            'data/processed/stage2/sensor_only.csv', 'data/processed/stage2/sensor_plus_baseline.csv']}})
        source = ['configs/source_package.json'] + runner.METADATA[:4] + [
            'scripts/prepare_stage2.py', 'scripts/run_stage5.py', 'scripts/verify_stage5.py']
        for p in source:
            if not (self.root / p).exists():
                self.put(p, '# SYNTHETIC ORCHESTRATION PLACEHOLDER; NOT EXECUTED')
        self.put('configs/source_package.json', {'required_source_files': source})
        self.authorization = dict(permits_processing_and_training=True,
            intended_use='SYNTHETIC TEST ONLY', basis='not a patient permission grant',
            reviewed_by='unit test', reviewed_at='synthetic fixture')

    def put(self, path, content):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(content) if isinstance(content, dict) else content, encoding='utf-8')

    def hash(self, path):
        return runner.sha(self.root / path)

    def plan(self):
        return runner.preflight(self.root, code_root=self.root)

    def fake_executor(self, command, work, log):
        """No subprocess or estimator is run by this fixture."""
        script = Path(command[1]).name
        self.commands.append(script)
        log.write_text('SYNTHETIC ORCHESTRATION ONLY')
        if script == 'prepare_stage2.py':
            for p, b in self.removed.items():
                target = work / p; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b)
        elif script == 'run_stage5.py':
            self.assertTrue((work / 'data/processed/stage5/protocol_freeze.json').is_file())
            for p in self.pids:
                (work / f'data/processed/stage5/model_{p:03d}.joblib').write_bytes(b'NOT A MODEL; SYNTHETIC FIXTURE')
        elif script == 'verify_stage5.py':
            runner.write(work / 'reports/stage5/verification.json', {'status': 'PASS', 'scope': 'SYNTHETIC ORCHESTRATION ONLY'})

    def test_preflight_uses_fourteen_selections_without_reselection(self):
        plan = self.plan()
        self.assertTrue(plan['ready'], plan['issues'])
        self.assertEqual(plan['selected_refits'], 14)
        self.assertEqual(plan['steps'], ['scripts/run_stage5.py', 'scripts/verify_stage5.py'])
        self.assertFalse(self.output.exists())

    def test_missing_reference_fails_before_output_or_training(self):
        (self.root / runner.REFERENCES[1]).unlink()
        plan = self.plan()
        self.assertFalse(plan['ready'])
        with self.assertRaisesRegex(ValueError, 'Preflight is blocked'):
            runner.execute(plan, self.output, self.authorization)
        self.assertFalse(self.output.exists())

    def test_missing_stage1_comparisons_block_preparation(self):
        (self.root / self.prepared[0]).unlink()
        for p in runner.COMPARISONS:
            (self.root / p).unlink()
        plan = self.plan()
        self.assertFalse(plan['ready'])
        self.assertEqual(plan['stage2_mode'], 'prepare')
        for p in runner.COMPARISONS:
            self.assertEqual(plan['files'][p]['status'], 'MISSING')

    def test_reuse_keeps_upstream_trace_without_requiring_raw_again(self):
        (self.root / 'synthetic/raw.txt').unlink()
        (self.root / runner.COMPARISONS[0]).unlink()
        plan = self.plan()
        self.assertTrue(plan['ready'], plan['issues'])
        self.assertEqual(plan['upstream_trace']['synthetic/raw.txt']['status'], 'MISSING')

    def test_corrupt_comparison_table_keeps_its_historical_gate(self):
        (self.root / self.prepared[0]).unlink()
        self.put(runner.COMPARISONS[0], 'changed')
        plan = self.plan()
        self.assertFalse(plan['ready'])
        self.assertEqual(plan['files'][runner.COMPARISONS[0]]['status'], 'INCOMPATIBLE')

    def test_fold_leakage_and_inner_overlap_are_rejected(self):
        for kind in ['outer', 'inner']:
            with self.subTest(kind=kind):
                split = json.loads(json.dumps(self.split))
                f = split['folds'][0]
                if kind == 'outer':
                    f['train']['participants'].append(f['test']['participants'][0])
                else:
                    f['inner_folds'][0]['train']['participants'].extend(f['inner_folds'][0]['validation']['participants'])
                with (self.root / runner.REFERENCES[0]).open() as stream:
                    with self.assertRaisesRegex(ValueError, 'exclusion'):
                        runner.validate_folds(split, list(csv.DictReader(stream)))

    def test_duplicate_or_wrong_candidate_is_rejected(self):
        with (self.root / runner.REFERENCES[0]).open() as stream:
            rows = list(csv.DictReader(stream))
        with self.assertRaisesRegex(ValueError, 'fourteen'):
            runner.validate_folds(self.split, rows + [rows[0]])
        rows[0]['held_out_pid'] = '2'
        with self.assertRaisesRegex(ValueError, 'held-out fold'):
            runner.validate_folds(self.split, rows)

    def test_isolated_execution_pins_outputs_before_verifier(self):
        self.commands = []
        before = {str(p.relative_to(self.root)): runner.sha(p) for p in self.root.rglob('*') if p.is_file()}
        result = runner.execute(self.plan(), self.output, self.authorization, self.fake_executor)
        self.assertEqual(self.commands, ['run_stage5.py', 'verify_stage5.py'])
        self.assertEqual(len([p for p in result['generated_sha256'] if p.endswith('.joblib')]), 14)
        self.assertFalse(result['patient_replay_verified'])
        self.assertEqual(result['state'], 'BUNDLE_VERIFIED_REPLAY_NOT_RUN')
        self.assertEqual(before, {str(p.relative_to(self.root)): runner.sha(p) for p in self.root.rglob('*') if p.is_file()})
        with self.assertRaises(FileExistsError):
            runner.execute(self.plan(), self.output, self.authorization, self.fake_executor)

    def test_prepare_is_ordered_and_original_stage2_hashes_are_retained(self):
        self.removed = {p: (self.root / p).read_bytes() for p in self.prepared if p != 'reports/stage2/split_manifest.json'}
        for p in self.removed:
            (self.root / p).unlink()
        plan = self.plan(); self.assertTrue(plan['ready'], plan['issues'])
        self.commands = []
        result = runner.execute(plan, self.output, self.authorization, self.fake_executor)
        self.assertEqual(self.commands, ['prepare_stage2.py', 'run_stage5.py', 'verify_stage5.py'])
        self.assertFalse(result['model_reselection'])

    def test_failed_preparation_hash_cannot_start_model_training(self):
        (self.root / self.prepared[0]).unlink()
        plan = self.plan(); self.assertTrue(plan['ready'], plan['issues'])
        commands = []
        def wrong(command, work, log):
            commands.append(Path(command[1]).name)
            p = work / self.prepared[0]; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('wrong generated bytes')
        with self.assertRaisesRegex(ValueError, 'Stage2 historical hash mismatch'):
            runner.execute(plan, self.output, self.authorization, wrong)
        self.assertEqual(commands, ['prepare_stage2.py'])
        self.assertEqual(json.loads((self.output / 'run-manifest.json').read_text())['state'], 'FAILED')

    def test_changed_input_or_missing_permission_never_trains(self):
        with self.assertRaisesRegex(ValueError, 'permission'):
            runner.execute(self.plan(), self.output, {})
        self.assertFalse(self.output.exists())
        plan = self.plan(); self.put(runner.REFERENCES[1], 'changed after preflight')
        with self.assertRaisesRegex(ValueError, 'Input changed'):
            runner.execute(plan, self.output, self.authorization)

    def test_dry_run_missing_inputs_nonzero_no_freeze_or_models(self):
        (self.root / runner.REFERENCES[1]).unlink()
        with patch.object(runner, 'CODE_ROOT', self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(['--dry-run', '--input-root', str(self.root), '--output-root', str(self.output)]), 2)
        self.assertTrue((self.output / 'preflight.json').exists())
        self.assertFalse(list(self.output.rglob('*.joblib')))
        self.assertFalse(list(self.output.rglob('*freeze*')))

    def test_output_inside_input_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'separate'):
            runner.execute(self.plan(), self.root / 'new', self.authorization)

    def test_verifier_cannot_change_the_pinned_generated_bundle(self):
        self.commands = []
        def mutate(command, work, log):
            self.fake_executor(command, work, log)
            if Path(command[1]).name == 'verify_stage5.py':
                (work / 'data/processed/stage5/model_001.joblib').write_bytes(b'changed fixture')
        with self.assertRaisesRegex(ValueError, 'changed during verification'):
            runner.execute(self.plan(), self.output, self.authorization, mutate)
        self.assertEqual(json.loads((self.output / 'run-manifest.json').read_text())['state'], 'FAILED')
