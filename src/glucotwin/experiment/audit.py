"""New Stage 1 audits, derived from observations without expected-total constants."""
import numpy as np
import pandas as pd


def audit_stream(stream, participant):
    """Inclusive 61-cell history, exact target, strict crossing and 30/15 episodes.

    This is intentionally separate from labels.event_labels and its vectorized
    implementation. All intervals are elapsed minute positions, including gaps.
    """
    if not stream.index.equals(pd.date_range(stream.index[0], periods=len(stream), freq='min')):
        raise ValueError('Audit requires a complete elapsed minute index')
    g = stream.glucose_mg_dl.to_numpy(float)
    valid = stream.valid.to_numpy(bool) & np.isfinite(g) & (g >= 40) & (g <= 400)
    n = len(g)
    eligible = sum(bool(valid[t-60:t+1].all() and valid[t+30]) for t in range(60, n-30))
    windows = [dict(participant=participant, sensor='Dexcom GL', history_minutes=60,
                    horizon_minutes=30, max_missing_run_minutes=0, eligible_origins=eligible)]
    events = []
    for threshold in (180, 250):
        crossings = sum(bool(valid[t:t+31].all() and g[t] <= threshold and
                             (g[t+1:t+31] > threshold).any()) for t in range(n-30))
        episodes = sum(bool(valid[s-30:s+15].all() and (g[s-30:s] <= threshold).all() and
                            (g[s:s+15] > threshold).all()) for s in range(30, n-14))
        events.append(dict(participant=participant, sensor='Dexcom GL', threshold_mg_dl=threshold,
                           horizon_minutes=30, new_crossing_positive_origins=crossings,
                           independent_episodes_30min_recovery=episodes))
    return windows, events
