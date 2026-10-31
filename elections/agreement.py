"""Paired resampling and fixed-support model-agreement diagnostics."""
from itertools import combinations
import numpy as np
from .agreement_model import FAMILIES
from .spatial import partition, distances


def building_weights(x,coordinates,seed):
    """Size-stratified whole-building bootstrap; preserve paired round records."""
    _,site=np.unique(coordinates,axis=0,return_inverse=True)
    n=site.max()+1
    sizes=np.bincount(site,weights=x.sum(1))
    order=np.argsort(sizes,kind='stable')
    strata=np.array_split(order,2) if n>=4 else [order]
    rng=np.random.default_rng(seed);counts=np.zeros(n,int)
    for members in strata:
        sampled=rng.choice(members,size=len(members),replace=True)
        counts+=np.bincount(sampled,minlength=n)
    return counts[site]


def resampled_groups(coordinates,weight,target=10,cap=5.):
    """Rebuild geographic partition; omitted buildings get unobserved groups.

    Counts influence the soft target via replicated whole-site observations.
    Omitted buildings are never silently attached to distant retained groups.
    Their parameters are predicted from the municipal/group prior.
    """
    weight=np.asarray(weight,int)
    if (weight<0).any() or not weight.sum():raise ValueError('Empty or invalid resample')
    index=np.repeat(np.arange(len(weight)),weight)
    groups=partition(np.asarray(coordinates)[index],target,cap)
    out=np.full(len(weight),-1,int)
    out[index]=groups
    # Co-located omitted sections share a physical building and must share label.
    next_label=int(groups.max()+1)
    for site in np.unique(np.asarray(coordinates)[out<0],axis=0):
        match=np.all(np.asarray(coordinates)==site,axis=1)
        retained=out[match];retained=retained[retained>=0]
        out[match]=retained[0] if len(retained) else next_label
        if not len(retained):next_label+=1
    return np.unique(out,return_inverse=True)[1]


def maximum_agreeing_subsets(available,compatible):
    """Return every tied maximum clique; never choose a favourable tie silently."""
    names=sorted(available)
    for size in range(len(names),0,-1):
        hits=[list(c) for c in combinations(names,size) if all(compatible(a,b) for a,b in combinations(c,2))]
        if hits:return hits
    return []


def flow_agreement(estimates,origin,electorate,origin_index,destination):
    """Point-estimate agreement. Fit quality remains a separate gate."""
    available={k:float(v) for k,v in estimates.items() if v is not None and np.isfinite(v)}
    pairwise=[];support=origin>=100
    key_flow=origin_index in [3,4] and destination in [0,1]
    for a,b in combinations(sorted(available),2):
        count=abs(available[a]-available[b]);rate=100*count/origin if origin else None
        pairwise.append({'first':a,'second':b,'difference_voters':count,'difference_rate_pp':rate,
            'difference_electorate_pp':100*count/electorate,
            'agrees':bool(support and rate<=10 and (not key_flow or count/electorate<=.02))})
    lookup={(r['first'],r['second']):r['agrees'] for r in pairwise}
    subsets=maximum_agreeing_subsets(available,lambda a,b:lookup.get(tuple(sorted((a,b))),False)) if support else []
    return {'available_models':sorted(available),'unavailable_models':sorted(set(FAMILIES)-set(available)),
        'expected_models':len(FAMILIES),'supported_origin':bool(support),'pairwise':pairwise,
        'maximum_subsets':subsets,'agreeing_models':len(subsets[0]) if subsets else None,
        'range_rate_pp':100*(max(available.values())-min(available.values()))/origin if available and origin else None,
        'range_voters':max(available.values())-min(available.values()) if available else None,
        'agreement_is_accuracy':False}


def matrix_comparisons(matrices,electorate):
    return [{'first':a,'second':b,'allocation_distance':float(np.abs(matrices[a]-matrices[b]).sum()/(2*electorate))}
            for a,b in combinations(sorted(matrices),2)]


def cluster_stability(reference,resampled,observed=None):
    """Label-invariant Jaccard matches; omit predictions for out-of-bag sites."""
    reference=np.asarray(reference);resampled=np.asarray(resampled)
    mask=np.ones(len(reference),bool) if observed is None else np.asarray(observed,bool)
    result=[]
    for label in np.unique(reference):
        original=(reference==label)&mask
        if not original.any():
            result.append({'reference_cluster':int(label),'jaccard':None});continue
        best=0.
        for match in np.unique(resampled[mask]):
            candidate=(resampled==match)&mask
            best=max(best,float((original&candidate).sum()/(original|candidate).sum()))
        result.append({'reference_cluster':int(label),'jaccard':best})
    return result
