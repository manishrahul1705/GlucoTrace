"""Integrity checks use external fixtures, never copy or modify private data."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('portable',Path(__file__).resolve().parents[1]/'scripts/verify_portable_package.py')
portable=importlib.util.module_from_spec(spec);spec.loader.exec_module(portable)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.src=self.base/'source';self.dst=self.base/'package'
        self.src.mkdir();(self.src/'required.txt').write_text('required fixture')
        (self.src/'configs').mkdir()
        (self.src/portable.MANIFEST).write_text(json.dumps(dict(schema_version=1,
            required_source_files=['required.txt',portable.MANIFEST],
            required_evidence_files=['reports/required-evidence.json'],optional_evidence_files=[])))

    def test_all_required_hashes_sizes_actual_count_and_optional_absence(self):
        r=portable.verify_package(self.src,self.dst,['required.txt'],['optional.txt'])
        self.assertEqual(r['total_files_packaged'],len(list(self.dst.rglob('*.txt'))))
        self.assertEqual(r['optional_missing'],['optional.txt'])
        entry=r['hash_audit'][0]
        self.assertEqual(entry['size_bytes'],(self.dst/'required.txt').stat().st_size)
        self.assertEqual(entry['source_sha256'],portable.sha256_file(self.dst/'required.txt'))

    def test_optional_present_is_copied_and_hashed(self):
        (self.src/'optional.txt').write_text('optional')
        r=portable.verify_package(self.src,self.dst,['required.txt'],['optional.txt'])
        self.assertEqual(r['total_files_packaged'],2)
        self.assertEqual(r['optional_missing'],[])

    def test_missing_required_fails_before_copy(self):
        with self.assertRaisesRegex(portable.IntegrityError,'missing.txt'):
            portable.verify_package(self.src,self.dst,['required.txt','missing.txt'])
        self.assertFalse(self.dst.exists())

    def test_corrupt_copy_fails(self):
        def corrupt(src,dst):Path(dst).write_text('corrupted')
        with patch.object(portable.shutil,'copy2',side_effect=corrupt):
            with self.assertRaisesRegex(portable.IntegrityError,'hash mismatch'):
                portable.verify_package(self.src,self.dst,['required.txt'])

    def test_source_changed_during_copy_fails(self):
        original=portable.shutil.copy2
        def change(src,dst):
            original(src,dst);Path(src).write_text('changed')
        with patch.object(portable.shutil,'copy2',side_effect=change):
            with self.assertRaises(portable.IntegrityError):portable.verify_package(self.src,self.dst,['required.txt'])

    def test_unsafe_duplicate_and_private_paths_rejected(self):
        for paths in [['../escape'],['/absolute'],['C:/drive'],['a\\b'],['a//b'],['a/./b'],['required.txt.'],['required.txt '],['CON'],['a?b'],['required.txt','REQUIRED.txt'],['data/processed/secret']]:
            with self.subTest(paths=paths):
                with self.assertRaises(portable.IntegrityError):portable.verify_package(self.src,self.dst,paths)

    def test_main_failure_nonzero_no_success_report(self):
        report=self.base/'report.json';stdout=io.StringIO();stderr=io.StringIO()
        with patch.object(portable,'ROOT',self.src):
            with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
                code=portable.main(['--mode','evidence','--output',str(report)])
        self.assertEqual(code,1);self.assertNotIn('PASS',stdout.getvalue())
        self.assertIn('Missing required file:',stderr.getvalue());self.assertFalse(report.exists())

    def test_main_success_report_and_no_overwrite(self):
        report=self.base/'report.json'
        with patch.object(portable,'ROOT',self.src):
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(portable.main(['--output',str(report)]),0)
                original=report.read_bytes()
                self.assertEqual(portable.main(['--output',str(report)]),1)
                self.assertEqual(report.read_bytes(),original)
        self.assertEqual(json.loads(original)['total_files_packaged'],2)

    def test_source_mode_without_git_reports_or_private_artifacts(self):
        report=self.base/'source.json'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(portable.main(['--root',str(self.src),'--mode','source','--output',str(report)]),0)
        result=json.loads(report.read_text())
        self.assertFalse(result['evidence_selected'])
        self.assertEqual({x['file'] for x in result['hash_audit']},{'required.txt',portable.MANIFEST})
        self.assertFalse((self.src/'.git').exists())

    def test_evidence_mode_requires_declared_evidence(self):
        report=self.base/'evidence.json'
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(portable.main(['--root',str(self.src),'--mode','evidence','--output',str(report)]),1)
        self.assertFalse(report.exists())
        (self.src/'reports').mkdir();(self.src/'reports/required-evidence.json').write_text('{}')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(portable.main(['--root',str(self.src),'--mode','evidence','--output',str(report)]),0)
        self.assertEqual(json.loads(report.read_text())['total_files_packaged'],3)
