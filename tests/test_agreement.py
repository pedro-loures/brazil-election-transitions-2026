import json
import numpy as np
import pytest
from elections.agreement import building_weights,resampled_groups,flow_agreement,cluster_stability,matrix_comparisons
from elections.agreement_model import responsibilities


def test_agreement_requires_all_pairs_and_preserves_ties():
    r=flow_agreement({'municipal':0,'geographic':8,'behavioural':16,'combined':8},100,1000,0,0)
    assert r['agreeing_models']==3
    assert {frozenset(c) for c in r['maximum_subsets']}=={
        frozenset(['municipal','geographic','combined']),frozenset(['behavioural','geographic','combined'])}
    assert not r['agreement_is_accuracy']


def test_missing_and_sparse_origins_cannot_manufacture_agreement():
    r=flow_agreement({'municipal':10,'geographic':10,'behavioural':np.nan},100,1000,0,0)
    assert r['agreeing_models']==2
    assert len(r['unavailable_models'])==2 and r['expected_models']==4
    sparse=flow_agreement(dict.fromkeys(['municipal','geographic','behavioural','combined'],1.),20,100,0,0)
    assert sparse['agreeing_models'] is None and sparse['maximum_subsets']==[]


def test_key_flow_tolerance_uses_both_origin_and_electorate():
    r=flow_agreement({'municipal':0,'geographic':30},1000,1000,4,0)
    assert r['pairwise'][0]['difference_rate_pp']==3
    assert not r['pairwise'][0]['agrees']


def test_building_resampling_preserves_colocation_and_is_reproducible():
    points=np.array([[0,0],[0,0],[0,.01],[0,.02],[0,.03],[0,.03]])
    x=np.arange(30).reshape(6,5)+1
    a=building_weights(x,points,11);b=building_weights(x,points,11)
    assert np.array_equal(a,b)
    assert a[0]==a[1] and a[4]==a[5]
    assert np.all(a>=0)


def test_rebuilt_groups_keep_omitted_buildings_and_enforce_distance_cap():
    p=np.array([[0,0],[0,0],[0,.01],[0,2]])
    labels=resampled_groups(p,[2,2,0,0],10,5)
    assert labels[0]==labels[1]
    assert labels[2]!=labels[0] and labels[3]!=labels[0]
    assert np.array_equal(np.unique(labels),np.arange(labels.max()+1))
    with pytest.raises(ValueError):resampled_groups(p,[0,0,0,0])


def test_cluster_stability_ignores_arbitrary_label_names():
    assert all(r['jaccard']==1 for r in cluster_stability([0,0,1,1],[4,4,9,9]))
    r=cluster_stability([0,0,1,1],[4,4,9,9],[1,1,0,0])
    assert r[0]['jaccard']==1 and r[1]['jaccard'] is None


def test_omitted_outcomes_do_not_affect_component_membership():
    p=np.array([[[[[.8,.1,.05,.05]]*5,[[.1,.8,.05,.05]]*5]]])
    x=np.array([[10]*5]);rho=np.array([.01]);mix=np.array([.7])
    a=responsibilities(p,x,np.array([[40,5,2,3]]),rho,mix,[False])
    b=responsibilities(p,x,np.array([[5,40,2,3]]),rho,mix,[False])
    assert np.allclose(a,b)
    assert np.allclose(a[0,0],[1/(1+np.exp(.7)),1/(1+np.exp(-.7))])
    observed=responsibilities(p,x,np.array([[40,5,2,3]]),rho,mix,[True])
    assert observed[0,0,0]>.99


def test_matrix_distance_is_allocation_disagreement_not_accuracy():
    a=np.ones((5,4))*5;b=a.copy();b[0,0]+=2;b[0,1]-=2
    rows=matrix_comparisons({'municipal':a,'geographic':b},100)
    assert rows[0]['allocation_distance']==pytest.approx(.02)


def test_job_grid_uses_frozen_splits_and_shared_cases():
    from elections.agreement_runner import jobs_for
    m={'sample':[{'municipality_code':10*b+i,'population_bin':b,'split':split,'sites':3}
                  for b in range(1,6) for i,split in enumerate(['development','validation'])],
       'development_replicates':30,'scenarios':['contextual']}
    jobs=jobs_for(m,'development')
    assert len(jobs)==5*30*5
    assert all(j['municipality_code']%10==0 for j in jobs)
    val=jobs_for(m,'validation',100)
    assert len(val)==5*100*5 and all(j['municipality_code']%10==1 for j in val)


def test_reject_validation_data_in_development_job_before_source_read():
    from elections.agreement_runner import case_data
    m={'sample':[{'municipality_code':1,'population_bin':1,'split':'validation'}]}
    with pytest.raises(ValueError,match='split'):
        case_data(m,{'municipality_code':1,'population_bin':1,'phase':'development'})
