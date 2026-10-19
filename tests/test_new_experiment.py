"""SYNTHETIC fixtures only. No acquired patient inputs are parsed or fitted."""
import contextlib
import csv
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from glucotwin.experiment.audit import audit_stream
from glucotwin.experiment import generate as gen, verify as verifier
from glucotwin.experiment.common import ROOT, digest, write, load, separate, preflight
from glucotwin.preprocessing import prepare_observations, construct_origins
from glucotwin.features import paired_features
from glucotwin.contracts import ParticipantBaseline, BASE_UNITS
from glucotwin.splits import make_splits
from glucotwin.stage5.core import calibrate


def stream(values):
    g=np.asarray(values,float)
    return pd.DataFrame(dict(glucose_mg_dl=g,valid=np.isfinite(g)&(g>=40)&(g<=400)),
                        index=pd.date_range('2020-01-01',periods=len(g),freq='min'))


class AuditArithmetic(unittest.TestCase):
    def test_training_only_scaling_and_ridge_solution_reject_mutations(self):
        from glucotwin.stage3.training import fit_estimator
        rng=np.random.default_rng(33);x=rng.normal(size=(50,21));x[:,0]=4
        y=3*x[:,2]+2
        model,scaler=fit_estimator('ridge',{'alpha':1},x,y)
        verifier.check_model(model,scaler,x,y,1)
        scaler.mean_[1]+=2
        with self.assertRaisesRegex(ValueError,'Training-only scaler mean'):
            verifier.check_model(model,scaler,x,y,1)
        scaler.mean_[1]-=2;model.coef_[2]+=1
        with self.assertRaisesRegex(ValueError,'normal-equation'):
            verifier.check_model(model,scaler,x,y,1)
    def test_exact_history_and_target_boundaries(self):
        for n,expected in [(90,0),(91,1),(92,2)]:
            with self.subTest(n=n):
                w,_=audit_stream(stream([120]*n),1);self.assertEqual(w[0]['eligible_origins'],expected)

    def test_intermediate_future_missing_does_not_remove_exact_target(self):
        g=np.full(91,120.);g[70]=np.nan
        w,_=audit_stream(stream(g),1);self.assertEqual(w[0]['eligible_origins'],1)
        for t in [0,60,90]:
            h=np.full(91,120.);h[t]=np.nan
            self.assertEqual(audit_stream(stream(h),1)[0][0]['eligible_origins'],0)

    def test_threshold_equality_recovery_and_confirmation(self):
        for threshold in (180,250):
            g=[threshold]*30+[threshold+1]*15
            _,e=audit_stream(stream(g),1);r=next(r for r in e if r['threshold_mg_dl']==threshold)
            self.assertEqual(r['independent_episodes_30min_recovery'],1)
            for t,value in [(29,threshold+1),(30,threshold),(44,np.nan)]:
                h=g.copy();h[t]=value
                r=next(r for r in audit_stream(stream(h),1)[1] if r['threshold_mg_dl']==threshold)
                self.assertEqual(r['independent_episodes_30min_recovery'],0)

    def test_record_end_and_crossing(self):
        _,e=audit_stream(stream([180]*30+[181]),1)
        self.assertEqual(e[0]['new_crossing_positive_origins'],1)
        self.assertEqual(e[0]['independent_episodes_30min_recovery'],0)
        _,e=audit_stream(stream([180]*30+[180]),1)
        self.assertEqual(e[0]['new_crossing_positive_origins'],0)

    def test_independent_convolution_counts_with_missingness(self):
        rng=np.random.default_rng(7);g=rng.uniform(50,300,400);g[[0,55,70,200,399]]=np.nan
        w,e=audit_stream(stream(g),1);nw,ne=verifier.counts(g,stream(g).valid)
        self.assertEqual(w[0]['eligible_origins'],nw)
        self.assertEqual({r['threshold_mg_dl']:(r['new_crossing_positive_origins'],r['independent_episodes_30min_recovery']) for r in e},ne)

    def test_scalar_features_known_linear_history(self):
        f=verifier.feature(np.arange(61)+100)
        np.testing.assert_array_equal(f[:13],np.arange(160,99,-5))
        self.assertAlmostEqual(f[13],152.5)
        self.assertAlmostEqual(f[14],np.sqrt(255/12))
        np.testing.assert_allclose(f[-2:],[1,1])

    def test_boundary_purges_independent(self):
        a=pd.Timestamp('2020-01-01')
        for minute,expected in [(1409,'offset'),(1410,'purged'),(1499,'purged'),(1500,'calibration'),
                                (2850,'purged'),(2940,'evaluation')]:
            self.assertEqual(verifier.phase(a+pd.Timedelta(minutes=minute),a,5),expected)
        self.assertEqual(verifier.phase(a+pd.Timedelta(minutes=2850),a,4),'purged_boundary')

    def test_rank_minimum_invalid_and_even_median(self):
        self.assertEqual(verifier.median([8,2,4,6]),5)
        for n in [0,99,100,101]:
            for alpha in ['0.10','0.05']:
                scores=np.arange(n,dtype=float)
                independent=verifier.quantile(scores,alpha);actual=calibrate(scores,alpha)
                self.assertEqual(independent,(actual.n,actual.k,actual.q,actual.reason))
        self.assertEqual(verifier.quantile(range(100),'0.10'),(100,91,90.,'OK'))
        self.assertEqual(verifier.quantile([0]*99+[np.nan],'0.10')[3],'INVALID_CALIBRATION_SCORES')


class BundleFixtures(unittest.TestCase):
    """One labelled 14-fold synthetic bundle, never usable by production CLI."""
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='SYNTHETIC_NEW_EXPERIMENT_')
        cls.bundle=Path(cls.tmp.name)/'fixture';cls.project=cls.bundle/'project'
        cls.project.mkdir(parents=True)
        cls.pids=list(range(1,15));members={};provenance={'version':'SYNTHETIC','extracted':[],'downloads':[],'archive_sha256_verified':False}
        needed=['scripts/prepare_stage2.py','scripts/regenerate_replay.py','configs/stage2_protocol.json','configs/stage5_protocol.json']
        shutil.copytree(ROOT/'src',cls.project/'src',ignore=shutil.ignore_patterns('__pycache__'))
        for name in needed:
            p=cls.project/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,p)
        cls.source={r:digest(cls.project/r) for r in needed if not r.startswith('configs/')}
        bio=[]
        for pid in cls.pids:
            n=4801;t=np.arange(n)
            values=155+pid*.7+45*np.sin(t/57)+8*np.cos(t/13)
            values[3401:3404]=np.nan  # late missingness and recovery, never compressed
            raw=pd.DataFrame({'Timestamp':pd.date_range('2020-01-01',periods=n,freq='min'),'Dexcom GL':values})
            name=f'data/raw/tables/CGMacros/CGMacros-{pid:03d}/CGMacros-{pid:03d}.csv'
            gen.csv(cls.project/name,raw);h=digest(cls.project/name)
            provenance['extracted'].append(dict(path=name,archive_member=f'CGMacros/CGMacros-{pid:03d}/CGMacros-{pid:03d}.csv',sha256=h))
            d=prepare_observations(pd.read_csv(cls.project/name),pid,name,h)
            base=ParticipantBaseline(pid,'T2D',40,25,7,100,BASE_UNITS,'synthetic',pid,'synthetic','assumed')
            origins,_=construct_origins(d,base);sf,_=paired_features(d,origins,base);members[pid]=list(sf.origin_id)
            bio.append({'subject':pid,'Age':40,'BMI':25,'A1c PDL (Lab)':7,'Fasting GLU - PDL (Lab)':100})
        name='data/raw/tables/CGMacros/bio.csv';gen.csv(cls.project/name,pd.DataFrame(bio))
        provenance['extracted'].append(dict(path=name,archive_member='CGMacros/bio.csv',sha256=digest(cls.project/name)))
        write(cls.project/'reports/stage1/provenance_manifest.json',provenance)
        config=load(cls.project/'configs/stage2_protocol.json');config['dataset']['provenance_sha256']=digest(cls.project/'reports/stage1/provenance_manifest.json')
        config['population']['expected_t2d_ids']=cls.pids;write(cls.project/'configs/stage2_protocol.json',config)
        cls.split=make_splits(members);write(cls.project/'reports/stage2/split_manifest.json',cls.split)
        write(cls.project/'reports/new_experiment/frozen_split.json',cls.split)
        selected=[]
        for fold in cls.split['folds']:
            selected.append(dict(family='ridge',variant='sensor_only',outer_fold=fold['outer_fold'],
                held_out_pid=fold['test']['participants'][0],selected_candidate_spec='{"alpha": 1.0}'))
        gen.csv(cls.project/'reports/stage3_remediation/selected_candidates.csv',pd.DataFrame(selected))
        gen.audit_project(cls.project)
        with (cls.bundle/'synthetic-stage2.log').open('w') as log:
            subprocess.run([sys.executable,str(cls.project/'scripts/prepare_stage2.py')],stdout=log,stderr=subprocess.STDOUT,check=True)
        plan=dict(selected=selected,input_hashes={e['path']:e['sha256'] for e in provenance['extracted']},
                  metadata_hashes={'reports/stage2/split_manifest.json':digest(cls.project/'reports/new_experiment/frozen_split.json')})
        amendment=dict(kind='SYNTHETIC_FIXTURE_ONLY',source_sha256=cls.source,plan=plan)
        write(cls.bundle/'amendment.json',amendment)
        cls.manifest=dict(kind='SYNTHETIC_FIXTURE_ONLY',synthetic_fixture=True,amendment_sha256=digest(cls.bundle/'amendment.json'),
                          amendment_frozen_at='SYNTHETIC',fits_completed=0)
        with patch.object(gen,'fit_estimator',wraps=gen.fit_estimator) as fit:
            gen.generate_models(cls.project,cls.split,cls.manifest,synthetic=True)
            cls.fit_calls=fit.call_count
        cls.artifact=dict(kind='NEW_EXPERIMENT',synthetic_fixture=True,fits=14,
            amendment_sha256=digest(cls.bundle/'amendment.json'),files={
                p.relative_to(cls.project).as_posix():digest(p) for p in cls.project.rglob('*') if p.is_file()
                and '__pycache__' not in p.parts and p.suffix!='.pyc'})
        write(cls.bundle/'artifact-manifest.json',cls.artifact)
        cls.trusted=digest(cls.bundle/'artifact-manifest.json')

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_14_fits_total_and_independent_verification(self):
        self.assertEqual(self.fit_calls,14);self.assertEqual(self.manifest['fits_completed'],14)
        result=verifier.verify(self.bundle,self.trusted,allow_synthetic=True)
        self.assertEqual(result['status'],'PASS');self.assertTrue(result['synthetic_fixture'])
        self.assertFalse(result['patient_replay_verified'])

    def test_production_verifier_rejects_fixture_before_deserializing(self):
        with patch.object(verifier.joblib,'load',side_effect=AssertionError('must not load')):
            with self.assertRaisesRegex(ValueError,'Synthetic fixture'):
                verifier.verify(self.bundle,self.trusted)

    def test_hash_failure_precedes_model_loading(self):
        with patch.object(verifier.joblib,'load',side_effect=AssertionError('must not load')):
            with self.assertRaisesRegex(ValueError,'Caller-pinned'):
                verifier.verify(self.bundle,'0'*64,allow_synthetic=True)

    def test_model_corruption_rejected(self):
        p=self.project/'data/processed/stage5/model_001.joblib';original=p.read_bytes()
        try:
            p.write_bytes(b'CORRUPTED SYNTHETIC PLACEHOLDER')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                verifier.verify(self.bundle,self.trusted,allow_synthetic=True)
        finally:p.write_bytes(original)

    def test_rehashed_reference_target_corruption_rejected_independently(self):
        p=self.project/'data/processed/stage5/partition_predictions.csv'
        original=p.read_bytes();manifest_path=self.bundle/'artifact-manifest.json'
        original_manifest=manifest_path.read_bytes()
        try:
            frame=pd.read_csv(p,float_precision='round_trip');frame.loc[0,'target_mg_dl']+=10
            gen.csv(p,frame)
            altered=load(manifest_path);altered['files'][p.relative_to(self.project).as_posix()]=digest(p)
            write(manifest_path,altered)
            with self.assertRaisesRegex(ValueError,'Reference exact targets'):
                verifier.verify(self.bundle,digest(manifest_path),allow_synthetic=True)
        finally:
            p.write_bytes(original);manifest_path.write_bytes(original_manifest)

    def test_cohort_difference_cannot_fit(self):
        wrong=json.loads(json.dumps(self.split));wrong['eligible_participants']=wrong['eligible_participants'][:-1]
        with patch.object(gen,'fit_estimator',side_effect=AssertionError('must not fit')):
            with self.assertRaisesRegex(ValueError,'Prepared split differs'):
                gen.generate_models(self.project,wrong,self.manifest,synthetic=True)

    def test_existing_and_nested_outputs_rejected(self):
        with self.assertRaisesRegex(ValueError,'Existing'):
            separate(self.bundle,Path(self.tmp.name)/'other')
        with self.assertRaisesRegex(ValueError,'separate'):
            separate(self.bundle/'nested',self.bundle)


class PreflightFailures(unittest.TestCase):
    def test_synthetic_orchestration_order_freeze_and_failure_record(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_ORCHESTRATION_') as t:
            root=Path(t);code=root/'code';amend=root/'amend';acq=root/'acq';out=root/'run'
            for base in [code,amend/'source']:
                write(base/'marker.json',{'scope':'SYNTHETIC ONLY'})
            meta=acq/'experiment-v1/input-project'
            for name in gen.META:write(meta/name,{'scope':'SYNTHETIC ONLY'})
            raw=acq/'inputs/data/raw/synthetic.txt';raw.parent.mkdir(parents=True);raw.write_text('SYNTHETIC')
            plan={'input_hashes':{'data/raw/synthetic.txt':digest(raw)},'runtime':'SYNTHETIC',
                  'metadata_hashes':{name:digest(meta/name) for name in gen.META}}
            write(amend/'amendment.json',dict(kind='NEW_EXPERIMENT_IMPLEMENTATION_AMENDMENT',
                  source_sha256={'marker.json':digest(code/'marker.json')},plan=plan,frozen_at_utc='SYNTHETIC'))
            expected=digest(amend/'amendment.json');commands=[]
            authorization=dict(permits_processing_and_training=True,private_noncommercial_only=True,
                basis='SYNTHETIC TEST NOT A PATIENT GRANT',reviewed_by='fixture',reviewed_at='SYNTHETIC')
            def audit(project):commands.append('audit')
            def models(project,split,manifest,synthetic=False):
                self.assertTrue(synthetic);self.assertTrue(manifest['synthetic_fixture'])
                commands.append('fits14_reuse');manifest['fits_completed']=14
            def run(command,**kwargs):
                name=Path(command[1]).name;commands.append(name)
                if name=='verify_new_experiment.py':
                    write(out/'bundle-verification.json',dict(status='PASS',synthetic_fixture=True,
                          artifact_manifest_sha256=digest(out/'artifact-manifest.json')))
                return subprocess.CompletedProcess(command,0)
            with patch.object(gen,'ROOT',code),patch.object(gen,'preflight',return_value=plan),\
                 patch.object(gen,'audit_project',side_effect=audit),patch.object(gen,'generate_models',side_effect=models),\
                 patch.object(gen.subprocess,'run',side_effect=run):
                result=gen.execute(acq,amend/'amendment.json',expected,out,authorization,_synthetic_fixture=True)
                self.assertEqual(result['state'],'SYNTHETIC_FIXTURE_VERIFIED')
                self.assertEqual(commands,['audit','prepare_stage2.py','fits14_reuse','verify_new_experiment.py'])
                self.assertEqual(load(out/'artifact-manifest.json')['fits'],14)
                self.assertTrue(load(out/'artifact-manifest.json')['synthetic_fixture'])
            failed=root/'failed'
            with patch.object(gen,'ROOT',code),patch.object(gen,'preflight',return_value=plan),\
                 patch.object(gen,'audit_project',side_effect=ValueError('SYNTHETIC failure')),\
                 patch.object(gen,'generate_models',side_effect=AssertionError('must not fit')):
                with self.assertRaisesRegex(ValueError,'SYNTHETIC failure'):
                    gen.execute(acq,amend/'amendment.json',expected,failed,authorization,_synthetic_fixture=True)
            self.assertEqual(load(failed/'run-manifest.json')['state'],'FAILED')
            self.assertEqual(load(failed/'run-manifest.json')['fits_completed'],0)

    def test_amendment_or_permission_mismatch_refuses_execution(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_amendment_') as t:
            root=Path(t);p=root/'amendment.json';write(p,{'scope':'SYNTHETIC'})
            with self.assertRaisesRegex(ValueError,'Amendment digest mismatch'):
                gen.execute(root/'acq',p,'0'*64,root/'out',{})
            self.assertFalse((root/'out').exists())

    def test_missing_inputs_dry_run_fails_without_fitting(self):
        with tempfile.TemporaryDirectory(prefix='SYNTHETIC_missing_') as t:
            with patch.object(gen,'fit_estimator',side_effect=AssertionError('must not fit')),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(gen.main(['--dry-run','--acquisition-root',t]),2)
            self.assertEqual(list(Path(t).iterdir()),[])

    def test_execute_requires_all_explicit_arguments(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(gen.main(['--execute','--acquisition-root','.']),2)
