"""Optional combined artifacts; failures remain local to the combined family."""
from dataclasses import replace
from pathlib import Path
import joblib
import numpy as np
from glucotwin.experiment.common import load,digest
from glucotwin.experiment.fusion import FEATURES,validate_baseline


def attach_fusion(source,pid,root):
    child=replace(source,model_family='baseline_sensor',fusion=None,expected=None,
                  artifact_reason='COMBINED_ARTIFACTS_UNAVAILABLE',baseline_context=None)
    try:
        root=Path(root);manifest=load(root/'manifest.json')
        names=[f'model_{pid:03d}.joblib',f'baseline_{pid:03d}.json','calibration.json','freeze.json','paired_summary.json']
        for name in names:
            if digest(root/name)!=manifest['files'][name]:raise ValueError('COMBINED_ARTIFACTS_INCOMPATIBLE')
        baseline=load(root/f'baseline_{pid:03d}.json');values=validate_baseline(baseline,pid)
        freeze=load(root/'freeze.json')
        if freeze['protocol']['features']!='21 existing sensor features followed by age,bmi,hba1c,fasting_glucose':raise ValueError('COMBINED_FEATURE_ORDER_INVALID')
        model,scaler=joblib.load(root/f'model_{pid:03d}.joblib')
        if model.n_features_in_!=25 or scaler.n_features_in_!=25:raise ValueError('COMBINED_DIMENSION_MISMATCH')
        if freeze['feature_order']!=FEATURES:raise ValueError('COMBINED_FEATURE_ORDER_INVALID')
        predictor=lambda x:model.predict(scaler.transform(np.column_stack((x,np.tile(values,(len(x),1))))))
        expected={f"{a['variant']}:{a['alpha']}":a for a in load(root/'calibration.json') if a['participant_id']==pid}
        if len(expected)!=4:raise ValueError('COMBINED_CALIBRATION_UNAVAILABLE')
        # This is study baseline context, not an EHR or verified longitudinal availability.
        context={k:v for k,v in baseline.items() if k!='participant_id'}
        context['study_results']=load(root/'paired_summary.json')
        return replace(child,predictor=predictor,expected=expected,artifact_reason='OK',baseline_context=context)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        reason=str(exc) if str(exc).startswith(('BASELINE_','COMBINED_')) else 'COMBINED_ARTIFACTS_UNAVAILABLE'
        return replace(child,artifact_reason=reason)
