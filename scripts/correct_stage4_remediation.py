"""Final descriptive correction only; never refit models or overwrite original reports."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from glucotwin.stage4.evaluation import reconcile_glycemic_mae, compute_glycemic_slices
from glucotwin.stage4.adaptation import compute_median_residual_offset


def run():
    original = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (ROOT / 'reports/stage4').rglob('*') if p.is_file()}
    data = ROOT / 'data/processed/stage4'
    out = ROOT / 'reports/stage4_remediation'
    local = data / 'final_correction'
    local.mkdir(exist_ok=True)
    later = pd.read_csv(data / 'predictions/later_evaluation_predictions.csv')
    cal = pd.read_csv(data / 'predictions/calibration_predictions.csv')
    offsets = pd.read_csv(data / 'patient_offsets.csv').set_index('participant_id')
    signed = []
    summary = {}
    for variant in ['sensor_only', 'sensor_plus_baseline']:
        base = 'ridge_' + variant
        un, ad = base + '_unadapted', base + '_adapted'
        for pid, group in later.groupby('participant_id'):
            c = cal[cal.participant_id == pid]
            residual = c.target_mg_dl.to_numpy() - c[base].to_numpy()
            offset = compute_median_residual_offset(c.target_mg_dl, c[base])
            stored = offsets.loc[pid, 'offset_' + variant + '_mg_dl']
            np.testing.assert_allclose(offset, stored, rtol=0, atol=1e-10)
            e_un = (group[un] - group.target_mg_dl).to_numpy()
            e_ad = (group[ad] - group.target_mg_dl).to_numpy()
            np.testing.assert_allclose(e_ad, e_un + offset, rtol=0, atol=1e-10)
            signed.append(dict(participant_id=pid, variant=variant, n_calibration=len(c),
                               calibration_residual_mean=float(residual.mean()),
                               calibration_residual_median=float(np.median(residual)),
                               fixed_offset=offset, stored_offset=stored,
                               later_mean_signed_error_unadapted=float(e_un.mean()),
                               later_mean_signed_error_adapted=float(e_ad.mean()),
                               signed_identity_max_abs_error=float(np.max(np.abs(e_ad-e_un-offset)))))
        details, people, agg = reconcile_glycemic_mae(later, [un, ad])
        details.to_csv(local / f'{variant}_slice_evidence.csv', index=False)
        people.to_csv(local / f'{variant}_participant_reconciliation.csv', index=False)
        pivot = people.pivot(index='participant_id', columns='method')
        direct_delta = pivot['direct_mae'][ad] - pivot['direct_mae'][un]
        rebuilt_delta = pivot['reconstructed_mae'][ad] - pivot['reconstructed_mae'][un]
        np.testing.assert_allclose(direct_delta, rebuilt_delta, rtol=0, atol=1e-10)
        pd.DataFrame(dict(direct_delta=direct_delta, reconstructed_delta=rebuilt_delta)).to_csv(
            local / f'{variant}_participant_delta_reconciliation.csv')
        a = agg.set_index('method')
        contributions = details.groupby(['method', 'slice_name']).weighted_contribution.sum() / later.participant_id.nunique()
        slices = compute_glycemic_slices(later, ad, un)
        slices = slices.rename(columns={c: c.replace('_mse', '_mean_signed_error') for c in slices.columns})
        slices.to_csv(out / f'final_{variant}_slices.csv', index=False)
        summary[variant] = dict(n_participants=int(later.participant_id.nunique()), n_origins=len(later),
            unadapted_direct=float(a.loc[un, 'direct_mae']), unadapted_reconstructed=float(a.loc[un, 'reconstructed_mae']),
            adapted_direct=float(a.loc[ad, 'direct_mae']), adapted_reconstructed=float(a.loc[ad, 'reconstructed_mae']),
            delta_direct=float(direct_delta.mean()), delta_reconstructed=float(rebuilt_delta.mean()),
            max_participant_reconstruction_error=float(np.max(np.abs(people.direct_mae-people.reconstructed_mae))),
            max_participant_delta_error=float(np.max(np.abs(direct_delta-rebuilt_delta))),
            equal_person_slice_contributions={m: {s: float(v) for s, v in contributions.loc[m].items()} for m in [un, ad]},
            invalid_cohort_weighted_slice_estimate_unadapted=float((slices.pct_total_origins/100*slices.equal_person_mae_unadapted).sum()),
            invalid_cohort_weighted_slice_estimate_adapted=float((slices.pct_total_origins/100*slices.equal_person_mae_adapted).sum()))
    signed = pd.DataFrame(signed)
    signed.to_csv(local / 'signed_error_evidence.csv', index=False)
    for variant, group in signed.groupby('variant'):
        summary[variant]['signed_error'] = dict(
            unadapted_equal_person=float(group.later_mean_signed_error_unadapted.mean()),
            adapted_equal_person=float(group.later_mean_signed_error_adapted.mean()),
            mean_fixed_offset=float(group.fixed_offset.mean()),
            calibration_equal_person_residual_mean=float(group.calibration_residual_mean.mean()),
            calibration_mean_of_participant_medians=float(group.calibration_residual_median.mean()),
            participants_reduced_absolute_mean_signed_error=int((group.later_mean_signed_error_adapted.abs() < group.later_mean_signed_error_unadapted.abs()).sum()),
            max_origin_identity_error=float(group.signed_identity_max_abs_error.max()))
    assert original == {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (ROOT / 'reports/stage4').rglob('*') if p.is_file()}
    result = dict(scope='Descriptive Stage 4 final correction; no Stage 5 execution or model fitting',
                  tolerance_mg_dl=1e-10, original_stage4_reports_unchanged=True,
                  original_stage4_report_sha256=original, results=summary)
    (out / 'final_correction_aggregate.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    run()
