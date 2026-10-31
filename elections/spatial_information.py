"""Held-out prediction check: do population bins add information beyond design?

This supplementary diagnostic does not select thresholds and is not causal.
Training fits use development simulations only; test errors use held-out cities.
"""
from pathlib import Path
import numpy as np
import pandas as pd
from .spatial import OUT
from .spatial_runner import save


def analyze(output=OUT):
    output=Path(output)
    status={'status':'insufficient_evidence','method':'geographic_extended','interpretation':'Predictive contribution of population strata, not evidence that size causes ecological bias.'}
    metrics=output/'simulation_metrics.csv.gz'
    if not metrics.exists():
        save(output/'information_analysis.json',status);return status
    try:frame=pd.read_csv(metrics,low_memory=False)
    except pd.errors.EmptyDataError:
        save(output/'information_analysis.json',status);return status
    if frame.empty:
        save(output/'information_analysis.json',status);return status
    frame=frame[frame.method.eq('geographic_extended')&frame.support.eq('municipality')&frame.status.eq('ok')]
    sample=pd.read_csv(output/'sample.csv')
    target=frame.groupby(['phase','municipality_code','scenario','replicate','config']).mse_electorate_pp.mean().reset_index()
    target=target.merge(sample,on='municipality_code',validate='many_to_one')
    dev=target[target.phase.eq('development')].copy()
    test=target[target.phase.eq('validation')].copy()
    status.update(development_municipalities=int(dev.municipality_code.nunique()),heldout_municipalities=int(test.municipality_code.nunique()))
    if dev.municipality_code.nunique()<10 or test.municipality_code.nunique()<5:
        save(output/'information_analysis.json',status);return status

    def features(block,mode):
        minimum=block[[f'origin_{g}' for g in ['a','b','other','invalid','abstention']]].replace(0,np.nan).min(1)
        values=np.c_[np.log1p(block.sections),np.log1p(minimum),block.composition_sd,
            block.coordinate_coverage,np.log1p(block.median_neighbour_km),
            np.log1p(block.design_condition.fillna(1e6))]
        if mode=='bins':values=np.column_stack([values]+[block.population_bin.eq(b).astype(float) for b in range(2,6)])
        if mode=='continuous':values=np.c_[values,np.log(block.population)]
        return values
    scores={}
    # Same held-out rows for each model. Fixed ridge penalty, no test tuning.
    y=np.log1p(np.sqrt(dev.mse_electorate_pp.to_numpy()))
    truth=np.log1p(np.sqrt(test.mse_electorate_pp.to_numpy()))
    for mode in ['direct_information','bins','continuous']:
        a,b=features(dev,mode),features(test,mode)
        center,scale=a.mean(0),a.std(0)+1e-8
        a=np.c_[np.ones(len(a)),(a-center)/scale];b=np.c_[np.ones(len(b)),(b-center)/scale]
        penalty=np.eye(a.shape[1]);penalty[0,0]=0
        beta=np.linalg.solve(a.T@a+penalty,a.T@y)
        errors=(b@beta-truth)**2
        # Equal weight to each held-out municipality, not to its number of draws.
        by_city=pd.DataFrame({'code':test.municipality_code.to_numpy(),'error':errors}).groupby('code').error.mean()
        scores[mode]={'heldout_mean_log_rmse_prediction_mse':float(by_city.mean()),'municipalities':len(by_city)}
    status.update(status='evaluated',models=scores,bin_improvement=scores['direct_information']['heldout_mean_log_rmse_prediction_mse']-scores['bins']['heldout_mean_log_rmse_prediction_mse'],
        note='Supplementary fixed-penalty predictive comparison; uncertainty about transfer across municipalities remains. This is not an independent threshold-selection step.')
    save(output/'information_analysis.json',status);return status
