import unittest,copy,hashlib,tempfile,importlib.util
from stage2_fixture import *
from glucotwin.splits import make_splits,verify_splits
from glucotwin.contracts import ContractError
from glucotwin.preprocessing import construct_origins
from glucotwin.features import paired_features
class SplitTests(unittest.TestCase):
 def origins(self):return {p:[f'p{p}_o{x}' for x in range(3)] for p in [3,5,12,14]}
 def test_disjoint_outer_inner_membership(self):
  m=make_splits(self.origins());self.assertTrue(verify_splits(m,self.origins()));self.assertEqual(len(m['folds']),4)
 def test_overlap_and_hash_tampering_rejected(self):
  m=make_splits(self.origins());m['folds'][0]['train']['participants'].append(3)
  with self.assertRaises(ContractError):verify_splits(m,self.origins())
 def test_origin_collision_rejected(self):
  o=self.origins();o[5]=o[3]
  with self.assertRaises(ContractError):make_splits(o)
 def test_deterministic_synthetic_data_config_and_split_hashes(self):
  def generate():
   d=observed();o,_=construct_origins(d,baseline());s,c=paired_features(d,o,baseline());return [hashlib.sha256(x.encode()).hexdigest() for x in [s.to_csv(index=False),c.to_csv(index=False),json.dumps(config(),sort_keys=True),json.dumps(make_splits(self.origins()),sort_keys=True)]]
  self.assertEqual(generate(),generate())
 def test_public_review_allowlist_excludes_raw_and_feature_tables(self):
  spec=importlib.util.spec_from_file_location('package2',ROOT/'scripts/package_stage2.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for f in ['data/raw/person.csv','data/processed/stage2/sensor_only.csv','reports/stage2/eligibility_summary.csv','docs/stage2/data_contract.md','src/glucotwin/features.py']:
    p=root/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
   selected=[p.relative_to(root).as_posix() for p in mod.review_files(root)];self.assertFalse(any(p.startswith('data/') for p in selected));self.assertIn('reports/stage2/eligibility_summary.csv',selected);self.assertNotIn('data/processed/stage2/sensor_only.csv',selected)
