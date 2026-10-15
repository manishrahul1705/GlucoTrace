"""Participant-only nested membership manifests; no model or tuning execution."""
import hashlib,json
from .contracts import ContractError

def ids_hash(ids):return hashlib.sha256(('\n'.join(sorted(map(str,ids)))+'\n').encode()).hexdigest()
def make_splits(origin_ids_by_participant):
 ids=sorted(origin_ids_by_participant)
 if len(ids)<4 or any(not origin_ids_by_participant[p] for p in ids):raise ContractError('Need >=4 participants with paired origins')
 sets={p:set(origin_ids_by_participant[p]) for p in ids}
 if sum(len(x) for x in sets.values())!=len(set().union(*sets.values())):raise ContractError('Origin IDs collide across participants')
 def part(ps):
  os=[o for p in ps for o in origin_ids_by_participant[p]];return {'participants':ps,'n_origins':len(os),'origin_ids_sha256':ids_hash(os)}
 folds=[]
 for test in ids:
  train=[p for p in ids if p!=test];inners=[]
  for k in range(3):
   val=train[k::3];tr=[p for p in train if p not in val];inners.append({'fold':k,'train':part(tr),'validation':part(val)})
  folds.append({'outer_fold':f'holdout_{test:03d}','train':part(train),'test':part([test]),'inner_folds':inners})
 return {'protocol':'stage2-v1','outer_scheme':'LOPO','inner_scheme':'3-fold sorted participant round-robin','eligible_participants':ids,'feature_variants':['sensor_only','sensor_plus_baseline'],'shared_paired_origins':True,'folds':folds}

def verify_splits(manifest,origins):
 ids=set(origins);seen=[]
 for fold in manifest['folds']:
  tr=set(fold['train']['participants']);te=set(fold['test']['participants'])
  if tr&te or tr|te!=ids:raise ContractError('Outer participant leakage/omission')
  seen.extend(te);val_seen=[]
  for inner in fold['inner_folds']:
   it=set(inner['train']['participants']);iv=set(inner['validation']['participants'])
   if it&iv or it|iv!=tr or (it|iv)&te:raise ContractError('Inner participant leakage/omission')
   val_seen.extend(iv)
  if sorted(val_seen)!=sorted(tr):raise ContractError('Inner validation membership not exactly once')
  for part in [fold['train'],fold['test']]+[x[k] for x in fold['inner_folds'] for k in ['train','validation']]:
   actual=[o for p in part['participants'] for o in origins[p]]
   if part['origin_ids_sha256']!=ids_hash(actual) or part['n_origins']!=len(actual):raise ContractError('Origin membership hash/count mismatch')
 if sorted(seen)!=sorted(ids):raise ContractError('Outer test not exactly once')
 return True
