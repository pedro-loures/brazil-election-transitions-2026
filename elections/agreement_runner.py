"""Isolated, resumable execution of the model-agreement extension."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone,timedelta
import hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
import numpy as np
import pandas as pd
from .agreement_model import FAMILIES,fit,prediction_chunks
from .agreement import building_weights,resampled_groups
from .hierarchy_inventory import sha256
from .spatial import ROOT,OUT as SPATIAL,KEY,seed_for
from .spatial_experiment import data_arrays,SCENARIOS
from .spatial_runner import save,clean,baseline_fit
from .spatial_validation import generate,aggregate,flow_scores,summarize_dataset

OUT=ROOT/'results/2026/model_agreement'
METHODS=FAMILIES+('municipal_wls',)


def prepare(output=OUT):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    path=output/'manifest.json'
    if path.exists():
        m=json.loads(path.read_text())
        for rel,digest in m['sources'].items():
            if sha256(ROOT/rel)!=digest:raise ValueError('Frozen extension source changed: '+rel)
        return m
    old=json.loads((SPATIAL/'manifest.json').read_text())
    for rel,digest in old['sources'].items():
        if sha256(ROOT/rel)!=digest:raise ValueError('Original source changed: '+rel)
    for rel,digest in old['frozen_artifacts'].items():
        if sha256(SPATIAL/rel)!=digest:raise ValueError('Frozen original design changed: '+rel)
    sample=old['sample'];pilot=[];profiles=[]
    for b,target in [(1,20),(2,30),(3,100),(4,600),(5,3200)]:
        options=[c for c in sample if c['population_bin']==b and c['split']=='development' and c['design_rank']==5]
        c=min(options,key=lambda c:(abs(c['sections']-target),c['municipality_code']))
        profiles.append(c['municipality_code'])
        if b<=3:pilot.append(c['municipality_code'])
    paths={ROOT/rel for rel in old['sources']}
    paths.update([SPATIAL/'manifest.json',SPATIAL/'sample_sections.csv.gz',SPATIAL/'sample.csv',ROOT/'MODEL_AGREEMENT_EXTENSION.md'])
    for pattern in ['elections/agreement*.py','scripts/*agreement*.py','web/agreement/*','tests/test_agreement*.py']:
        paths.update(p for p in ROOT.glob(pattern) if p.is_file())
    paths.update(ROOT/p for p in ['elections/spatial.py','elections/spatial_model.py','elections/spatial_validation.py','elections/spatial_experiment.py','elections/model.py','elections/hierarchy.py','elections/hierarchy_simulation.py','elections/spatial_runner.py'])
    m={'created_utc':datetime.now(timezone.utc).isoformat(),'version':'model_agreement_v1','seed':20261030,
       'sources':{str(p.relative_to(ROOT)):sha256(p) for p in sorted(paths)},'sample':sample,
       'pilot_cities':pilot,'profile_cities':profiles,'families':list(FAMILIES),'additional_benchmark':'municipal_wls',
       'geography':{'target_sections':10,'max_diameter_km':5.,'selection':'fixed prospective comparator, not reliability-selected'},
       'mixture':{'components':2,'selection':'fixed prospective pilot; no claim of an optimal number','component_anchor':'ordered A-to-A reference logit',
           'membership':'marginalized during fitting; conditional categorical draws during prediction',
           'bootstrap_omitted_sections':'prior membership; omitted outcomes not used for assignments'},
       'matched_specification':'All four families use the same composition design, beta prior, DM moment rho prior and normal margin likelihood. Mixture/geographic terms differ.',
       'sampling':{'chains':4,'warmup':700,'samples':700,'acceptance':.97,'depth':11},
       'confirmation_sampling':{'chains':4,'warmup':1000,'samples':1500,'acceptance':.99,'depth':12},
       'resampling':{'unit':'whole polling building','strata':'two first-round site-electorate rank strata if at least four buildings',
           'paired_indices_across_families':True,'rebuild_geographic_groups':True,'pilot_replicates':20,'full_replicates':100,
           'estimand':'original fixed electorate; original-place and section supports retained',
           'interpretation':'case-weight perturbation sensitivity, not independent elections or a calibrated confidence interval'},
       'agreement':{'matrix_distance':.05,'supported_origin_min':100,'rate_difference_pp':10.,'key_flow_electorate_pp':2.,
          'largest_subset':'all mutually agreeing maximum subsets; report tied subsets, dissent and missing models'},
       'scenarios':list(SCENARIOS),'development_replicates':30,'validation_looks':[100,500,1000],
       'pilot_simulations':{'bins':[1],'scenarios':['within_building','contextual'],'replicates':30},
       'acceptance':old['gate'],
       'scope':'Expected transitions, not observed individual ballots. Consensus never overrides validation or computation failures.'}
    from importlib.metadata import version
    m['versions']={package:version(package) for package in ['numpy','pandas','scipy','jax','jaxlib','numpyro','arviz']}
    save(path,m)
    (output/'code_snapshot').mkdir(exist_ok=True)
    import shutil
    for rel in m['sources']:
        if rel.startswith(('elections/','scripts/','web/','tests/')) or rel.endswith('.md'):
            target=output/'code_snapshot'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,target)
    return m


def path_for(output,job):
    key=f"{job['phase']}-{job['municipality_code']}-{job['scenario']}-r{job['replicate']:04d}-{job['family']}-{job.get('variant','primary')}"
    return Path(output)/'jobs'/(key+'.json')


def make_job(city,phase,scenario='observed',replicate=0,family='municipal',variant='primary'):
    return {'municipality_code':int(city['municipality_code']),'population_bin':int(city['population_bin']),
            'phase':phase,'scenario':scenario,'replicate':int(replicate),'family':family,'variant':variant}


def jobs_for(m,stage,replicates=None):
    jobs=[]
    if stage in ['pilot','observed','resampling','profile']:
        cities=[c for c in m['sample'] if c['municipality_code'] in (m['profile_cities'] if stage=='profile' else m['pilot_cities'])] if stage in ['pilot','profile'] else m['sample']
        for c in cities:
            phases=[('profile',0,'primary')] if stage=='profile' else [('observed',0,'primary')]
            if stage in ['pilot','resampling']:
                n=replicates or (m['resampling']['pilot_replicates'] if stage=='pilot' else m['resampling']['full_replicates'])
                phases += [('bootstrap',r,'primary') for r in range(n)]
                phases += [('deletion',r,'primary') for r in range(min(2,c['sites']-1))]
                phases += [('observed',0,v) for v in ['tighter','wider']]
            for phase,r,v in phases:
                for f in METHODS if v=='primary' else FAMILIES:
                    jobs.append(make_job(c,phase,replicate=r,family=f,variant=v))
        # Complete the common observed fits before launching perturbations.
        jobs.sort(key=lambda j:(j['phase'] not in ['observed','profile'],j['variant']!='primary',j['replicate'],j['municipality_code'],j['family']))
    if stage in ['pilot','development','validation']:
        phase='validation' if stage=='validation' else 'development'
        bins=m['pilot_simulations']['bins'] if stage=='pilot' else range(1,6)
        scenarios=m['pilot_simulations']['scenarios'] if stage=='pilot' else m['scenarios']
        n=replicates or (100 if phase=='validation' else m['development_replicates'])
        for b in bins:
            cities=sorted([c for c in m['sample'] if c['population_bin']==b and c['split']==phase],key=lambda c:c['municipality_code'])
            # Frozen split labels are development / validation.
            for scenario in scenarios:
                for r in range(n):
                    for f in METHODS:jobs.append(make_job(cities[r%len(cities)],phase,scenario,r,f))
    if stage=='pilot':
        # At least one known-flow dataset per scenario precedes a long resampling run.
        jobs.sort(key=lambda j:(0 if j['phase']=='observed' and j['variant']=='primary' else
                                1 if j['phase']=='development' and j['replicate']==0 else 2,
                               j['replicate'],j['municipality_code'],j['family']))
    return jobs


def case_data(m,job):
    city=next(c for c in m['sample'] if c['municipality_code']==job['municipality_code'])
    if city['population_bin']!=job['population_bin']:raise ValueError('Wrong population bin')
    if job['phase'] in ['development','validation'] and city['split']!=job['phase']:raise ValueError('Wrong experimental split')
    frame=pd.read_csv(SPATIAL/'sample_sections.csv.gz')
    s=frame[frame.municipality_code.eq(job['municipality_code'])].reset_index(drop=True)
    x,y,points,administrative=data_arrays(s)
    data_seed=seed_for(m['seed'],m['version'],job['phase'] if job['phase'] in ['development','validation'] else 'observed',job['municipality_code'],job['scenario'],job['replicate'] if job['phase'] in ['development','validation'] else 0)
    truth=None
    if job['scenario']!='observed':x,y,truth,_,points=generate(x,administrative,points,job['scenario'],data_seed)
    weight=np.ones(len(x),int)
    if job['phase']=='bootstrap':weight=building_weights(x,points,seed_for(m['seed'],'paired-building-bootstrap',job['municipality_code'],job['replicate']))
    elif job['phase']=='deletion':
        _,site=np.unique(points,axis=0,return_inverse=True)
        size=np.bincount(site,weights=x.sum(1));selected=np.argsort(-size,kind='stable')[job['replicate']]
        weight[site==selected]=0
    groups=resampled_groups(points,weight,m['geography']['target_sections'],m['geography']['max_diameter_km'])
    return s,x,y,points,administrative,weight,groups,truth,data_seed


def draw_rows(draws,origins,support,units,truth=None):
    point=draws.mean(0);low,high=np.quantile(draws,[.025,.975],axis=0)
    rows=[]
    for i,unit in enumerate(units):
        for g in range(5):
            for k in range(4):
                n=float(origins[i,g]);electorate=float(origins[i].sum())
                row={'support':support,'unit':int(unit),'origin':g,'destination':k,'origin_voters':n,'electorate':electorate,
                    'estimate':float(point[i,g,k]),'low':float(low[i,g,k]),'high':float(high[i,g,k]),
                    'width_rate_pp':float(100*(high[i,g,k]-low[i,g,k])/n) if n else None}
                if truth is not None:row['truth']=float(truth[i,g,k])
                rows.append(row)
    return rows


def execute(output,job):
    m=prepare(output);started=time.monotonic()
    s,x,y,points,admin,weight,group,truth,data_seed=case_data(m,job)
    seed=seed_for(data_seed,job['family'],job['variant'],job['phase'],job['replicate'])
    result={'job':job,'manifest_hash':sha256(Path(output)/'manifest.json'),'data_seed':data_seed,
        'weight_sha256':hashlib.sha256(weight.tobytes()).hexdigest(),'groups':int(group.max()+1),'sections':len(x),
        'active_sections':int((weight>0).sum()),'electorate':int(x.sum()),'origin_counts':x.sum(0).tolist(),
        'grouping_rebuilt':True,'observed_round_totals':y.sum(0).tolist(),'scores':[],'coassignment':[]}
    supports={'municipality':np.zeros(len(x),int),'original_place':admin,'geographic_group':group}
    rows=[];scores=[]
    if job['family']=='municipal_wls':
        index=np.repeat(np.arange(len(x)),weight)
        base,diag=baseline_fit(x[index],y[index],seed)
        result['diagnostics']=diag
        if base is not None:
            point,draws=base
            for name,labels in {**supports,'section':np.arange(len(x))}.items():
                counts=aggregate(x,labels);f=draws[:,None]*counts[None,:,:,None]
                r=draw_rows(f,counts,name,range(len(counts)),aggregate(truth,labels) if truth is not None else None)
                for row in r:row['estimate']=float(point[row['origin'],row['destination']]*counts[row['unit'],row['origin']])
                rows+=r
                if truth is not None:scores+=flow_scores(f,aggregate(truth,labels),counts,name,point=point[None]*counts[:,:,None])
    else:
        posterior,diag=fit(x,y,group,weight,job['family'],seed=seed,variant=job['variant'],**m['sampling'])
        result['diagnostics']=diag
        count=m['sampling']['chains']*m['sampling']['samples']
        grouped={name:np.zeros((count,int(labels.max()+1),5,4)) for name,labels in supports.items()}
        membership=[]
        for sl,p,labels,q in prediction_chunks(posterior,x,y,group,job['family'],weight,seed+1):
            f=p*x[None,sl,:,None]
            rows+=draw_rows(f,x[sl],'section',range(sl.start,sl.stop),truth[sl] if truth is not None else None)
            if truth is not None:scores+=flow_scores(f,truth[sl],x[sl],'section',np.arange(len(x))[sl])
            if labels is not None:membership.append(labels)
            for name,out in grouped.items():
                for label in np.unique(supports[name][sl]):out[:,label]+=f[:,supports[name][sl]==label].sum(1)
        for name,draws in grouped.items():
            labels=supports[name];counts=aggregate(x,labels)
            rows+=draw_rows(draws,counts,name,range(len(counts)),aggregate(truth,labels) if truth is not None else None)
            if truth is not None:scores+=flow_scores(draws,aggregate(truth,labels),counts,name)
        if membership:
            labels=np.concatenate(membership,axis=1)
            result['membership_mode']=(labels.mean(0)>=.5).astype(int).tolist()
            result['membership_probability_component_1']=labels.mean(0).tolist()
            rng=np.random.default_rng(seed_for(m['seed'],'fixed-section-pairs',job['municipality_code']))
            pairs=set()
            while len(pairs)<min(200,len(x)*(len(x)-1)//2):
                a,b=sorted(rng.choice(len(x),2,replace=False));pairs.add((int(a),int(b)))
            result['coassignment']=[{'first':a,'second':b,'probability':float((labels[:,a]==labels[:,b]).mean()),
                'both_in_sample':bool(weight[a]>0 and weight[b]>0)} for a,b in sorted(pairs)]
        if job['phase'] in ['observed','profile'] and job['variant']=='primary':
            destination=Path(output)/'fits'/path_for(output,job).with_suffix('.npz').name
            destination.parent.mkdir(exist_ok=True);np.savez_compressed(destination,**posterior)
    result['weights']=weight.tolist()
    if scores:result['scores']=summarize_dataset(scores)
    if rows:
        frame=pd.DataFrame(rows)
        for key,value in job.items():frame[key]=value
        frame['status']=result['diagnostics']['status']
        destination=Path(output)/'flows'/path_for(output,job).with_suffix('.csv.gz').name
        destination.parent.mkdir(exist_ok=True);frame.to_csv(destination,index=False)
        result['flow_file']=str(destination.relative_to(output))
        result['municipal_flows']=frame[frame.support.eq('municipality')].to_dict('records')
    result['elapsed_seconds']=time.monotonic()-started
    save(path_for(output,job),result)
    return result


def run_one(output,job,timeout,slot):
    path=path_for(output,job);digest=sha256(Path(output)/'manifest.json')
    if path.exists():
        r=json.loads(path.read_text())
        if r['manifest_hash']!=digest:raise ValueError('Wrong cached experiment')
        return r
    path.parent.mkdir(parents=True,exist_ok=True)
    import shutil
    if shutil.disk_usage(output).free<2*1024**3:
        result={'job':job,'manifest_hash':digest,'diagnostics':{'status':'resource_storage_reserve'},'elapsed_seconds':0.,'scores':[]}
        save(path,result);return result
    spec=path.with_suffix('.job.json');save(spec,job)
    env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MPLCONFIGDIR='/tmp/elections-matplotlib',
        XLA_FLAGS='--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1')
    available=sorted(os.sched_getaffinity(0));parts=np.array_split(available,4)
    command=['taskset','-c',','.join(map(str,parts[slot])),sys.executable,'-m','elections.agreement_runner','worker','--output',str(output),'--job',str(spec)]
    started=time.monotonic()
    with path.with_suffix('.log').open('w') as log:
        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        try:code=proc.wait(timeout=timeout);status='process_failed' if code else 'missing_result'
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL);proc.wait();status='resource_timeout'
    if not path.exists():save(path,{'job':job,'manifest_hash':digest,'diagnostics':{'status':status},'elapsed_seconds':time.monotonic()-started,'scores':[]})
    result=json.loads(path.read_text())
    print(json.dumps({'job':path.name,'status':result['diagnostics']['status'],'seconds':round(result['elapsed_seconds'],1)}),flush=True)
    return result


def run(output=OUT,stage='pilot',workers=4,timeout=900,wall_seconds=7200,replicates=None):
    output=Path(output);m=prepare(output)
    if stage=='validation':
        if replicates is not None and replicates not in m['validation_looks']:
            raise ValueError('Validation only permits the frozen 100/500/1000 dataset looks')
        lock=output/'selection.json'
        selection=json.loads(lock.read_text()) if lock.exists() else {}
        if selection.get('status')!='frozen' or selection.get('manifest_hash')!=sha256(output/'manifest.json'):
            raise ValueError('Independent validation requires a complete development-only procedure freeze')
    jobs=jobs_for(m,stage,replicates);started=time.monotonic();deadline=started+wall_seconds
    state={'stage':stage,'status':'running','started_utc':datetime.now(timezone.utc).isoformat(),'planned_jobs':len(jobs),'workers':workers,'timeout_seconds':timeout,
           'manifest_hash':sha256(output/'manifest.json'),'pilot_is_not_independent_validation':stage=='pilot'}
    def checkpoint():
        complete=[json.loads(path_for(output,j).read_text()) for j in jobs if path_for(output,j).exists()]
        state.update(completed_jobs=len(complete),pending_jobs=len(jobs)-len(complete),elapsed_seconds=time.monotonic()-started,
            statuses=pd.Series([r['diagnostics']['status'] for r in complete],dtype=str).value_counts().to_dict())
        measured=[r['elapsed_seconds'] for r in complete if r['job']['family']!='municipal_wls' and r['diagnostics']['status'] in ['ok','diagnostic_warning']]
        if measured:
            pending=sum(not path_for(output,j).exists() and j['family']!='municipal_wls' for j in jobs)
            seconds=pending*np.quantile(measured,[.5,.9])/workers
            state['eta_remaining_seconds_median_p90']=seconds.tolist()
            state['eta_utc_median_p90']=[(datetime.now(timezone.utc)+timedelta(seconds=float(v))).isoformat() for v in seconds]
            state['eta_scope']='Observed completed-fit runtimes; extrapolation may understate metropolitan cost or diagnostic upgrades.'
        save(output/'execution_state.json',state)
    checkpoint()
    pending=[j for j in jobs if not path_for(output,j).exists()]
    def worker(slot):
        for job in pending[slot::workers]:
            if time.monotonic()>=deadline:return
            run_one(output,job,timeout,slot)
    last_report=started
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(worker,i) for i in range(workers)]
            while not all(f.done() for f in futures):
                time.sleep(5);checkpoint()
                if time.monotonic()-last_report>=120:
                    from scripts.build_agreement_report import build
                    build(output);last_report=time.monotonic()
            for f in futures:f.result()
        checkpoint();state['status']='completed_requested_stage' if state['pending_jobs']==0 else 'incomplete_wall_budget'
    except BaseException as error:
        state['status']='controller_failed';state['error']=repr(error)
        raise
    finally:
        checkpoint();save(output/'execution_state.json',state)
        from scripts.build_agreement_report import build
        build(output)
    return state


def freeze_development(output=OUT):
    """Keep all fixed families for the comparison; never select a consensus post hoc."""
    output=Path(output);m=prepare(output);jobs=jobs_for(m,'development')
    missing=[str(path_for(output,j).name) for j in jobs if not path_for(output,j).exists()]
    if missing:raise ValueError(f'Development incomplete: {len(missing)} method fits remain')
    results=[]
    for job in jobs:
        path=path_for(output,job);result=json.loads(path.read_text())
        if result['manifest_hash']!=sha256(output/'manifest.json'):raise ValueError('Wrong experiment')
        results.append(sha256(path))
    value={'status':'frozen','manifest_hash':sha256(output/'manifest.json'),'families':list(FAMILIES),
        'development_result_hash':hashlib.sha256(''.join(results).encode()).hexdigest(),
        'rule':'All four prespecified families retained for independent comparison; agreement tolerances and model complexity unchanged. No claim that every family passes development.'}
    path=output/'selection.json'
    if path.exists() and json.loads(path.read_text())!=value:raise ValueError('Selection already frozen')
    save(path,value)
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['prepare','pilot','profile','observed','resampling','development','select','validation','report','worker'])
    p.add_argument('--output',type=Path,default=OUT);p.add_argument('--job',type=Path);p.add_argument('--workers',type=int,default=4)
    p.add_argument('--timeout',type=int,default=900);p.add_argument('--wall-seconds',type=int,default=7200);p.add_argument('--replicates',type=int)
    a=p.parse_args()
    if not 1<=a.workers<=4:p.error('workers must be 1–4')
    if a.stage=='worker':execute(a.output,json.loads(a.job.read_text()));return
    if a.stage=='prepare':prepare(a.output);return
    if a.stage=='select':freeze_development(a.output);return
    if a.stage=='report':
        from scripts.build_agreement_report import build
        build(a.output);return
    print(json.dumps(run(a.output,a.stage,a.workers,a.timeout,a.wall_seconds,a.replicates),indent=2))


if __name__=='__main__':main()
