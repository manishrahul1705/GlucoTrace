"""Bounded authored engineering scenarios, independent of research artifacts."""
from dataclasses import replace
import numpy as np
from .sources import synthetic,Reading

CATALOG={
 'clean':('Scripted day','Original seeded demonstration with authored rises and variation.'),
 'steady':('Steady baseline','Small observation noise around a constant authored baseline.'),
 'meal':('Scripted rise & recovery','Authored meal-related rise and recovery; not validated physiology.'),
 'activity':('Activity variation','An authored downward variation and return; no treatment simulation.'),
 'noisy':('Noisy observations','Independent observation noise around an authored baseline.'),
 **{f'dropout{n}':(f'{n}-minute simulated input dropout',f'Original scripted signal with {n} minutes of simulated input dropout; evaluator targets retained.') for n in [15,30,60,120]}
}

def make_scenario(scenario='clean',seed=1705,duration_minutes=720):
    if scenario not in CATALOG or type(seed) is not int or not 0<=seed<=2147483647:
        raise ValueError('INVALID_SCENARIO_CONFIGURATION')
    if type(duration_minutes) is not int or not 360<=duration_minutes<=1440 or duration_minutes%5:
        raise ValueError('INVALID_SCENARIO_DURATION')
    source=synthetic(scenario if scenario.startswith('dropout') else 'clean',seed,duration_minutes+1)
    version='scripted-v1' if scenario=='clean' or scenario.startswith('dropout') else 'scenario-lab-v1'
    if scenario in ['steady','meal','activity','noisy']:
        rng=np.random.default_rng(seed);t=np.arange(duration_minutes+1,dtype=float)
        values=110+rng.normal(0,4 if scenario=='noisy' else .35,len(t))
        if scenario=='meal':
            pulse=np.maximum(t-75,0)/32;values+=55*pulse*np.exp(1-pulse)*(t>=75)
        if scenario=='activity':values-=18*np.exp(-((t-180)/45)**2)
        source=replace(source,readings=tuple(Reading(f'syn-{i:05d}',i,float(v),True) for i,v in enumerate(values)),reference={i:float(v) for i,v in enumerate(values)},gap=None)
    config=dict(scenario=scenario,name=CATALOG[scenario][0],description=CATALOG[scenario][1],seed=seed,
                generator_version=version,duration_minutes=duration_minutes,
                input_loss_minutes=int(scenario[7:]) if scenario.startswith('dropout') else 0,
                predictor='persistence',provenance='independent authored synthetic engineering scenario',units='mg/dL')
    return replace(source,configuration=config)
