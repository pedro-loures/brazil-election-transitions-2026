"""Section-level generators, fixed-support scoring and conservative expansion gates."""
import numpy as np
import pandas as pd
from scipy.special import softmax
from scipy.stats import norm
from scipy.optimize import brentq

from .hierarchy_simulation import BASE
from .spatial import distances, partition
from .spatial_model import probability_chunks, context_design


def generate(x, administrative, coordinates, scenario, seed):
    """Grouping is downstream of this generator. Truth is never given to it."""
    rng=np.random.default_rng(seed)
    x=np.asarray(x,int).copy()
    points=np.asarray(coordinates,float).copy()
    if scenario=='sparse_origins':
        n=x.sum(1)
        x=np.array([rng.multinomial(int(v),[.4,.35,.001,.009,.24]) for v in n])
    baseline=np.log(BASE[:,:3]/BASE[:,3:])
    logits=np.broadcast_to(baseline,(len(x),5,3)).copy()
    rad=np.radians(points)
    center=rad.mean(0)
    xy=np.c_[(rad[:,1]-center[1])*np.cos(center[0]),rad[:,0]-center[0]]*6371.0088
    scale=np.std(xy,axis=0)+.1
    u=xy/scale
    if scenario in ['smooth','strong_spatial','coordinate_error']:
        strength=1.2 if scenario=='strong_spatial' else .5
        smooth=np.sin(u[:,0])+np.cos(u[:,1])
        logits[:,:,0]+=strength*smooth[:,None]
        logits[:,:,1]-=strength*smooth[:,None]
    elif scenario=='sharp_boundary':
        side=np.where(u[:,0]>=np.median(u[:,0]),1.,-1.)
        logits[:,:,0]+=side[:,None]
        logits[:,:,1]-=side[:,None]
    elif scenario in ['nonspatial','within_building']:
        logits+=rng.normal(0,.4,(administrative.max()+1,5,3))[administrative]
        if scenario=='within_building':
            logits+=rng.normal(0,.75,logits.shape)
    elif scenario=='contextual':
        c=context_design(x)
        logits[:,:,0]+=1.25*c[:,0,None]
        logits[:,:,1]-=1.25*c[:,0,None]
    elif scenario=='switching':
        logits[:,0,1]+=2.;logits[:,1,0]+=2.
    elif scenario not in ['homogeneous','sparse_origins','zero_flows']:
        raise ValueError('Unknown scenario: '+scenario)
    p=softmax(np.concatenate([logits,np.zeros((*logits.shape[:-1],1))],axis=-1),axis=-1)
    if scenario=='zero_flows':
        p[:,0,1]=p[:,1,0]=0.
        p/=p.sum(-1,keepdims=True)
    truth=x[:,:,None]*p
    table=np.empty_like(truth)
    for s in range(len(x)):
        for g in range(5):
            table[s,g]=rng.multinomial(int(x[s,g]),p[s,g])
    observed_points=points.copy()
    if scenario=='coordinate_error':
        # Five percent of whole sites misplaced; all co-located sections move together.
        sites,inverse=np.unique(points,axis=0,return_inverse=True)
        affected=rng.random(len(sites))<.05
        displacement=rng.normal(0,.025,sites.shape)*affected[:,None]
        observed_points+=displacement[inverse]
    return x,table.sum(1),truth,table,observed_points


def aggregate(values, labels):
    result=np.zeros((int(labels.max()+1),*values.shape[1:]))
    np.add.at(result,labels,values)
    return result


def flow_scores(draws, truth, origins, support, group_ids=None, point=None):
    """One row per estimand; absent origins stay unavailable, never zero rates."""
    draws=np.asarray(draws)
    estimate=draws.mean(0) if point is None else np.asarray(point)
    low,high,upper=np.quantile(draws,[.025,.975,.95],axis=0)
    rows=[]
    for unit in range(len(truth)):
        electorate=float(origins[unit].sum())
        for g in range(5):
            for k in range(4):
                origin=float(origins[unit,g])
                t=float(truth[unit,g,k])
                e=float(estimate[unit,g,k]-t)
                zero=t<1e-10 and origin>0
                rows.append({'support':support,'unit':int(unit) if group_ids is None else int(group_ids[unit]),
                    'origin':g,'destination':k,'electorate':electorate,'origin_voters':origin,
                    'truth':t,'estimate':float(estimate[unit,g,k]),'low':float(low[unit,g,k]),
                    'high':float(high[unit,g,k]),'error_voters':e,'error_electorate_pp':e/electorate*100,
                    'error_rate_pp':e/origin*100 if origin else None,
                    'width_rate_pp':float((high[unit,g,k]-low[unit,g,k])/origin*100) if origin else None,
                    'covered':bool(low[unit,g,k]-1e-10<=t<=high[unit,g,k]+1e-10),
                    'boundary_zero':zero,'upper95_rate_pp':float(upper[unit,g,k]/origin*100) if origin else None,
                    'boundary_false_positive':bool(zero and low[unit,g,k]>.01*origin),
                    'supported_origin':bool(origin>=100)})
    return rows


def score_posterior(posterior,x,model_group,truth,supports,extension=False,common=False):
    """Municipality, original places, sections and candidate groups; chunk sections."""
    from .spatial_model import flow_draws
    summaries=[]
    grouped=flow_draws(posterior,x,model_group,supports,extension,common)
    for name,draws in grouped.items():
        labels=supports[name]
        summaries.extend(flow_scores(draws,aggregate(truth,labels),aggregate(x,labels),name))
    for subset,p in probability_chunks(posterior,x,model_group,extension,common,chunk=64):
        summaries.extend(flow_scores(p*x[None,subset,:,None],truth[subset],x[subset],'section',
                                    np.arange(len(x))[subset]))
    return summaries


def summarize_dataset(rows):
    """Reduce places/cells within a dataset; MC independence is between datasets."""
    frame=pd.DataFrame(rows)
    summaries=[]
    for (support,g,k),block in frame.groupby(['support','origin','destination']):
        supported=block[block.supported_origin]
        interior=block[~block.boundary_zero & block.origin_voters.gt(0)]
        boundary=block[block.boundary_zero]
        summaries.append({'support':support,'origin':int(g),'destination':int(k),'units':len(block),
            'active_origin_units':int(block.origin_voters.gt(0).sum()),
            'bias_electorate_pp':float(block.error_electorate_pp.mean()),
            'mse_electorate_pp':float((block.error_electorate_pp**2).mean()),
            'mae_electorate_pp':float(block.error_electorate_pp.abs().mean()),
            'mse_rate_pp':float((supported.error_rate_pp**2).mean()) if len(supported) else None,
            'coverage':float(interior.covered.mean()) if len(interior) else None,
            'median_width_rate_pp':float(supported.width_rate_pp.median()) if len(supported) else None,
            'boundary_units':len(boundary),
            'boundary_false_positive_fraction':float(boundary.boundary_false_positive.mean()) if len(boundary) else None,
            'boundary_upper95_rate_pp':float(boundary.upper95_rate_pp.median()) if len(boundary) else None})
    return summaries


def mc_summary(frame):
    """Bounded-mean KL confidence bounds, allowing three planned MC looks.

    Hoeffding (1963), Theorem 1: independent [0,1] dataset summaries need not
    be identically distributed. Invert exp(-n*KL(q_hat || mean)). Allocate
    alpha across both tails and 100/500/1000 looks. Empirical MCSE is also
    reported; the gate uses an upper MCSE bound rather than zero at all-success.
    """
    values=np.asarray(frame,float)
    values=values[np.isfinite(values)]
    n=len(values)
    if not n:
        return {'n':0,'mean':None,'mcse':None,'mcse_empirical':None,'lower95':None,'upper95':None}
    if (values<0).any() or (values>1).any():raise ValueError('Coverage summaries must be in [0,1]')
    mean=float(values.mean())
    empirical=float(values.std(ddof=1)/np.sqrt(n)) if n>1 else None
    threshold=np.log(2*3/.05)/n
    if mean==1:
        lower,upper=float(np.exp(-threshold)),1.
    elif mean==0:
        lower,upper=0.,float(1-np.exp(-threshold))
    else:
        def divergence(p):
            return mean*np.log(mean/p)+(1-mean)*np.log((1-mean)/(1-p))-threshold
        lo,hi=np.nextafter(0.,1.),np.nextafter(1.,0.)
        with np.errstate(over='ignore',divide='ignore'):
            lower=float(brentq(divergence,lo,mean,xtol=1e-14)) if divergence(lo)>0 else 0.
            upper=float(brentq(divergence,mean,hi,xtol=1e-14)) if divergence(hi)>0 else 1.
        lower=max(0.,lower-1e-12);upper=min(1.,upper+1e-12)
    worst=float(np.clip(.5,lower,upper))
    se=float(np.sqrt(worst*(1-worst)/n))
    return {'n':n,'mean':mean,'mcse':se,'mcse_empirical':empirical,'lower95':lower,'upper95':upper,
            'bound':'Hoeffding binary-KL inversion; 95% family across three planned looks; MCSE is an upper bound'}


def gate_cell(summary,baseline,gate,phase='validation',replicates=0):
    legacy_empty=summary.coverage.isna() & summary.boundary_units.eq(0) & summary.mse_rate_pp.isna()
    empty=summary.active_origin_units.fillna((~legacy_empty).astype(int)).eq(0) if 'active_origin_units' in summary else legacy_empty
    if len(summary) and empty.all():
        return {'reasons':[],'not_applicable':True,'coverage':mc_summary([]),
                'rmse_electorate_pp':0.,'rmse_rate_pp':None,'median_width_rate_pp':None,'rmse_ratio':None,
                'note':'No voters in this origin: counts are structurally zero; transition rates and interval calibration are not applicable.'}
    reasons=[]
    if phase!='validation' or replicates<100:
        reasons.append('independent_validation_incomplete')
    coverage=mc_summary(summary.coverage)
    if coverage['mean'] is not None:
        if phase=='development' and coverage['mean']<gate['min_coverage_lower_mc_bound']:
            reasons.append('development_coverage_below_floor')
        elif phase!='development' and coverage['lower95']<gate['min_coverage_lower_mc_bound']:
            reasons.append('coverage_below_floor_or_unresolved')
        if coverage['mcse']>gate['max_coverage_mcse']:
            reasons.append('coverage_monte_carlo_imprecise')
    elif not summary.boundary_units.gt(0).any():
        reasons.append('coverage_unavailable')
    rmse=float(np.sqrt(summary.mse_electorate_pp.mean()))
    if rmse>gate['max_cell_rmse_electorate_pp']:
        reasons.append('absolute_flow_error')
    rate_rmse=float(np.sqrt(summary.mse_rate_pp.mean())) if summary.mse_rate_pp.notna().any() else None
    if rate_rmse is not None and rate_rmse>gate['max_rate_rmse_pp']:
        reasons.append('origin_rate_error')
    width=float(summary.median_width_rate_pp.median()) if summary.median_width_rate_pp.notna().any() else None
    if width is not None and width>gate['max_median_width_rate_pp']:
        reasons.append('interval_too_wide')
    ratio=None
    paired_datasets=0
    paired_fraction=None
    boundary_reference_zero=False
    if baseline is not None and len(baseline):
        keys=[k for k in ['replicate','municipality_code'] if k in summary and k in baseline]
        if keys:
            paired=summary[keys+['mse_electorate_pp']].merge(baseline[keys+['mse_electorate_pp']],on=keys,
                suffixes=('_new','_baseline'),validate='one_to_one')
            new_mse,old_mse=paired.mse_electorate_pp_new,paired.mse_electorate_pp_baseline
        else:
            if len(summary)!=len(baseline):raise ValueError('Unkeyed benchmark datasets cannot be paired')
            new_mse,old_mse=summary.mse_electorate_pp,baseline.mse_electorate_pp
        paired_datasets=len(new_mse);paired_fraction=paired_datasets/len(summary)
        if not paired_datasets:
            reasons.append('baseline_comparison_unavailable')
        else:
            numerator=float(np.sqrt(new_mse.mean()));denominator=float(np.sqrt(old_mse.mean()))
            boundary_reference_zero=bool(denominator<=1e-12 and summary.coverage.isna().all() and summary.boundary_units.gt(0).any())
            if not boundary_reference_zero:ratio=numerator/denominator if denominator else (1. if numerator==0 else float('inf'))
        if paired_fraction<.95:reasons.append('paired_benchmark_availability_below_95pct')
        if ratio is not None and ratio>gate['max_rmse_ratio']:
            reasons.append('worse_than_municipal_baseline')
    else:
        reasons.append('baseline_comparison_unavailable')
    if summary.boundary_units.gt(0).any():
        if summary.boundary_false_positive_fraction.mean()>.05:
            reasons.append('boundary_false_positives')
        if summary.boundary_upper95_rate_pp.median()>20:
            reasons.append('boundary_upper_limit_uninformative')
    return {'reasons':reasons,'coverage':coverage,'rmse_electorate_pp':rmse,'rmse_rate_pp':rate_rmse,
            'median_width_rate_pp':width,'rmse_ratio':ratio if ratio is not None and np.isfinite(ratio) else None,
            'paired_benchmark_datasets':paired_datasets,'paired_benchmark_fraction':paired_fraction,
            'boundary_zero_reference_error':boundary_reference_zero}
