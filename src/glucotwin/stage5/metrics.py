"""Participant-first and pooled summaries with explicit availability denominators."""
import numpy as np
import pandas as pd


def summarize(rows, n_expected_participants):
    """Rows represent all scheduled origins for one scenario/variant/level/slice."""
    point = rows.point_reason.eq('OK') & np.isfinite(rows.prediction)
    interval = point & rows.interval_reason.eq('OK') & np.isfinite(rows.lower) & np.isfinite(rows.upper)
    target = np.isfinite(rows.target)
    scored = point & target
    interval_scored = interval & target
    people = []
    for pid, group in rows.groupby('participant_id'):
        idx = group.index
        p, q = group.loc[scored.loc[idx]], group.loc[interval_scored.loc[idx]]
        error = p.prediction-p.target
        covered = (q.lower <= q.target) & (q.target <= q.upper)
        people.append(dict(participant_id=pid, n_point_scored=len(p), n_interval_scored=len(q),
                           mae=error.abs().mean(), rmse=np.sqrt((error**2).mean()),
                           mean_signed_error=error.mean(), empirical_coverage=covered.mean() if len(q) else np.nan,
                           mean_width=(q.upper-q.lower).mean()))
    per = pd.DataFrame(people, columns=['participant_id', 'n_point_scored', 'n_interval_scored',
                                       'mae', 'rmse', 'mean_signed_error', 'empirical_coverage', 'mean_width'])
    p, q = rows.loc[scored], rows.loc[interval_scored]
    e = p.prediction-p.target
    covered = (q.lower <= q.target) & (q.target <= q.upper)
    records = []
    for weighting in ['equal_participant', 'pooled_window']:
        record = dict(weighting=weighting, n_expected_participants=n_expected_participants,
                      n_scheduled=len(rows), n_eligible=int(rows.clean_eligible.sum()),
                      n_issued=int(point.sum()), n_target_available=int(target.sum()),
                      n_interval_available=int(interval.sum()), n_point_scored=int(scored.sum()),
                      n_interval_scored=int(interval_scored.sum()),
                      contributing_point_participants=int((per.n_point_scored > 0).sum()),
                      contributing_interval_participants=int((per.n_interval_scored > 0).sum()))
        record['absent_point_participants'] = n_expected_participants-record['contributing_point_participants']
        record['absent_interval_participants'] = n_expected_participants-record['contributing_interval_participants']
        for key in ['mae','rmse','mean_signed_error','empirical_coverage','mean_width']:
            if weighting == 'equal_participant':
                record[key] = float(per[key].mean())
            else:
                values = dict(mae=e.abs().mean(), rmse=np.sqrt((e**2).mean()), mean_signed_error=e.mean(),
                              empirical_coverage=covered.mean() if len(q) else np.nan, mean_width=(q.upper-q.lower).mean())
                record[key] = float(values[key])
        for metric in ['empirical_coverage', 'mean_width']:
            record['participant_'+metric+'_min'] = float(per[metric].min())
            record['participant_'+metric+'_max'] = float(per[metric].max())
        records.append(record)
    return pd.DataFrame(records), per


def slice_masks(rows):
    return {'all': pd.Series(True, index=rows.index), 'below70': rows.target < 70,
            '70to180': rows.target.between(70,180), 'above180': rows.target > 180}
