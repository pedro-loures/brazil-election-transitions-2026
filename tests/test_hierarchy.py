"""Tests target the statistical quantities and geography, without long sampling."""
import numpy as np
import pytest

from elections.hierarchy import (column_moments, exact_margin_pmf, expected_flows,
                                likelihood_audit, validate_counts)
from elections.hierarchy_simulation import generate, score


def test_multinomial_column_moments_against_exact_margin_distribution():
    x=np.array([2,3,1,1,2])
    p=np.array([[.7,.1,.1,.1],[.1,.7,.1,.1],[.3,.4,.2,.1],
                [.3,.2,.4,.1],[.2,.1,.1,.6]])
    distribution=exact_margin_pmf(x,p)
    support=np.array(list(distribution));mass=np.array(list(distribution.values()))
    mean,covariance=column_moments(x,p)
    assert mass.sum()==pytest.approx(1.)
    assert np.allclose((mass[:,None]*support).sum(0),mean)
    centered=support-mean
    assert np.allclose(np.einsum('n,ni,nj->ij',mass,centered,centered),covariance)
    assert np.linalg.eigvalsh(covariance).min()>0


def test_expected_flow_draws_use_origin_weights_and_aggregate_before_quantiles():
    x=np.array([[100,0,0,0,0],[900,0,0,0,0]])
    p=np.zeros((2,2,5,4));p[:,:,:,3]=1
    p[0,0,0]=[1,0,0,0];p[0,1,0]=[0,1,0,0]
    p[1,0,0]=[0,1,0,0];p[1,1,0]=[1,0,0,0]
    local,municipal=expected_flows(x,np.array([0,1]),p)
    assert municipal[0,0,0]==100 and municipal[0,0,1]==900
    assert np.allclose(local.sum(1),municipal)
    assert np.allclose(municipal.sum(2),x.sum(0)[None])
    # Sum of marginal quantiles is not the quantile of the sum.
    assert np.quantile(local[:,:,0,0],.025,axis=0).sum()!=pytest.approx(np.quantile(municipal[:,0,0],.025))


def test_population_changes_and_place_label_gaps_are_rejected():
    x=np.ones((3,5))*20;y=np.ones((3,4))*25
    validate_counts(x,y,np.array([0,0,1]))
    y[0,0]+=1
    with pytest.raises(ValueError,match="equal positive"):
        validate_counts(x,y,np.array([0,0,1]))
    y[0,0]-=1
    with pytest.raises(ValueError,match="contiguous"):
        validate_counts(x,y,np.array([0,0,2]))


def test_simulated_tables_preserve_electorate_and_separate_truth_from_realization():
    rng=np.random.default_rng(4)
    x=rng.integers(5,100,(29,5));place=np.repeat(np.arange(10),3)[:29]
    for scenario in ["homogeneous","moderate","strong","contextual","within_place","weak_design","sparse","boundary","few_places"]:
        xx,y,pp,expected,realized=generate(x,place,scenario,77)
        assert np.array_equal(xx.sum(1),y.sum(1))
        assert np.allclose(expected.sum((0,2)),xx.sum(0))
        assert np.array_equal(realized.sum((0,2)),xx.sum(0))
        assert not np.allclose(expected,realized)
        if scenario=="boundary":
            assert np.all(expected[:,0,1]==0) and np.all(expected[:,1,0]==0)


def test_normal_likelihood_audit_exposes_small_count_error():
    rows=likelihood_audit()
    small=next(r for r in rows if r['kind']=='exact_four_destination' and r['N']==8)
    assert small['normalized_grid_total_variation']>.1
    assert small['mean_max_error']<1e-10


def test_normalized_matrix_distance_is_not_rate_difference():
    true=np.ones((5,4))*100
    estimate=true.copy();estimate[0,0]+=30;estimate[0,1]-=30
    assert score(estimate,true)['matrix_distance_to_truth']==pytest.approx(30/2000)


def test_cached_simulation_resume_exports_sparse_strata_without_refitting(tmp_path,monkeypatch):
    import json
    import pandas as pd
    import elections.hierarchy_simulation as simulation
    from elections.model import ORIGINS,DESTINATIONS
    manifest={'seed':17,'simulation':{'replicates':1,'scenarios':['homogeneous']}}
    monkeypatch.setattr(simulation,'prepare',lambda output:manifest)
    row={'uf':'SC','municipality_code':81914,'zone':77,'polling_place_1':1001}
    row.update({g+'_1':2 for g in ORIGINS})
    row.update({g+'_2':v for g,v in zip(DESTINATIONS,[2,3,1,4])})
    pd.DataFrame([row]).to_csv(tmp_path/'pilot_sections.csv.gz',index=False)
    folder=tmp_path/'simulations';folder.mkdir()
    metrics=[]
    for method,level,sparse in [('hierarchical','municipality',False),('municipal_baseline','municipality',False),
                                ('hierarchical','place',True),('independent_place','place',True)]:
        metrics.append(dict(method=method,level=level,sparse=sparse,scenario='homogeneous',replicate=0,
                            status='ok' if method!='independent_place' else 'too_few_sections',
                            coverage=.95,mae_electorate_pp=1.,rmse_electorate_pp=1.2,
                            width_electorate_pp=2.,abstention_to_a_bias_electorate_pp=.1))
    cached={'metrics':metrics,'flows':[{'origin_index':0,'destination_index':0,'true_expected_voters':2.,
              'true_realized_voters':3,'hierarchical_expected_voters':2.1,'baseline_expected_voters':2.2,'p025':1.,'p975':3.}]}
    (folder/'homogeneous-000.json').write_text(json.dumps(cached))
    def unexpected(*args,**kwargs):raise AssertionError('Cached repetitions must not refit')
    monkeypatch.setattr(simulation,'fit_hierarchy',unexpected)
    simulation.simulate(tmp_path)
    summary=pd.read_csv(tmp_path/'simulation_summary.csv')
    sparse=summary[summary['stratum'].eq('sparse')&summary.method.eq('independent_place')].iloc[0]
    assert sparse.unavailable_fraction==1.
    assert json.loads((tmp_path/'turnover_check.json').read_text())['unequal_population_rejected']
