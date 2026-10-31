"""Frozen nationwide combined-model run; the published baseline is never edited.

prepare -> run -> verify -> candidate-site build -> authorized release.
Every domestic municipal unit receives a terminal record, including exclusions.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone,timedelta
import hashlib,json,os,queue,shutil,signal,subprocess,sys,threading,time
from pathlib import Path
import numpy as np
import pandas as pd
from .agreement_model import fit,prediction_chunks
from .hierarchy_inventory import sha256
from .spatial import ROOT,OUT as SPATIAL,KEY,partition,information,seed_for
from .spatial_experiment import load_sections,data_arrays
from .spatial_runner import save
from .model import fit_transition

OUT=ROOT/'results/2026/national_combined'
SAMPLING={'primary':{'chains':4,'warmup':700,'samples':700,'acceptance':.97,'depth':11},
          'long':{'chains':4,'warmup':1000,'samples':1500,'acceptance':.99,'depth':12}}
SOURCE_FILES=['elections/national_combined.py','elections/agreement_model.py','elections/spatial_model.py',
              'elections/spatial.py','elections/hierarchy.py','elections/model.py']


def verify_sources(manifest,heavy=True):
    for rel,digest in manifest['sources'].items():
        if heavy or rel.startswith('elections/'):
            if sha256(ROOT/rel)!=digest:raise ValueError('Frozen national source changed: '+rel)


def prepare(output=OUT):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    path=output/'manifest.json'
    if path.exists():
        m=json.loads(path.read_text());verify_sources(m);return m
    old=json.loads((SPATIAL/'manifest.json').read_text())
    for rel,digest in old['sources'].items():
        if sha256(ROOT/rel)!=digest:raise ValueError('Original source changed: '+rel)
    for rel,digest in old['frozen_artifacts'].items():
        if sha256(SPATIAL/rel)!=digest:raise ValueError('Audited source changed: '+rel)
    sections=load_sections(SPATIAL)
    cities=pd.read_csv(ROOT/'results/2026/municipalities.csv')
    population=pd.read_csv(ROOT/'results/2026/spatial_feasibility/municipality_population_bins.csv')
    sections=sections[sections.coordinate_status.eq('verified_register_boundary')]
    grouped={int(code):s.reset_index(drop=True) for code,s in sections.groupby('municipality_code',sort=True)}
    pop=population.set_index('municipality_code')
    (output/'inputs').mkdir(exist_ok=True);inventory=[]
    for city in cities.to_dict('records'):
        code=int(city['municipality_code']);s=grouped.get(code)
        item={'municipality_code':code,'municipality':city['municipality'],'uf':city['uf'],
              'population_bin':int(pop.loc[code,'population_bin']),'population':int(pop.loc[code,'population']),
              'sections_union':int(city['sections_union']),'original_retained_sections':int(city['sections_analyzed']),
              'full_electorate':float(city['eligible_1']),'original_retained_electorate':float(city.get('analyzed_eligible_1',0) or 0)}
        if s is None or s.empty:
            item.update(sections=0,electorate=0,coverage=0.,status='no_verified_sections')
        else:
            x,y,points,admin=data_arrays(s)
            destination=output/'inputs'/f'{code}.npz'
            np.savez_compressed(destination,x=x,y=y,points=points,admin=admin,
                section=s['section'].to_numpy(int),zone=s['zone'].to_numpy(int))
            item.update(**information(x),coverage=float(x.sum()/city['eligible_1']),status='pending',
                input_sha256=sha256(destination),sites=len(np.unique(points,axis=0)),
                observed_origins=x.sum(0).tolist(),observed_destinations=y.sum(0).tolist(),
                latitude=float(points[:,0].mean()),longitude=float(points[:,1].mean()))
        inventory.append(item)
    sources={ROOT/rel for rel in SOURCE_FILES}
    sources.update([SPATIAL/'manifest.json',SPATIAL/'section_coordinates.csv.gz',ROOT/'results/2026/sections.csv.gz',
        ROOT/'results/2026/municipalities.csv',ROOT/'results/2026/spatial_feasibility/municipality_population_bins.csv',
        ROOT/'results/2026/model_agreement/manifest.json',ROOT/'results/2026/model_agreement/decision.json'])
    from importlib.metadata import version
    manifest={'version':'national_combined_v1','created_utc':datetime.now(timezone.utc).isoformat(),'seed':20261030,
       'sources':{str(p.relative_to(ROOT)):sha256(p) for p in sorted(sources)},'inventory':inventory,
       'family':'combined','behavioural_regimes':2,'target_sections':10,'max_diameter_km':5.,'variant':'primary',
       'sampling':SAMPLING,'timeouts_seconds':{'primary':900,'long':1800},
       'versions':{p:version(p) for p in ['numpy','pandas','scipy','jax','jaxlib','numpyro','arviz']},
       'selection':'Fixed completed-pilot specification; no national outcome tuning or empirical reliability threshold.',
       'interval_type':'Pointwise conditional posterior credible interval; not independently calibrated nationally.',
       'release':'User-authorized experimental replacement after every city has a terminal result and publication checks pass.',
       'failed_fit_policy':'Never substitute original baseline estimates for unavailable new fits.',
       'upgrade_policy':'One longer attempt for a primary sampling warning or resource timeout. Keep all raw attempts; prefer a converged fit, otherwise retain a provisional available fit.',
       'workers_max':8,'storage_reserve_bytes':2*1024**3,'independent_validation_complete':False}
    save(path,manifest);pd.DataFrame(inventory).to_csv(output/'inventory.csv',index=False)
    return manifest


def attempt_path(output,code,level):return Path(output)/'attempts'/f'{code}-{level}.json'


def fit_attempt(output,code,level):
    output=Path(output);m=json.loads((output/'manifest.json').read_text());verify_sources(m,False)
    item=next(c for c in m['inventory'] if c['municipality_code']==code)
    shard=output/'inputs'/f'{code}.npz'
    if sha256(shard)!=item['input_sha256']:raise ValueError('Municipal input changed')
    with np.load(shard) as a:x,y,points=a['x'],a['y'],a['points']
    groups=partition(points,m['target_sections'],m['max_diameter_km'])
    sampling=m['sampling'][level];seed=seed_for(m['seed'],m['version'],code,level)
    started=time.monotonic()
    posterior,diagnostics=fit(x,y,groups,np.ones(len(x),int),'combined',seed=seed,variant=m['variant'],**sampling)
    draws=np.zeros((sampling['chains']*sampling['samples'],5,4))
    for sl,p,_,_ in prediction_chunks(posterior,x,y,groups,'combined',np.ones(len(x),int),seed+1):
        draws+=(p*x[None,sl,:,None]).sum(1)
    matrix=draws.mean(0);low,high=np.quantile(draws,[.025,.975],axis=0)
    origin=x.sum(0)
    if not np.allclose(matrix.sum(1),origin,atol=1e-7):raise ValueError('Origin conservation failed')
    baseline=None
    if len(x)>=10 and np.linalg.matrix_rank(x/x.sum(1,keepdims=True))==5:
        fitted=fit_transition(x,y)
        if fitted['status']=='ok':baseline=fitted['flows']
    result={'municipality_code':code,'level':level,'manifest_hash':sha256(output/'manifest.json'),
        'input_sha256':item['input_sha256'],'seed':seed,'diagnostics':diagnostics,'groups':int(groups.max()+1),
        'matrix':matrix.tolist(),'low':low.tolist(),'high':high.tolist(),'origins':origin.tolist(),
        'observed_destinations':y.sum(0).tolist(),'predicted_destinations':matrix.sum(0).tolist(),
        'destination_residual_votes':(matrix.sum(0)-y.sum(0)).tolist(),
        'baseline_matrix':None if baseline is None else baseline.tolist(),
        'baseline_allocation_distance':None if baseline is None else float(abs(matrix-baseline).sum()/(2*x.sum())),
        'elapsed_seconds':time.monotonic()-started,'independent_validation_complete':False}
    draw_path=output/'draws'/f'{code}-{level}.npz';draw_path.parent.mkdir(exist_ok=True)
    temporary=draw_path.with_suffix('.tmp')
    with temporary.open('wb') as f:np.savez_compressed(f,flows=draws)
    temporary.replace(draw_path);result['draws_sha256']=sha256(draw_path)
    save(attempt_path(output,code,level),result)
    return result


def run_attempt(output,item,level,slot,workers):
    code=item['municipality_code'];path=attempt_path(output,code,level)
    if path.exists():return json.loads(path.read_text())
    path.parent.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    m=json.loads((Path(output)/'manifest.json').read_text())
    if shutil.disk_usage(output).free<m['storage_reserve_bytes']:
        r={'municipality_code':code,'level':level,'diagnostics':{'status':'resource_storage_reserve'},'elapsed_seconds':0.}
        save(path,r);return r
    env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MPLCONFIGDIR='/tmp/elections-matplotlib',
         XLA_FLAGS='--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1')
    partitions=np.array_split(sorted(os.sched_getaffinity(0)),workers)
    command=['taskset','-c',','.join(map(str,partitions[slot])),sys.executable,'-m','elections.national_combined','worker',
        '--output',str(output),'--code',str(code),'--level',level]
    with path.with_suffix('.log').open('w') as log:
        proc=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            exit_code=proc.wait(timeout=m['timeouts_seconds'][level]);status='process_failed' if exit_code else 'missing_result'
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL);proc.wait();status='resource_timeout'
    if not path.exists():save(path,{'municipality_code':code,'level':level,'diagnostics':{'status':status},'elapsed_seconds':time.monotonic()-started})
    return json.loads(path.read_text())


def select_attempt(primary,long=None):
    """A failed upgrade cannot destroy a converged/provisional original fit."""
    available=[r for r in [primary,long] if r is not None and 'matrix' in r]
    good=[r for r in available if r['diagnostics']['status']=='ok']
    if good:return good[-1]
    if available:return available[-1]
    return long or primary


def fit_city(output,item,slot,workers):
    code=item['municipality_code'];destination=Path(output)/'cities'/f'{code}.json'
    if destination.exists():return json.loads(destination.read_text())
    if item['sections']==0:
        result={**item,'diagnostics':{'status':'no_verified_sections'},'status':'no_verified_sections'}
    else:
        primary=run_attempt(output,item,'primary',slot,workers);long=None
        if primary['diagnostics']['status'] in ['diagnostic_warning','resource_timeout']:
            long=run_attempt(output,item,'long',slot,workers)
        selected=select_attempt(primary,long)
        result={**item,**selected,'status':selected['diagnostics']['status'],
            'attempts':[{'level':r['level'],'status':r['diagnostics']['status'],'seconds':r['elapsed_seconds']} for r in [primary,long] if r],
            'provisional':selected['diagnostics']['status']!='ok','independent_validation_complete':False}
    save(destination,result);return result


def ordered_inventory(inventory):
    lookup={c['municipality_code']:c for c in inventory}
    early=[93831,2054,68659,50911,2550,81914]
    rest=sorted([c for c in inventory if c['municipality_code'] not in early],
        key=lambda c:(c['population_bin'],c['sections'],c['municipality_code']))
    return [lookup[c] for c in early if c in lookup]+rest


def run(output=OUT,workers=8,wall_seconds=None,limit=None):
    output=Path(output);m=prepare(output)
    if not 1<=workers<=m['workers_max']:raise ValueError('Invalid worker count')
    requested=ordered_inventory(m['inventory']);requested=requested[:limit] if limit else requested
    results={}
    for item in requested:
        path=output/'cities'/f"{item['municipality_code']}.json"
        if path.exists():results[item['municipality_code']]=json.loads(path.read_text())
    pending=queue.Queue()
    for item in requested:
        if item['municipality_code'] not in results:pending.put(item)
    started=time.monotonic();deadline=started+wall_seconds if wall_seconds else float('inf')
    lock=threading.Lock()
    state={'status':'running','started_utc':datetime.now(timezone.utc).isoformat(),'requested_cities':len(requested),
        'domestic_cities':len(m['inventory']),'workers':workers,'manifest_hash':sha256(output/'manifest.json'),
        'limited_run':limit is not None,'publication_allowed':False}
    def checkpoint():
        with lock:done=list(results.values())
        state.update(completed_cities=len(done),pending_cities=len(requested)-len(done),elapsed_seconds=time.monotonic()-started,
            statuses=pd.Series([r['status'] for r in done],dtype=str).value_counts().to_dict())
        duration=[sum(a['seconds'] for a in r.get('attempts',[])) for r in done if r.get('attempts')]
        if duration:
            eta=state['pending_cities']*np.quantile(duration,[.5,.9])/workers
            state['remaining_seconds_median_p90']=eta.tolist()
            state['eta_utc_median_p90']=[(datetime.now(timezone.utc)+timedelta(seconds=float(v))).isoformat() for v in eta]
            state['eta_scope']='Early extrapolation includes observed upgrades; unsampled metropolitan costs can be much larger.'
        save(output/'execution_state.json',state)
    def worker(slot):
        while time.monotonic()<deadline:
            try:item=pending.get_nowait()
            except queue.Empty:return
            result=fit_city(output,item,slot,workers)
            with lock:results[item['municipality_code']]=result
            print(json.dumps({'completed':item['municipality_code'],'status':result['status'],'remaining_queue':pending.qsize()}),flush=True)
    checkpoint()
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(worker,s) for s in range(workers)]
            while not all(f.done() for f in futures):time.sleep(10);checkpoint()
            for future in futures:future.result()
        checkpoint();state['status']='completed' if not state['pending_cities'] else 'incomplete_wall_budget'
        state['publication_allowed']=state['status']=='completed' and not state['limited_run']
    except BaseException as error:
        state['status']='controller_failed';state['error']=repr(error);raise
    finally:checkpoint();save(output/'execution_state.json',state)
    return state


def verify(output=OUT,require_complete=True):
    output=Path(output);m=prepare(output);checked=0;posteriors=0
    records=[]
    for item in m['inventory']:
        path=output/'cities'/f"{item['municipality_code']}.json"
        if not path.exists():
            if require_complete:raise ValueError('National run incomplete')
            continue
        r=json.loads(path.read_text());records.append(r)
        if 'matrix' not in r:continue
        matrix=np.asarray(r['matrix']);low=np.asarray(r['low']);high=np.asarray(r['high']);origin=np.asarray(r['origins'])
        if matrix.shape!=(5,4) or not np.isfinite(matrix).all() or (matrix<0).any():raise ValueError('Invalid matrix')
        if not np.allclose(matrix.sum(1),origin):raise ValueError('Origin mismatch')
        if (low<0).any() or (high<low).any() or (high>origin[:,None]+1e-6).any():raise ValueError('Invalid interval')
        source=output/'draws'/f"{r['municipality_code']}-{r['level']}.npz"
        if sha256(source)!=r['draws_sha256']:raise ValueError('Posterior draws changed')
        draws=np.load(source)['flows']
        if not np.allclose(matrix,draws.mean(0)) or not np.allclose(low,np.quantile(draws,.025,axis=0)) or not np.allclose(high,np.quantile(draws,.975,axis=0)):
            raise ValueError('Draw-before-quantile check failed')
        checked+=20;posteriors+=1
    stats={'passed':True,'complete':len(records)==len(m['inventory']),'municipalities_checked':len(records),
        'expected_municipalities':len(m['inventory']),'posterior_files_checked':posteriors,'flow_cells_checked':checked,
        'sources_unchanged':True,'independent_validation_complete':False}
    save(output/'verification.json',stats);return stats


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['prepare','run','worker','verify']);p.add_argument('--output',type=Path,default=OUT)
    p.add_argument('--workers',type=int,default=8);p.add_argument('--wall-seconds',type=int);p.add_argument('--limit',type=int)
    p.add_argument('--code',type=int);p.add_argument('--level',choices=['primary','long'],default='primary');p.add_argument('--allow-partial',action='store_true')
    a=p.parse_args()
    if a.stage=='prepare':r=prepare(a.output);print(json.dumps({'municipalities':len(r['inventory'])}));return
    if a.stage=='worker':fit_attempt(a.output,a.code,a.level);return
    if a.stage=='verify':print(json.dumps(verify(a.output,not a.allow_partial),indent=2));return
    print(json.dumps(run(a.output,a.workers,a.wall_seconds,a.limit),indent=2))


if __name__=='__main__':main()
