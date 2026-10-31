"""Resumable spatial experiment with process isolation and honest failure states.

python -m elections.spatial_runner --help
No command modifies the original national estimates or deploys a website.
"""
import argparse
import copy
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import numpy as np
import pandas as pd

from .hierarchy_inventory import sha256, write_json
from .spatial import OUT, ROOT, KEY, seed_for, partition
from .spatial_experiment import prepare, build_groupings, data_arrays, export_membership, SCENARIOS, METHODS
from .spatial_validation import generate, aggregate, flow_scores, score_posterior, summarize_dataset, gate_cell

REQUIRED_SUPPORTS = ('municipality','geographic_group')


def clean(value):
    if isinstance(value,dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,np.ndarray):return clean(value.tolist())
    if isinstance(value,(float,np.floating)) and not np.isfinite(value):return None
    if isinstance(value,np.generic):return value.item()
    return value


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+f'.{os.getpid()}.{threading.get_ident()}.tmp')
    write_json(temporary,clean(value));temporary.replace(path)


def effective_results(records):
    """Upgrade computation on the same data without creating new replications.

    Raw result files are immutable. Separate confirmation rows remain available
    as computational diagnostics; admission uses their completed computation in
    place of the original warning, never in addition to it within a data phase.
    """
    def key(job,phase=None):
        return tuple([phase or job['phase']]+[job[k] for k in ['population_bin','municipality_code','scenario','replicate','method','config','variant']])
    confirmations={key(r['job'],r['job']['data_phase']):r for r in records
                   if r['job']['phase']=='confirmation' and r['job'].get('data_phase')}
    output=[]
    for original in records:
        confirmation=confirmations.get(key(original['job'])) if original['job']['phase']!='confirmation' else None
        result=copy.deepcopy(confirmation or original)
        if confirmation:
            completed=confirmation['diagnostics']['status'] in ['ok','diagnostic_warning']
            if completed and original.get('data_seed')!=confirmation.get('data_seed'):
                raise ValueError('Confirmation used different generated data')
            result['job']=copy.deepcopy(original['job'])
        result['original_status']=original['diagnostics']['status']
        result['status_source']='confirmation' if confirmation else 'original'
        output.append(result)
    return output


def design_hash(output):
    return sha256(Path(output)/'manifest.json')


def config_parts(config):
    a,b=config.split('_')
    return int(a[1:]),float(b[1:])


def candidate_configurations(output=OUT):
    """Cheap geometric shortlist, never a selected reliability threshold."""
    output=Path(output)
    manifest=prepare(output)
    file=output/'candidate_configurations.json'
    if file.exists():return {int(k):v for k,v in json.loads(file.read_text())['candidates'].items()}
    feasibility=pd.read_csv(output/'group_feasibility.csv')
    result={}
    for b in range(1,6):
        block=feasibility[feasibility.population_bin.eq(b)&feasibility.split.eq('development')].copy()
        # Pick one partition for small, medium and large targets. Full 24-way
        # feasibility remains exported; simulation selection is still pending.
        chosen=[]
        for targets in [(5,10),(20,40),(80,160)]:
            pool=block[block.config.map(lambda c:config_parts(c)[0] in targets)].copy()
            pool['cap']=pool.config.map(lambda c:config_parts(c)[1])
            pool=pool.sort_values(['undersized_electorate_fraction','cap','median_diameter_km','config'])
            if len(pool):chosen.append(str(pool.iloc[0].config))
        result[b]=list(dict.fromkeys(chosen))
    save(file,{'manifest_hash':design_hash(output),'status':'geographic_shortlist_not_validated_threshold',
        'rule':'Three target-scale bands, minimize development undersized-electorate fraction then cap then diameter; no generated or second-round outcomes.',
        'candidates':result})
    export_membership(output,result)
    return result


def job_path(output,job):
    return Path(output)/'jobs'/f"{job['phase']}-b{job['population_bin']}-{job['municipality_code']}-{job['scenario']}-r{job['replicate']:04d}-{job['method']}-{job['config']}-{job['variant']}.json"


def load_city(output,code):
    sections=pd.read_csv(Path(output)/'sample_sections.csv.gz')
    s=sections[sections.municipality_code.eq(code)].reset_index(drop=True)
    if s.empty:raise ValueError('No verified sections for municipality')
    return s,data_arrays(s)


def validate_job_scope(manifest,job,actual_bin):
    if int(job['population_bin'])!=int(actual_bin):raise ValueError('Job population bin disagrees with frozen data')
    city=next((c for c in manifest['sample'] if c['municipality_code']==job['municipality_code']),None)
    data_phase=job.get('data_phase',job['phase'])
    if job['phase']=='validation' and data_phase!='validation':raise ValueError('Validation cannot reuse development data streams')
    if data_phase in ['development','validation']:
        expected='development' if data_phase=='development' else 'validation'
        if city is None or city['split']!=expected:raise ValueError('Dataset belongs to the wrong frozen municipal split')


def baseline_fit(x,y,seed):
    from .model import fit_transition
    if len(x)<10 or np.linalg.matrix_rank(x/x.sum(1,keepdims=True))<5:
        return None,{'status':'too_few_sections_or_rank_deficient'}
    base=fit_transition(x,y)
    if base['status']!='ok':return None,{'status':base['status']}
    rng=np.random.default_rng(seed)
    draws=[]
    for _ in range(150):
        index=rng.integers(0,len(x),len(x))
        if np.linalg.matrix_rank(x[index]/x[index].sum(1,keepdims=True))<5:continue
        fitted=fit_transition(x[index],y[index])
        if fitted['status']=='ok':draws.append(fitted['p'])
    if len(draws)<120:
        return None,{'status':'insufficient_bootstrap','successful':len(draws)}
    return (base['p'],np.asarray(draws)),{'status':'ok','successful':len(draws),
        'interval_type':'150-resample independent-section bootstrap sensitivity range; coverage assessed in simulations'}


def evaluate_baseline(fitted,x,truth,supports):
    p,draws=fitted
    rows=[]
    for name,labels in supports.items():
        origins=aggregate(x,labels)
        d=draws[:,None]*origins[None,:,:,None]
        rows.extend(flow_scores(d,aggregate(truth,labels),origins,name,point=origins[:,:,None]*p))
    return rows


def real_estimates(posterior,x,group,supports,extension,common):
    from .spatial_model import flow_draws
    grouped=flow_draws(posterior,x,group,supports,extension,common)
    rows=[]
    for support,d in grouped.items():
        origins=aggregate(x,supports[support])
        mean=d.mean(0);low,high=np.quantile(d,[.025,.975],axis=0)
        for unit in range(len(origins)):
            for g in range(5):
                for k in range(4):
                    n=float(origins[unit,g]);N=float(origins[unit].sum())
                    rows.append({'support':support,'unit':unit,'origin':g,'destination':k,
                        'electorate':N,'origin_voters':n,'estimate':float(mean[unit,g,k]),
                        'low':float(low[unit,g,k]),'high':float(high[unit,g,k]),
                        'rate_pp':float(mean[unit,g,k]/n*100) if n else None,
                        'width_rate_pp':float((high[unit,g,k]-low[unit,g,k])/n*100) if n else None,
                        'interval_type':'Pointwise 95% conditional posterior credible interval'})
    return rows


def execute_job(output,job):
    output=Path(output)
    manifest=prepare(output)
    s,(x,y,points,admin)=load_city(output,job['municipality_code'])
    validate_job_scope(manifest,job,s.population_bin.iloc[0])
    if job.get('data_phase',job['phase'])=='validation':
        lock=output/'selected_procedure.json'
        if not lock.exists():raise ValueError('Validation requires a frozen selection')
        selected=json.loads(lock.read_text())
        if selected['manifest_hash']!=design_hash(output) or job['config'] not in selected['candidates'].get(str(job['population_bin']),[]):
            raise ValueError('Validation configuration is not the frozen development selection')
    data_phase=job.get('data_phase',job['phase'])
    seed=seed_for(manifest['seed'],data_phase,job['population_bin'],job['scenario'],job['replicate'])
    # Identical data stream across methods/configurations/prior variants.
    truth=None
    if job['scenario']!='observed':
        x,y,truth,realized,points=generate(x,admin,points,job['scenario'],seed)
    target,cap=config_parts(job['config'])
    geography=partition(points,target,cap,manifest['neighbours'])
    supports={'municipality':np.zeros(len(x),int),'original_place':admin,'geographic_group':geography,'section':np.arange(len(x))}
    method=job['method']
    common=method=='municipal_bayes'
    extended=method.endswith('_extended')
    group=admin if method.startswith('administrative') else geography
    if common:group=np.zeros(len(x),int)
    result={'job':job,'manifest_hash':design_hash(output),'seed':seed,'data_seed':seed,
            'sections':len(x),'electorate':int(x.sum()),'scores':[]}
    started=time.monotonic()
    if method=='municipal_wls':
        fitted,diagnostic=baseline_fit(x,y,seed)
        result['diagnostics']=diagnostic
        if fitted is not None:
            if truth is not None:
                rows=evaluate_baseline(fitted,x,truth,supports)
            else:
                # Use bootstrap interval endpoints but original WLS point estimate.
                p,draws=fitted
                rows=[]
                for support,labels in supports.items():
                    if support=='section':continue
                    origins=aggregate(x,labels);d=draws[:,None]*origins[None,:,:,None]
                    low,high=np.quantile(d,[.025,.975],axis=0)
                    for unit in range(len(origins)):
                        for g in range(5):
                            for k in range(4):
                                n=float(origins[unit,g]);v=float(origins[unit,g]*p[g,k])
                                rows.append({'support':support,'unit':unit,'origin':g,'destination':k,
                                    'electorate':float(origins[unit].sum()),'origin_voters':n,'estimate':v,
                                    'low':float(low[unit,g,k]),'high':float(high[unit,g,k]),
                                    'rate_pp':float(100*p[g,k]) if n else None,
                                    'width_rate_pp':float(100*(high[unit,g,k]-low[unit,g,k])/n) if n else None,
                                    'interval_type':diagnostic['interval_type']})
                result['estimates']=rows
    else:
        from .spatial_model import fit
        fit_x,fit_y,fit_group=x,y,group
        if method=='literal_aggregation':
            fit_x,fit_y=aggregate(x,geography),aggregate(y,geography)
            fit_group=np.arange(len(fit_x))
        sampling=manifest['sampling'] if job['phase'] in ['real','profile','validation'] else manifest['screen_sampling']
        if job.get('confirmation'):sampling=manifest['confirmation_sampling']
        posterior,diagnostic=fit(fit_x,fit_y,fit_group,seed=seed_for(seed,method,job['config'],job['variant']),
            extension=extended,common=common,variant=job['variant'],**sampling)
        result['diagnostics']=diagnostic
        # Literal aggregation implies common rates within each summed group.
        # Its probabilities can be evaluated on original sections for fixed-support scoring.
        if truth is not None:
            rows=score_posterior(posterior,x,group,truth,supports,extended,common)
        else:
            result['estimates']=real_estimates(posterior,x,group,supports,extended,common)
        if job['phase'] in ['profile','real','confirmation'] or job.get('confirmation'):
            destination=output/'fits'/job_path(output,job).stem
            destination.parent.mkdir(exist_ok=True)
            np.savez_compressed(destination.with_suffix('.npz'),**posterior)
    if truth is not None and result['diagnostics']['status'] in ['ok','diagnostic_warning']:
        result['scores']=summarize_dataset(rows)
        # Full original-section/cell rows are useful for audits, not MC replication.
        if job['replicate']==0:
            destination=output/'flow_audits'/job_path(output,job).with_suffix('.csv.gz').name
            destination.parent.mkdir(exist_ok=True)
            pd.DataFrame(rows).to_csv(destination,index=False)
    result['elapsed_seconds']=time.monotonic()-started
    save(job_path(output,job),result)
    return result


def run_one(output,job,timeout=300,slot=0):
    path=job_path(output,job)
    if path.exists():
        result=json.loads(path.read_text())
        if result['manifest_hash']!=design_hash(output):raise ValueError('Cached result belongs to another design')
        return result
    path.parent.mkdir(parents=True,exist_ok=True)
    spec=path.with_suffix('.job.json');save(spec,job)
    env=os.environ.copy()
    env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MPLCONFIGDIR='/tmp/elections-matplotlib',
               XLA_FLAGS='--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1')
    available=sorted(os.sched_getaffinity(0))
    chosen=available[(slot%4)*max(1,len(available)//4):(slot%4+1)*max(1,len(available)//4)]
    command=['taskset','-c',','.join(map(str,chosen)),sys.executable,'-m','elections.spatial_runner','worker','--output',str(output),'--job',str(spec)]
    log=path.with_suffix('.log')
    started=time.monotonic()
    with log.open('w') as stream:
        process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        try:
            code=process.wait(timeout=timeout)
            status='process_failed' if code else 'missing_result'
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait()
            status='resource_timeout'
    if not path.exists():
        result={'job':job,'manifest_hash':design_hash(output),'diagnostics':{'status':status},
                'scores':[],'elapsed_seconds':time.monotonic()-started,'log':str(log.relative_to(output))}
        save(path,result)
    result=json.loads(path.read_text())
    print(json.dumps({'completed':path.name,'status':result['diagnostics']['status'],'seconds':round(result['elapsed_seconds'],1)}),flush=True)
    return result


def run_jobs(output,jobs,workers=4,timeout=300):
    # Each worker owns one CPU partition; subprocess isolation also releases JAX caches.
    def batch(slot):
        return [run_one(output,job,timeout,slot) for job in jobs[slot::workers]]
    results=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(batch,slot) for slot in range(workers)]):
            results.extend(future.result())
    return results


def make_job(city,phase,scenario,replicate,method,config,variant='primary',**kwargs):
    return {'municipality_code':int(city['municipality_code']),'population_bin':int(city['population_bin']),
            'phase':phase,'scenario':scenario,'replicate':int(replicate),'method':method,'config':config,'variant':variant,**kwargs}


def profiles(output,workers=4,timeout=300):
    m=prepare(output);short=candidate_configurations(output)
    jobs=[]
    for b in range(1,6):
        cities=sorted([c for c in m['sample'] if c['population_bin']==b and c['split']=='development'],key=lambda c:c['sections'])
        # Full small/median/large designs in every bin, including a metropolitan design.
        choices=[cities[i] for i in sorted({0,len(cities)//2,len(cities)-1})]
        for city in choices:
            for method in ['municipal_bayes','geographic','geographic_extended']:
                jobs.append(make_job(city,'profile','observed',0,method,short[b][0]))
    result=run_jobs(output,jobs,workers,timeout)
    save(Path(output)/'resource_profiles.json',{'jobs':[{**r['job'],**r['diagnostics'],'elapsed_seconds':r['elapsed_seconds']} for r in result],
        'policy':'Full observed designs; timeout does not certify a subsample or all other designs.'})
    return result


def simulation_jobs(output,phase,scenario,replicates,candidates):
    m=prepare(output);jobs=[]
    split='development' if phase=='development' else 'validation'
    for b in range(1,6):
        cities=sorted([c for c in m['sample'] if c['population_bin']==b and c['split']==split],key=lambda c:c['municipality_code'])
        for r in range(replicates):
            city=cities[r%len(cities)]
            for method in METHODS:
                if phase=='validation' and method=='literal_aggregation':continue
                configurations=candidates.get(b,[]) if method.startswith('geographic') or method in ['literal_aggregation','municipal_wls'] else candidates.get(b,[])[:1]
                for config in configurations:
                    jobs.append(make_job(city,phase,scenario,r,method,config))
    return jobs


def commit_validation_checkpoint(output,replicates,candidates):
    """Only complete, prespecified looks can authorize scaling, not live peeks."""
    output=Path(output)
    if replicates not in [100,500,1000]:return {}
    selection_path=output/'selected_procedure.json'
    if not selection_path.exists():return {}
    selection=json.loads(selection_path.read_text())
    checkpoints_path=output/'validation_checkpoints.json'
    checkpoints=json.loads(checkpoints_path.read_text()) if checkpoints_path.exists() else {}
    digest=design_hash(output)
    for b,configs in candidates.items():
        if not configs:continue
        expected=[]
        for scenario in SCENARIOS:
            expected.extend(simulation_jobs(output,'validation',scenario,replicates,{b:configs}))
        complete=bool(expected)
        for job in expected:
            path=job_path(output,job)
            if not path.exists():complete=False;break
            result=json.loads(path.read_text())
            if result['manifest_hash']!=digest:raise ValueError('Checkpoint result belongs to another design')
            if result['diagnostics']['status']=='diagnostic_warning':
                upgraded={**job,'phase':'confirmation','data_phase':'validation','confirmation':True}
                path=job_path(output,upgraded)
                if not path.exists():complete=False;break
                if json.loads(path.read_text())['manifest_hash']!=digest:raise ValueError('Upgrade belongs to another design')
        if complete:
            checkpoints[str(b)]={'replicates':replicates,'manifest_hash':digest,
                'selection_hash':sha256(selection_path),'procedure':selection['procedures'][str(b)],
                'complete_scenarios':SCENARIOS,'method_jobs':len(expected)}
    save(checkpoints_path,checkpoints)
    return checkpoints


def consolidate(output):
    output=Path(output);m=prepare(output)
    jobs=[];scores=[];estimates=[];records=[]
    for path in sorted((output/'jobs').glob('*.json')):
        if path.name.endswith('.job.json'):continue
        result=json.loads(path.read_text())
        if result.get('manifest_hash')!=design_hash(output):raise ValueError('Result manifest mismatch: '+str(path))
        records.append(result)
    pd.DataFrame([{**r['job'],**r['diagnostics'],'elapsed_seconds':r['elapsed_seconds']} for r in records]).to_csv(output/'raw_fit_status.csv',index=False)
    for result in effective_results(records):
        job=result['job'];status=result['diagnostics']['status']
        provenance={'original_status':result['original_status'],'status_source':result['status_source']}
        jobs.append({**job,**result['diagnostics'],**provenance,'elapsed_seconds':result['elapsed_seconds']})
        for row in result.get('scores',[]):scores.append({**job,'status':status,**provenance,**row})
        for row in result.get('estimates',[]):estimates.append({**job,'status':status,**provenance,**row})
    jobs=pd.DataFrame(jobs);scores=pd.DataFrame(scores);estimates=pd.DataFrame(estimates)
    jobs.to_csv(output/'fit_status.csv',index=False)
    scores.to_csv(output/'simulation_metrics.csv.gz',index=False)
    estimates.to_csv(output/'estimates.csv.gz',index=False)
    summaries=[]
    if len(scores):
        group_columns=['phase','population_bin','scenario','method','config','support','origin','destination']
        base_columns=['phase','population_bin','scenario','config','support','origin','destination']
        attempt_columns=['phase','population_bin','scenario','method','config']
        baselines=scores[scores.method.eq('municipal_wls')]
        baseline_lookup={key:block for key,block in baselines.groupby(base_columns)}
        baseline_template_lookup={key:block for key,block in baselines.groupby(base_columns+['municipality_code'])}
        attempt_lookup={key:block for key,block in jobs.groupby(attempt_columns)}
        attempt_template_lookup={key:block for key,block in jobs.groupby(attempt_columns+['municipality_code'])}
        partitions=[(dict(zip(group_columns,key)),block,'bin') for key,block in scores.groupby(group_columns)]
        partitions += [(dict(zip(group_columns+['municipality_code'],key)),block,'municipal_template')
                       for key,block in scores.groupby(group_columns+['municipality_code'])]
        for labels,block,calibration_scope in partitions:
            # Only computationally sound runs can authorize scale. Exploratory
            # results remain in raw exports, never silently dropped from failures.
            good=block[block.status.eq('ok')]
            baseline_key=tuple(labels[k] for k in base_columns)
            base=baseline_lookup.get(baseline_key)
            if calibration_scope=='municipal_template':base=baseline_template_lookup.get(baseline_key+(labels['municipality_code'],))
            comparison=gate_cell(good,base,m['gate'],labels['phase'],good.replicate.nunique()) if len(good) else {'reasons':['no_computationally_valid_datasets']}
            if calibration_scope=='municipal_template' and 'coverage_monte_carlo_imprecise' in comparison['reasons']:
                # One-percentage-point MCSE is required for the primary bin
                # result. Templates still require the coverage lower bound and
                # report their own precision; they cannot hide behind an average.
                comparison['reasons'].remove('coverage_monte_carlo_imprecise')
            attempt_key=tuple(labels[k] for k in attempt_columns)
            attempted=attempt_lookup[attempt_key] if calibration_scope=='bin' else attempt_template_lookup[attempt_key+(labels['municipality_code'],)]
            failed_fraction=float((~attempted.status.eq('ok')).mean())
            if failed_fraction>m['gate']['max_failure_fraction']:comparison['reasons'].append('computational_failure_fraction')
            summaries.append({**labels,'calibration_scope':calibration_scope,'datasets':int(block.replicate.nunique()),'valid_datasets':int(good.replicate.nunique()),
                'failure_fraction':failed_fraction,'decision':('not_applicable' if comparison.get('not_applicable') else 'pass') if not comparison['reasons'] else 'not_passed',**comparison})
    save(output/'simulation_summary.json',summaries)
    decisions=[]
    candidates=candidate_configurations(output)
    selection_path=output/'selected_procedure.json'
    selection=json.loads(selection_path.read_text()) if selection_path.exists() else {}
    checkpoint_path=output/'validation_checkpoints.json'
    checkpoints=json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {}
    for b in range(1,6):
        for method,config in [(method,config) for method in ['geographic','geographic_extended'] for config in candidates[b]]:
            cells=[r for r in summaries if r['population_bin']==b and r['config']==config and r['method']==method]
            dev=[r for r in cells if r['phase']=='development' and r['support'] in REQUIRED_SUPPORTS]
            val=[r for r in cells if r['phase']=='validation' and r['support'] in REQUIRED_SUPPORTS]
            scenarios={r['scenario'] for r in val}
            substantive={reason for r in dev for reason in r['reasons'] if reason in ['absolute_flow_error','origin_rate_error','interval_too_wide','boundary_false_positives']}
            # Statistical summaries alone cannot authorize scale: require real
            # prior/disagreement investigations and a separately completed gate.
            audits_path=output/'real_comparison_gate.json'
            audit=json.loads(audits_path.read_text()) if audits_path.exists() else {}
            real_pass=audit.get(str(b),{}).get(f'{method}:{config}',{}).get('passed',False)
            procedure=selection.get('procedures',{}).get(str(b)) or {}
            selected=(selection.get('manifest_hash')==design_hash(output) and procedure.get('config')==config and procedure.get('method')==method)
            checkpoint=checkpoints.get(str(b),{})
            n=checkpoint.get('replicates',0)
            committed=(selected and checkpoint.get('manifest_hash')==design_hash(output) and
                checkpoint.get('selection_hash')==sha256(selection_path) and checkpoint.get('procedure')==procedure and n in [100,500,1000])
            if committed:
                attempted=jobs[(jobs.phase=='validation')&(jobs.population_bin==b)&(jobs.method==method)&(jobs.config==config)]
                committed=all(set(attempted[attempted.scenario.eq(s)].replicate)==set(range(n)) for s in SCENARIOS)
            full=committed and bool(val) and scenarios==set(SCENARIOS) and set(REQUIRED_SUPPORTS)<={r['support'] for r in val} and all(r['decision'] in ['pass','not_applicable'] for r in val) and real_pass
            decision='scale' if full else ('do_not_scale' if substantive else 'insufficient_evidence')
            decisions.append({'population_bin':b,'method':method,'config':config,'decision':decision,
                'required_validation_supports':list(REQUIRED_SUPPORTS),
                'resolution_diagnostics':{support:('simulation_passed' if committed and [r for r in cells if r['phase']=='validation' and r['support']==support] and
                    all(r['decision'] in ['pass','not_applicable'] for r in cells if r['phase']=='validation' and r['support']==support) and
                    {r['scenario'] for r in cells if r['phase']=='validation' and r['support']==support}==set(SCENARIOS) else 'not_validated')
                    for support in ['municipality','original_place','section','geographic_group']},
                'threshold_status':'validated' if full else 'no_supported_threshold',
                'development_datasets':max([r['datasets'] for r in dev],default=0),
                'validation_scenarios':sorted(scenarios),'reasons':sorted(substantive) if substantive else
                    ([] if full else ['independent_validation_and_full_flow_support_not_complete']),
                'scope':'Qualification requires municipality and new geographic-group validation. Original-place and section results are separately assessed and never inherit group qualification; observed individual transitions remain unknown.'})
    save(output/'threshold_profiles.json',decisions)
    return jobs,scores,estimates,summaries,decisions


def freeze_selection(output=OUT):
    """No held-out outcomes may influence development selection or its lock."""
    output=Path(output);m=prepare(output)
    jobs,scores,_,summary,decisions=consolidate(output)
    chosen={};procedures={};evidence={};pending=[]
    for b in range(1,6):
        eligible=[]
        for method,config in [(method,config) for method in ['geographic','geographic_extended'] for config in candidate_configurations(output)[b]]:
            cells=[r for r in summary if r['phase']=='development' and r['population_bin']==b and
                   r['config']==config and r['method']==method and r.get('support','municipality') in REQUIRED_SUPPORTS]
            scenarios={r['scenario'] for r in cells}
            # Development need not have final MC precision, but all substantive
            # performance, diagnostic and 30-dataset requirements must pass.
            ignored={'independent_validation_incomplete','coverage_monte_carlo_imprecise'}
            reasons={v for r in cells for v in r['reasons'] if v not in ignored}
            complete=(scenarios==set(SCENARIOS) and set(REQUIRED_SUPPORTS)<={r.get('support','municipality') for r in cells} and
                      all(r['datasets']>=30 for r in cells if r.get('calibration_scope','bin')=='bin'))
            attempted_complete=False
            if jobs is not None and len(jobs):
                attempts=jobs[(jobs.phase=='development')&(jobs.population_bin==b)&(jobs.config==config)&(jobs.method==method)]
                attempted_complete=all(attempts[attempts.scenario.eq(s)].replicate.nunique()>=30 for s in SCENARIOS)
            rejected=any(r['population_bin']==b and r['config']==config and r.get('method')==method and r['decision']=='do_not_scale' and
                         r['development_datasets']>=30 for r in decisions or [])
            if not complete and not attempted_complete and not rejected:pending.append(f'{b}:{method}:{config}')
            evidence[f'{b}:{method}:{config}']={'complete':complete,'all_scenarios_attempted':attempted_complete,'reasons':sorted(reasons)}
            if complete and not reasons:
                eligible.append({'method':method,'config':config})
        feasibility=pd.read_csv(output/'group_feasibility.csv')
        local=feasibility[(feasibility.population_bin==b)&(feasibility.split=='development')].set_index('config')
        eligible=sorted(eligible,key=lambda p:(local.loc[p['config'],'median_diameter_km'],
            p['method']!='geographic',config_parts(p['config'])[0],config_parts(p['config'])[1]))
        procedures[b]=eligible[0] if eligible else None
        chosen[b]=[eligible[0]['config']] if eligible else []
    path=output/'selected_procedure.json'
    value={'manifest_hash':design_hash(output),'candidates':chosen,'procedures':procedures,'development_evidence':evidence,
        'development_results_hash':hashlib.sha256(json.dumps(clean(scores[scores.phase.eq('development')].to_dict('records')) if len(scores) else [],sort_keys=True).encode()).hexdigest(),
        'rule':'Most local development-passing geographic procedure per bin; prefer the simpler model for equal locality. Method and grouping freeze together; held-out outcomes not consulted.',
        'status':'selected' if any(chosen.values()) else 'no_development_supported_threshold'}
    if pending:
        value.update(status='selection_deferred',pending_configurations=pending)
        save(output/'selection_status.json',value)
        return value
    if path.exists() and json.loads(path.read_text())!=clean(value):
        raise ValueError('Selection is frozen; create a separate experiment for a revised procedure')
    save(path,value)
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['prepare','group','profile','screen','select','validate','real','summarize','all','worker'])
    parser.add_argument('--output',type=Path,default=OUT)
    parser.add_argument('--job',type=Path)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--timeout',type=int,default=300)
    parser.add_argument('--wall-seconds',type=int,default=3600,help='New-work budget for the complete staged workflow; completed jobs resume')
    parser.add_argument('--replicates',type=int)
    parser.add_argument('--scenarios',nargs='+',choices=SCENARIOS)
    parser.add_argument('--bins',nargs='+',type=int,choices=range(1,6))
    parser.add_argument('--methods',nargs='+',choices=METHODS)
    args=parser.parse_args();out=args.output
    if not 1<=args.workers<=4:parser.error('workers must be 1–4')
    if args.phase=='worker':execute_job(out,json.loads(args.job.read_text()));return
    if args.phase=='all':
        from scripts.run_spatial_pooling import run
        run(out,args.workers,args.timeout,args.wall_seconds)
        return
    m=prepare(out)
    if args.phase=='prepare':return
    if args.phase=='select':freeze_selection(out);return
    if args.phase in ['group','all']:build_groupings(out)
    candidates=candidate_configurations(out)
    if args.phase in ['profile','all']:profiles(out,args.workers,args.timeout)
    if args.phase in ['screen','validate','all']:
        phase='validation' if args.phase=='validate' else 'development'
        if phase=='validation':
            lock=out/'selected_procedure.json'
            if not lock.exists():raise ValueError('Validation requires a development-selected, frozen selected_procedure.json; no automatic access to held-out outcomes')
            chosen=json.loads(lock.read_text())
            if chosen['manifest_hash']!=design_hash(out):raise ValueError('Selected procedure manifest mismatch')
            candidates={int(k):v for k,v in chosen['candidates'].items()}
        scenarios=args.scenarios or ['within_building','contextual']+[s for s in SCENARIOS if s not in ['within_building','contextual']]
        for scenario in scenarios:
            n=args.replicates or (100 if phase=='validation' else 30)
            jobs=simulation_jobs(out,phase,scenario,n,candidates)
            if args.bins:jobs=[j for j in jobs if j['population_bin'] in args.bins]
            if args.methods:jobs=[j for j in jobs if j['method'] in args.methods]
            run_jobs(out,jobs,args.workers,args.timeout)
            if phase=='validation':
                upgrades=[]
                for job in jobs:
                    if json.loads(job_path(out,job).read_text())['diagnostics']['status']=='diagnostic_warning':
                        upgrades.append({**job,'phase':'confirmation','data_phase':'validation','confirmation':True})
                run_jobs(out,upgrades,args.workers,args.timeout)
            consolidate(out)
        if phase=='validation':commit_validation_checkpoint(out,n,candidates)
    if args.phase=='real':
        jobs=[]
        for city in m['sample']:
            if args.bins and city['population_bin'] not in args.bins:continue
            for method in args.methods or METHODS:
                if method=='literal_aggregation' and city['split']!='development':continue
                configs=candidates[city['population_bin']] if method.startswith('geographic') else candidates[city['population_bin']][:1]
                for config in configs:
                    for variant in (['primary'] if method=='municipal_wls' else ['primary','tighter','wider']):
                        jobs.append(make_job(city,'real','observed',0,method,config,variant))
        run_jobs(out,jobs,args.workers,args.timeout)
    if args.phase not in ['prepare','group']:consolidate(out)


if __name__=='__main__':main()
