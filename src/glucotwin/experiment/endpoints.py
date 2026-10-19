"""Freeze and evaluate endpoint flags on existing immutable held-out forecasts; zero fits."""
from pathlib import Path
import numpy as np
import pandas as pd
from .common import ROOT,load,write,digest,hashes,source_files,runtime,stamp,separate
from .verify import check_hashes,require
from .generate import csv as save_csv
from glucotwin.stage6.endpoint_flags import THRESHOLDS,metrics,ratio


def inputs(sensor,fusion):
    return {'sensor':Path(sensor)/'project/data/processed/stage5/evaluation.csv','fusion':Path(fusion)/'evaluation.csv'}

def freeze(sensor,sensor_trusted,fusion,fusion_trusted,output):
    sensor,fusion,output=Path(sensor).resolve(),Path(fusion).resolve(),Path(output).resolve()
    separate(output,sensor,fusion,ROOT)
    check_hashes(sensor,sensor_trusted)
    require(digest(fusion/'manifest.json')==fusion_trusted,'Endpoint fusion manifest pin')
    for name,h in load(fusion/'manifest.json')['files'].items():require(digest(fusion/name)==h,'Endpoint fusion bytes')
    protocol=load(ROOT/'configs/endpoint_protocol.json');require(tuple(protocol['thresholds_mg_dl'])==THRESHOLDS,'Endpoint frozen threshold contract')
    output.mkdir(parents=True)
    record=dict(kind='ENDPOINT_RESEARCH_FREEZE',frozen_at_utc=stamp(),sensor_bundle=str(sensor),fusion_bundle=str(fusion),sensor_manifest_sha256=sensor_trusted,fusion_manifest_sha256=fusion_trusted,
                source_sha256=hashes(ROOT,source_files()),runtime=runtime(),protocol=protocol,fits=0,
                input_sha256={k:digest(p) for k,p in inputs(sensor,fusion).items()})
    write(output/'freeze.json',record);return digest(output/'freeze.json')

def check_parents(f):
    sensor,fusion=Path(f['sensor_bundle']),Path(f['fusion_bundle'])
    check_hashes(sensor,f['sensor_manifest_sha256'])
    require(digest(fusion/'manifest.json')==f['fusion_manifest_sha256'],'Endpoint frozen fusion parent pin')
    manifest=load(fusion/'manifest.json')
    require(manifest['kind']=='FUSION_ARTIFACTS','Endpoint fusion parent kind')
    for name,h in manifest['files'].items():require(digest(fusion/name)==h,'Endpoint frozen fusion bytes')
    require(load(fusion/'freeze.json')['parent_manifest_sha256']==f['sensor_manifest_sha256'],'Endpoint fusion/sensor parent identity')


def read_rows(f):
    frames=[]
    for key,path in inputs(f['sensor_bundle'],f['fusion_bundle']).items():
        require(digest(path)==f['input_sha256'][key],'Endpoint input freeze changed')
        allrows=pd.read_csv(path,dtype={'alpha':str},float_precision='round_trip')
        require(set(allrows.alpha)=={'0.05','0.10'},'Endpoint interval level completeness')
        keys=['participant_id','variant','scenario','issue_time']
        a=allrows[allrows.alpha.eq('0.05')].sort_values(keys);b=allrows[allrows.alpha.eq('0.10')].sort_values(keys)
        require(not a.duplicated(keys).any() and not b.duplicated(keys).any(),'Endpoint unique scheduled decisions')
        require(list(map(tuple,a[keys].to_numpy()))==list(map(tuple,b[keys].to_numpy())),'Endpoint interval-level origin identity')
        require(list(a.point_reason)==list(b.point_reason) and list(a.clean_eligible)==list(b.clean_eligible),'Endpoint point availability independent of interval level')
        require(np.allclose(a.prediction,b.prediction,rtol=0,atol=1e-8,equal_nan=True),'Point forecasts differ between nominal levels')
        require(np.allclose(a.target,b.target,rtol=0,atol=1e-8,equal_nan=True),'Endpoint target identity')
        require(not ((a.point_reason.eq('OK')&np.isfinite(a.prediction)&np.isfinite(a.target))&~a.clean_eligible).any(),'Endpoint scorable origins must belong to frozen later evaluation')
        frames.append(a)
    return pd.concat(frames,ignore_index=True)

def execute(freeze_path,trusted,output):
    f=load(freeze_path);output=Path(output).resolve()
    require(digest(freeze_path)==trusted,'Endpoint freeze pin');require(hashes(ROOT,f['source_sha256'])==f['source_sha256'] and runtime()==f['runtime'],'Endpoint frozen source/runtime')
    separate(output,Path(f['sensor_bundle']).resolve(),Path(f['fusion_bundle']).resolve(),Path(freeze_path).resolve().parent,ROOT)
    require(f['kind']=='ENDPOINT_RESEARCH_FREEZE' and f['fits']==0,'Endpoint zero-fit freeze kind')
    check_parents(f)
    output.mkdir(parents=True);write(output/'freeze.json',f)
    try:
        rows=read_rows(f);people=[]
        for (pid,variant,scenario),group in rows.groupby(['participant_id','variant','scenario']):
            for threshold in THRESHOLDS:
                m=metrics(group.prediction,group.target,group.point_reason,threshold)
                m.update(participant_id=int(pid),variant=variant,scenario=scenario,threshold_mg_dl=threshold,clean_eligible_origins=int(group.clean_eligible.sum()))
                people.append(m)
        per=pd.DataFrame(people);save_csv(output/'participants.csv',per)
        summaries=[]
        for (variant,scenario,threshold),group in per.groupby(['variant','scenario','threshold_mg_dl']):
            counts={n:int(group[n].sum()) for n in ['TP','FP','TN','FN','scheduled','issued','suppressed','scorable','missing_target','issued_missing_target','observed_positive_targets','scorable_positive_targets','clean_eligible_origins']}
            macro={};contributing={}
            for name in ('precision','recall','specificity'):
                defined=group[name].dropna();macro[name]=float(defined.mean()) if len(defined) else None;contributing[name]=len(defined)
            tp,fp,tn,fn=(counts[k] for k in ['TP','FP','TN','FN'])
            summaries.append(dict(analysis_role='primary' if scenario=='clean' and variant==f['protocol']['primary_variant'] else 'secondary',variant=variant,scenario=scenario,threshold_mg_dl=int(threshold),participants=len(group),participants_with_scorable_positive_targets=int((group.scorable_positive_targets>0).sum()),counts=counts,
                pooled=dict(precision=ratio(tp,tp+fp),recall=ratio(tp,tp+fn),specificity=ratio(tn,tn+fp)),macro=macro,contributing_participants=contributing,
                endpoint_only=True,lead_time='NOT_APPLICABLE',false_alarms_per_day='NOT_REPORTED',note='Exploratory dependent endpoint decisions; sparse-positive groups do not establish validation'))
        write(output/'summary.json',summaries)
        write(output/'manifest.json',dict(kind='ENDPOINT_RESEARCH_RESULTS',fits=0,freeze_sha256=trusted,files={p.name:digest(p) for p in output.iterdir() if p.is_file()}))
        return digest(output/'manifest.json')
    except Exception as exc:write(output/'failure.json',dict(error=repr(exc),at=stamp()));raise

def verify(output,trusted):
    output=Path(output);require(digest(output/'manifest.json')==trusted,'Endpoint result manifest pin');manifest=load(output/'manifest.json')
    for name,h in manifest['files'].items():require(digest(output/name)==h,'Endpoint result bytes')
    require(digest(output/'freeze.json')==manifest['freeze_sha256'],'Endpoint result freeze')
    f=load(output/'freeze.json');require(tuple(f['protocol']['thresholds_mg_dl'])==THRESHOLDS,'Endpoint threshold freeze');require(manifest['kind']=='ENDPOINT_RESEARCH_RESULTS' and manifest['fits']==f['fits']==0,'Endpoint result kind/fits');check_parents(f);rows=read_rows(f);per=pd.read_csv(output/'participants.csv');summary=load(output/'summary.json')
    require(set(rows.variant)==set([f['protocol']['primary_variant']]+f['protocol']['secondary_variants']),'Endpoint model coverage')
    require(len(set(rows.participant_id))==14,'Endpoint frozen cohort completeness')
    require(len(per)==14*4*5*2 and len(summary)==4*5*2,'Endpoint expected case completeness')
    checked=0
    for record in per.itertuples():
        group=rows[rows.participant_id.eq(record.participant_id)&rows.variant.eq(record.variant)&rows.scenario.eq(record.scenario)]
        counts=dict(TP=0,FP=0,TN=0,FN=0,issued=0,scorable=0,missing_target=0,issued_missing_target=0)
        for pred,target,reason in zip(group.prediction,group.target,group.point_reason):
            point=reason=='OK' and np.isfinite(pred);observed=np.isfinite(target)
            counts['issued']+=int(point);counts['missing_target']+=int(not observed);counts['issued_missing_target']+=int(point and not observed)
            if not (point and observed):continue
            counts['scorable']+=1;flag=pred>record.threshold_mg_dl;actual=target>record.threshold_mg_dl
            key='TP' if flag and actual else 'FP' if flag else 'FN' if actual else 'TN';counts[key]+=1
        for key,value in counts.items():require(getattr(record,key)==value,'Independent endpoint confusion/denominator')
        require(record.scheduled==len(group) and record.suppressed==len(group)-counts['issued'],'Endpoint scheduled/suppression count')
        require(record.observed_positive_targets==sum(np.isfinite(t) and t>record.threshold_mg_dl for t in group.target),'Endpoint observed positives')
        require(record.scorable_positive_targets==counts['TP']+counts['FN'],'Endpoint scorable positives')
        require(record.clean_eligible_origins==int(group.clean_eligible.sum()),'Endpoint eligible origins')
        for name,n,d in [('precision',counts['TP'],counts['TP']+counts['FP']),('recall',counts['TP'],counts['TP']+counts['FN']),('specificity',counts['TN'],counts['TN']+counts['FP'])]:
            value=getattr(record,name);require(pd.isna(value) if d==0 else abs(value-n/d)<1e-12,'Independent endpoint metric')
        checked+=1
    for item in summary:
        group=per[per.variant.eq(item['variant'])&per.scenario.eq(item['scenario'])&per.threshold_mg_dl.eq(item['threshold_mg_dl'])]
        for key,value in item['counts'].items():require(value==int(group[key].sum()),'Endpoint aggregate counts')
        require(item['participants']==len(group) and item['participants_with_scorable_positive_targets']==int((group.scorable_positive_targets>0).sum()),'Endpoint participant denominators')
        for name,numerator,denominator in [('precision','TP',('TP','FP')),('recall','TP',('TP','FN')),('specificity','TN',('TN','FP'))]:
            d=sum(item['counts'][k] for k in denominator);expected=None if not d else item['counts'][numerator]/d;value=item['pooled'][name]
            require(value is None if expected is None else abs(value-expected)<1e-12,'Independent pooled endpoint metric')
        for name in ['precision','recall','specificity']:
            defined=group[name].dropna();value=item['macro'][name]
            require(item['contributing_participants'][name]==len(defined),'Endpoint defined participant count')
            require(value is None if not len(defined) else abs(value-defined.mean())<1e-12,'Endpoint macro participant metric')
    return dict(status='PASS',verified_at_utc=stamp(),participant_model_scenario_threshold_cases=checked,fits=0,artifact_manifest_sha256=trusted)
