import numpy as np
import pandas as pd
import pytest

from elections.spatial import distances, partition, diameter, group_inventory, select_sample, seed_for
from elections.spatial_model import margin_moments, context_design, probability_chunks, flow_draws
from elections.spatial_validation import generate, aggregate, flow_scores, mc_summary, summarize_dataset, gate_cell
from elections.spatial_runner import config_parts


def example():
    rng=np.random.default_rng(42)
    x=np.array([rng.multinomial(300,[.35,.32,.08,.05,.2]) for _ in range(16)])
    points=np.array([[-23.+i*.003,-46.] for i in range(8) for _ in range(2)])
    admin=np.repeat(np.arange(8),2)
    return x,points,admin


def test_distance_units_and_symmetry():
    assert distances([0,0],[0,1])==pytest.approx(111.195,abs=.01)
    assert distances([-23,-46],[-23,-46])==0
    assert distances([-90,0],[90,0])==pytest.approx(np.pi*6371.0088)


def test_grouping_respects_diameter_colocation_and_determinism():
    x,points,_=example()
    labels=partition(points,5,1)
    assert np.array_equal(labels,partition(points,5,1))
    assert all(labels[i]==labels[i+1] for i in range(0,16,2))
    for label in np.unique(labels):assert diameter(points[labels==label])<=1+1e-8
    info=group_inventory(x,points,labels,5,1)
    assert sum(v['electorate'] for v in info)==x.sum()
    assert sum(v['sections'] for v in info)==16


def test_geographically_isolated_sections_are_not_forced_together():
    points=np.array([[0,0],[0,2],[0,4]])
    labels=partition(points,160,50)
    assert len(np.unique(labels))==3


def test_oversized_building_stays_whole():
    labels=partition(np.tile([-23.,-46.],(37,1)),5,1)
    assert np.all(labels==0)


def test_grouping_permutation_invariance():
    _,points,_=example()
    original=partition(points,5,1)
    order=np.random.default_rng(9).permutation(len(points))
    shuffled=partition(points[order],5,1)
    assert np.array_equal(shuffled,original[order])


def test_invalid_coordinates_rejected():
    with pytest.raises(ValueError):partition([[np.nan,1]],5,1)


@pytest.mark.parametrize('scenario',['homogeneous','smooth','strong_spatial','sharp_boundary','nonspatial',
    'within_building','contextual','sparse_origins','switching','zero_flows','coordinate_error'])
def test_generators_conserve_population_and_are_reproducible(scenario):
    x,points,admin=example()
    generated=generate(x,admin,points,scenario,123)
    other=generate(x,admin,points,scenario,123)
    for a,b in zip(generated,other):assert np.array_equal(a,b)
    xx,y,truth,realized,_=generated
    assert np.array_equal(xx.sum(1),y.sum(1))
    assert np.allclose(truth.sum(2),xx)
    assert np.allclose(realized.sum(2),xx)
    if scenario=='zero_flows':assert np.all(truth[:,0,1]==0) and np.all(truth[:,1,0]==0)


def test_dm_moments_against_monte_carlo():
    x=np.array([[4,3,2,1,5]])
    p=np.array([[[.6,.2,.1,.1],[.1,.6,.1,.2],[.2,.4,.1,.3],[.2,.2,.3,.3],[.3,.2,.1,.4]]])
    rho=.05; concentration=1/rho-1
    mean,cov=margin_moments(x,p,rho)
    rng=np.random.default_rng(11);ys=np.zeros((30000,3))
    for g in range(5):
        random_p=rng.dirichlet(p[0,g]*concentration,len(ys))
        for i in range(len(ys)):ys[i]+=rng.multinomial(x[0,g],random_p[i])[:3]
    assert np.allclose(ys.mean(0),mean[0],atol=.04)
    assert np.allclose(np.cov(ys.T),cov[0],atol=.09)


def test_posterior_aggregation_and_context_expectations():
    x,points,admin=example()
    posterior={'mu':np.zeros((2,3,5,3)),'tau':np.ones((2,3))*.2,
               'z':np.arange(2*3*8*5*3).reshape(2,3,8,5,3)/1000}
    support={'municipality':np.zeros(16,int),'original_place':admin}
    draws=flow_draws(posterior,x,admin,support)
    assert np.allclose(draws['municipality'][:,0],draws['original_place'].sum(1))
    assert np.allclose(draws['municipality'][:,0].sum(2),x.sum(0))
    common={'mu':np.zeros((2,3,5,3))}
    p=list(probability_chunks(common,x,np.zeros(16,int),common=True))[0][1]
    assert np.allclose(p,.25)
    assert np.allclose(context_design(x).mean(0),0)


def test_absent_origins_and_boundary_are_not_successful_zero_rates():
    origins=np.array([[100.,0,0,0,0]])
    truth=np.zeros((1,5,4));truth[0,0,0]=100
    draws=np.tile(truth,(100,1,1,1))
    rows=flow_scores(draws,truth,origins,'municipality')
    absent=[r for r in rows if r['origin']==1]
    assert all(r['error_rate_pp'] is None for r in absent)
    assert all(not r['supported_origin'] for r in absent)
    assert any(r['boundary_zero'] for r in rows)


def test_mc_unit_is_dataset_not_correlated_cells():
    result=mc_summary([1.,1.,1.,1.])
    assert result['n']==4 and result['mcse']>0
    assert result['lower95']<1
    assert mc_summary([])['mean'] is None
    assert mc_summary([1.,1.,1.])['lower95']==pytest.approx((.05/6)**(1/3))
    assert mc_summary([0.,0.,0.])['upper95']==pytest.approx(1-(.05/6)**(1/3))
    assert mc_summary([1.]*100)['mcse_empirical']==0
    assert mc_summary([1.]*100)['mcse']>0


def test_screen_cannot_authorize_scale():
    frame=pd.DataFrame({'coverage':[.95]*30,'mse_electorate_pp':[.01]*30,'mse_rate_pp':[1.]*30,
        'median_width_rate_pp':[5.]*30,'boundary_units':[0]*30,'boundary_false_positive_fraction':[np.nan]*30,
        'boundary_upper95_rate_pp':[np.nan]*30})
    gate={'min_coverage_lower_mc_bound':.9,'max_coverage_mcse':.01,'max_cell_rmse_electorate_pp':2.,
          'max_rate_rmse_pp':10.,'max_median_width_rate_pp':20.,'max_rmse_ratio':1.1}
    r=gate_cell(frame,frame,gate,'development',30)
    assert 'independent_validation_incomplete' in r['reasons']


def test_sample_counts_and_no_outcome_dependency():
    rows=[]
    for b in range(1,6):
        for i in range(8 if b==5 else 30):
            rows.append({'municipality_code':b*100+i,'population_bin':b,'region':['N','NE','CO','SE','S'][i%5],
                'sections':i+3,'composition_sd':i/1000,'coordinate_coverage':.9,'median_neighbour_km':i/10,
                **{f'origin_share_{g}':.2 for g in ['a','b','other','invalid','abstention']}})
    inventory=pd.DataFrame(rows)
    a=select_sample(inventory)
    inventory['a_2']=np.arange(len(inventory))*9999
    b=select_sample(inventory)
    assert a.municipality_code.tolist()==b.municipality_code.tolist()
    assert len(a)==48 and not a.municipality_code.duplicated().any()
    for n in range(1,6):
        block=a[a.population_bin==n]
        assert block.split.eq('development').sum()==(5 if n==5 else 6)
        assert block.split.eq('validation').sum()==(3 if n==5 else 4)


def test_streams_and_config_keys():
    assert seed_for('development',1)!=seed_for('validation',1)
    assert config_parts('n160_d50')==(160,50.)


def test_information_comparison_handles_missing_and_heldout_data(tmp_path):
    from elections.spatial_information import analyze
    assert analyze(tmp_path)['status']=='insufficient_evidence'
    inventory=[];metrics=[]
    for i in range(16):
        inventory.append({'municipality_code':i,'population_bin':i%5+1,'sections':10+i,'composition_sd':.1,
            'coordinate_coverage':.99,'median_neighbour_km':1+i/10,'design_condition':20.,'population':1000*(i+1),
            **{f'origin_{g}':100+i for g in ['a','b','other','invalid','abstention']}})
        metrics.append({'municipality_code':i,'phase':'development' if i<10 else 'validation','scenario':'homogeneous',
            'replicate':0,'config':'n5_d1','method':'geographic_extended','support':'municipality','status':'ok','mse_electorate_pp':.1+i/100})
    pd.DataFrame(inventory).to_csv(tmp_path/'sample.csv',index=False)
    pd.DataFrame(metrics).to_csv(tmp_path/'simulation_metrics.csv.gz',index=False)
    result=analyze(tmp_path)
    assert result['status']=='evaluated'
    assert result['heldout_municipalities']==6
    assert set(result['models'])=={'direct_information','bins','continuous'}


def test_validation_requires_frozen_development_selection(tmp_path,monkeypatch):
    import sys
    import elections.spatial_runner as runner
    monkeypatch.setattr(runner,'prepare',lambda output:{})
    monkeypatch.setattr(runner,'candidate_configurations',lambda output:{1:['n5_d1']})
    monkeypatch.setattr(sys,'argv',['spatial_runner','validate','--output',str(tmp_path)])
    with pytest.raises(ValueError,match='frozen selected_procedure'):
        runner.main()


def test_heldout_results_cannot_change_frozen_selection(tmp_path,monkeypatch):
    import json
    import elections.spatial_runner as runner
    from elections.spatial_experiment import SCENARIOS
    (tmp_path/'manifest.json').write_text('{}')
    pd.DataFrame([{'population_bin':1,'config':'n5_d1','split':'development','median_diameter_km':.5}]).to_csv(tmp_path/'group_feasibility.csv',index=False)
    summaries=[{'phase':'development','population_bin':1,'config':'n5_d1','method':method,'support':support,
        'scenario':s,'datasets':30,'reasons':['independent_validation_incomplete','coverage_monte_carlo_imprecise']} for method in ['geographic','geographic_extended'] for s in SCENARIOS for support in ['municipality','geographic_group']]
    scores=pd.DataFrame([{'phase':'development','value':1.},{'phase':'validation','value':999.}])
    monkeypatch.setattr(runner,'prepare',lambda output:{})
    monkeypatch.setattr(runner,'candidate_configurations',lambda output:{b:['n5_d1'] if b==1 else [] for b in range(1,6)})
    monkeypatch.setattr(runner,'consolidate',lambda output:(None,scores,None,summaries,None))
    a=runner.freeze_selection(tmp_path)
    scores.loc[scores.phase.eq('validation'),'value']=-999.
    summaries.append({'phase':'validation','population_bin':1,'config':'n5_d1','method':'geographic_extended',
        'scenario':'homogeneous','datasets':999,'reasons':['very_bad_heldout_result']})
    b=runner.freeze_selection(tmp_path)
    assert a==b and a['candidates'][1]==['n5_d1']
    assert a['procedures'][1]['method']=='geographic'


def test_worker_rejects_wrong_split_stream_or_population_bin():
    from elections.spatial_runner import validate_job_scope
    manifest={'sample':[{'municipality_code':1,'split':'development'},{'municipality_code':2,'split':'validation'}]}
    job={'phase':'validation','municipality_code':2,'population_bin':1}
    validate_job_scope(manifest,job,1)
    with pytest.raises(ValueError,match='wrong frozen'):
        validate_job_scope(manifest,{**job,'municipality_code':1},1)
    with pytest.raises(ValueError,match='reuse development'):
        validate_job_scope(manifest,{**job,'data_phase':'development'},1)
    with pytest.raises(ValueError,match='population bin'):
        validate_job_scope(manifest,job,2)


def test_confirmation_upgrades_computation_without_extra_data():
    from elections.spatial_runner import effective_results
    job={'phase':'development','population_bin':1,'municipality_code':1,'scenario':'within_building',
         'replicate':0,'method':'geographic','config':'n5_d1','variant':'primary'}
    original={'job':job,'data_seed':123,'diagnostics':{'status':'diagnostic_warning'},'scores':[{'estimate':1}]}
    upgraded={'job':{**job,'phase':'confirmation','data_phase':'development'},'data_seed':123,
              'diagnostics':{'status':'ok'},'scores':[{'estimate':2}]}
    result=effective_results([original,upgraded])
    development=[r for r in result if r['job']['phase']=='development']
    assert len(development)==1
    assert development[0]['diagnostics']['status']=='ok'
    assert development[0]['original_status']=='diagnostic_warning'
    assert development[0]['status_source']=='confirmation'
    assert original['scores'][0]['estimate']==1
    with pytest.raises(ValueError,match='different generated data'):
        effective_results([original,{**upgraded,'data_seed':999}])
    failed={'job':upgraded['job'],'diagnostics':{'status':'resource_timeout'},'scores':[]}
    result=effective_results([original,failed])
    assert result[0]['diagnostics']['status']=='resource_timeout' and result[0]['scores']==[]


def test_absent_origin_is_not_a_zero_rate_or_calibration_failure():
    frame=pd.DataFrame({'coverage':[None],'boundary_units':[0],'mse_rate_pp':[None],
                        'active_origin_units':[0]})
    result=gate_cell(frame,None,{},'validation',100)
    assert result['not_applicable'] and result['reasons']==[]
    assert result['rmse_rate_pp'] is None


def test_relative_error_uses_only_paired_completed_datasets():
    frame=pd.DataFrame({'replicate':[0,1],'municipality_code':[1,2],'coverage':[1.,1.],
        'mse_electorate_pp':[1.,100.],'mse_rate_pp':[1.,1.],'median_width_rate_pp':[1.,1.],
        'boundary_units':[0,0],'boundary_false_positive_fraction':[None,None],'boundary_upper95_rate_pp':[None,None]})
    baseline=frame.iloc[:1].copy()
    gate={'min_coverage_lower_mc_bound':.9,'max_coverage_mcse':.01,'max_cell_rmse_electorate_pp':20.,
        'max_rate_rmse_pp':10.,'max_median_width_rate_pp':20.,'max_rmse_ratio':1.1}
    result=gate_cell(frame,baseline,gate,'development',2)
    assert result['rmse_ratio']==1.
    assert result['paired_benchmark_fraction']==.5
    assert 'paired_benchmark_availability_below_95pct' in result['reasons']


def test_zero_flow_reference_error_uses_boundary_assessment():
    frame=pd.DataFrame({'coverage':[None]*1000,'mse_electorate_pp':[1e-8]*1000,'mse_rate_pp':[1e-4]*1000,
        'median_width_rate_pp':[1.]*1000,'boundary_units':[1]*1000,'boundary_false_positive_fraction':[0.]*1000,
        'boundary_upper95_rate_pp':[.2]*1000})
    base=frame.copy();base['mse_electorate_pp']=0.
    gate={'min_coverage_lower_mc_bound':.9,'max_coverage_mcse':.01,'max_cell_rmse_electorate_pp':2.,
        'max_rate_rmse_pp':10.,'max_median_width_rate_pp':20.,'max_rmse_ratio':1.1}
    result=gate_cell(frame,base,gate,'validation',1000)
    assert result['boundary_zero_reference_error'] and result['rmse_ratio'] is None
    assert not result['reasons']


def test_validation_checkpoint_waits_for_all_data_and_upgrades(tmp_path,monkeypatch):
    import json
    import elections.spatial_runner as runner
    (tmp_path/'manifest.json').write_text('{}')
    digest=runner.design_hash(tmp_path)
    (tmp_path/'selected_procedure.json').write_text(json.dumps({'procedures':{'1':{'method':'geographic','config':'n5_d1'}}}))
    city={'municipality_code':2,'population_bin':1}
    planned=[runner.make_job(city,'validation','homogeneous',i,'geographic','n5_d1') for i in range(100)]
    monkeypatch.setattr(runner,'SCENARIOS',['homogeneous'])
    monkeypatch.setattr(runner,'simulation_jobs',lambda *args:planned)
    assert not runner.commit_validation_checkpoint(tmp_path,100,{1:['n5_d1']})
    for job in planned:
        path=runner.job_path(tmp_path,job);path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'manifest_hash':digest,'diagnostics':{'status':'ok' if job['replicate']<99 else 'diagnostic_warning'}}))
    assert not runner.commit_validation_checkpoint(tmp_path,100,{1:['n5_d1']})
    upgrade={**planned[-1],'phase':'confirmation','data_phase':'validation','confirmation':True}
    runner.job_path(tmp_path,upgrade).write_text(json.dumps({'manifest_hash':digest,'diagnostics':{'status':'resource_timeout'}}))
    result=runner.commit_validation_checkpoint(tmp_path,100,{1:['n5_d1']})
    assert result['1']['replicates']==100 and result['1']['selection_hash']
    assert not runner.commit_validation_checkpoint(tmp_path,200,{1:['n5_d1']})


def test_local_prior_sensitivity_uses_group_denominator_and_complete_variants():
    from scripts.build_spatial_report import local_prior_sensitivity
    rows=[]
    for variant in ['primary','tighter','wider']:
        for g in range(5):
            for k in range(4):
                value=5.
                if variant=='wider' and g==0 and k==0:value=9.
                if variant=='wider' and g==0 and k==3:value=1.
                rows.append({'phase':'real','support':'geographic_group','method':'geographic_extended',
                    'municipality_code':1,'config':'n5_d1','unit':0,'origin':g,'destination':k,'variant':variant,
                    'estimate':value,'electorate':100.,'origin_voters':20.,'status':'ok'})
    frame=pd.DataFrame(rows)
    result=local_prior_sensitivity(frame).iloc[0]
    assert result.complete and result.sensitivity_electorate_pp==4.
    assert result.investigation_status=='unresolved_prior_sensitivity'
    result=local_prior_sensitivity(frame[frame.variant.ne('wider')]).iloc[0]
    assert not result.complete and pd.isna(result.sensitivity_electorate_pp)


def test_compact_display_preserves_matrix_order_intervals_and_absent_origins():
    from scripts.build_spatial_report import compact_estimates
    rows=[]
    for g in range(5):
        for k in range(4):
            rows.append({'municipality_code':1,'phase':'real','method':'geographic','config':'n5_d1',
                'support':'geographic_group','unit':0,'origin':g,'destination':k,'status':'ok',
                'interval_type':'conditional','electorate':80.,'origin_voters':20. if g<4 else 0.,
                'estimate':5. if g<4 else 0.,'low':1. if g<4 else 0.,'high':9. if g<4 else 0.})
    frame=pd.DataFrame(rows)
    packed=compact_estimates(frame)[0]
    assert packed['origin_counts']==[20,20,20,20,0]
    assert packed['point'][:4]==[5.]*4 and packed['point'][16:]==[0.]*4
    assert packed['low'][0]==1. and packed['high'][0]==9.
    with pytest.raises(ValueError,match='incomplete'):
        compact_estimates(frame.iloc[:-1])
