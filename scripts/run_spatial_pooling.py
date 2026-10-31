"""Execute the staged experiment, stopping regimes that fail prespecified gates.

Every stage resumes immutable completed jobs. Full validation can be expensive.
The wall budget pauses new work with explicit pending counts; it never passes a
regime. Invoke again to resume. Worker timeouts are independent of this budget.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from elections.spatial import OUT, verify_geography
from elections.spatial_experiment import prepare, build_groupings, SCENARIOS
from elections.spatial_runner import (candidate_configurations,make_job,run_one,job_path,simulation_jobs,
    consolidate,freeze_selection,save,design_hash,commit_validation_checkpoint,REQUIRED_SUPPORTS)


def run(output=OUT,workers=4,timeout=300,wall_seconds=3600):
    output=Path(output);started=time.monotonic()
    deadline=started+wall_seconds
    if not (output/'section_coordinates.csv.gz').exists():verify_geography(output)
    m=prepare(output);build_groupings(output);candidates=candidate_configurations(output)
    state={'manifest_hash':design_hash(output),'status':'running','completed_stages':[],'pending_jobs':0,
           'worker_timeout_seconds':timeout,'wall_budget_seconds':wall_seconds,'resources_are_not_statistical_failures':True}

    def checkpoint():
        state['elapsed_seconds']=time.monotonic()-started
        save(output/'execution_state.json',state)

    def batch(jobs):
        pending=[j for j in jobs if not job_path(output,j).exists()]
        state['pending_jobs']=len(pending);checkpoint()
        def worker(slot):
            for job in pending[slot::workers]:
                if time.monotonic()>=deadline:return
                run_one(output,job,timeout,slot)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(worker,i) for i in range(workers)]):future.result()
        remaining=sum(not job_path(output,j).exists() for j in jobs)
        state['pending_jobs']=remaining
        if remaining:
            state['status']='incomplete_resource_budget';checkpoint();return False
        checkpoint();return True

    # Profile progressively larger full designs in every bin before calibration.
    # Other designs/configurations retain their own per-fit limits; a timeout in
    # a representative city is never extrapolated to unattempted cities.
    profile=[]
    for b in range(1,6):
        cities=sorted([c for c in m['sample'] if c['population_bin']==b and c['split']=='development'],key=lambda c:c['sections'])
        for index in sorted({0,len(cities)//2,len(cities)-1}):
            city=cities[index]
            for method in ['municipal_bayes','geographic','geographic_extended']:
                profile.append(make_job(city,'profile','observed',0,method,candidates[b][0]))
    if not batch(profile):return finish(output,state)
    state['completed_stages'].append('full_design_resource_and_diagnostic_profiles');checkpoint()
    # Profile failures are not proof of statistical inaccuracy; preserve broad
    # simulation evidence while withholding unsupported regime claims.
    active={b:list(v) for b,v in candidates.items()}
    for scenario in ['within_building','contextual']+[v for v in SCENARIOS if v not in ['within_building','contextual']]:
        jobs=simulation_jobs(output,'development',scenario,30,active)
        if not batch(jobs):return finish(output,state)
        _,_,_,summary,decisions=consolidate(output)
        state['completed_stages'].append('development_'+scenario)
        # A candidate can be falsified by one critical scenario. Upgrade every
        # warning on the same data before using it for accuracy/selection; short
        # sampling budgets cannot masquerade as statistical model failures.
        confirmations=[]
        for job in jobs:
            if job['method']=='municipal_wls':continue
            result=json.loads(job_path(output,job).read_text())
            if result['diagnostics']['status']=='diagnostic_warning':
                confirmations.append({**job,'phase':'confirmation','data_phase':'development','confirmation':True})
        if not batch(confirmations):return finish(output,state)
        # Use the upgraded same-data results for this rejection decision.
        # The summary collected before confirmations still describes short fits.
        _,_,_,summary,decisions=consolidate(output)
        rejected=[]
        for b,configs in active.items():
            keep=[]
            for config in configs:
                evidence=[r for r in decisions if r['population_bin']==b and r['config']==config]
                if evidence and all(r['decision']=='do_not_scale' for r in evidence):rejected.append((b,config))
                else:keep.append(config)
            active[b]=keep
        state['development_rejected_configurations']=state.get('development_rejected_configurations',[])+rejected
        checkpoint()
        if not any(active.values()):break
    selection=freeze_selection(output)
    if selection['status']=='selection_deferred':
        state['status']='incomplete_development_evidence';checkpoint()
        return finish(output,state)
    state['completed_stages'].append('development_selection_frozen');checkpoint()
    chosen={int(k):v for k,v in selection['candidates'].items()}
    if any(chosen.values()):
        remaining={b:list(configs) for b,configs in chosen.items()}
        procedures={int(k):v for k,v in selection['procedures'].items() if v is not None}
        for n in [100,500,1000]:
            for scenario in SCENARIOS:
                validation_jobs=simulation_jobs(output,'validation',scenario,n,remaining)
                if not batch(validation_jobs):return finish(output,state)
                upgrades=[]
                for job in validation_jobs:
                    result=json.loads(job_path(output,job).read_text())
                    if result['diagnostics']['status']=='diagnostic_warning':
                        upgrades.append({**job,'phase':'confirmation','data_phase':'validation','confirmation':True})
                if not batch(upgrades):return finish(output,state)
            commit_validation_checkpoint(output,n,remaining)
            _,_,_,summary,_=consolidate(output)
            relevant=[r for r in summary if r['phase']=='validation' and r['population_bin'] in procedures and
                      r['method']==procedures[r['population_bin']]['method'] and r['config']==procedures[r['population_bin']]['config'] and
                      r['support'] in REQUIRED_SUPPORTS]
            # Extend only imprecise calibration, never repeat until a biased
            # method happens to pass. Clear failures halt this expansion branch.
            for b in remaining:
                cells=[r for r in relevant if r['population_bin']==b]
                substantive=[v for r in cells for v in r['reasons'] if v not in ['coverage_monte_carlo_imprecise','coverage_below_floor_or_unresolved','independent_validation_incomplete']]
                if cells and (all(r['decision'] in ['pass','not_applicable'] for r in cells) or substantive):remaining[b]=[]
            if not any(remaining.values()):break
        state['completed_stages'].append('independent_validation');checkpoint()
    # Real comparisons are useful even when scaling fails. No selection uses
    # these observed second-round results. Prior variants remain explicit.
    real=[]
    cities=m['sample']
    if m['historical_check']:
        import pandas as pd
        inventory=pd.read_csv(output/'municipality_inventory.csv')
        cities=cities+[dict(inventory[inventory.municipality_code.eq(code)].iloc[0],split='historical') for code in m['historical_check']]
    for city in cities:
        for method in ['municipal_wls','municipal_bayes','administrative','administrative_extended','geographic','geographic_extended']:
            for config in candidates[city['population_bin']] if method.startswith('geographic') else candidates[city['population_bin']][:1]:
                for variant in ['primary'] if method=='municipal_wls' else ['primary','tighter','wider']:
                    real.append(make_job(city,'real','observed',0,method,config,variant))
    if not batch(real):return finish(output,state)
    upgrades=[]
    for job in real:
        result=json.loads(job_path(output,job).read_text())
        if result['diagnostics']['status']=='diagnostic_warning':
            upgrades.append({**job,'phase':'confirmation','data_phase':'real','confirmation':True})
    if not batch(upgrades):return finish(output,state)
    state['completed_stages'].append('real_comparisons_and_prior_sensitivity')
    state['status']='complete';checkpoint()
    return finish(output,state)


def finish(output,state):
    from scripts.build_spatial_report import build
    build(output)
    save(Path(output)/'execution_state.json',state)
    return state


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=OUT);p.add_argument('--workers',type=int,default=4)
    p.add_argument('--timeout',type=int,default=300);p.add_argument('--wall-seconds',type=int,default=3600)
    a=p.parse_args()
    if not 1<=a.workers<=4:p.error('workers must be 1–4')
    print(json.dumps(run(a.output,a.workers,a.timeout,a.wall_seconds),indent=2))
