"""Rebuild actual cross-model evidence; missing fits never become agreement."""
from itertools import combinations
from pathlib import Path
import json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from elections.agreement import flow_agreement,matrix_comparisons,cluster_stability
from elections.agreement_model import FAMILIES
from elections.agreement_runner import OUT
from elections.spatial_runner import save,clean
from elections.spatial_validation import gate_cell,mc_summary
from elections.hierarchy_inventory import sha256


def build(output=OUT):
    output=Path(output);m=json.loads((output/'manifest.json').read_text())
    records=[json.loads(p.read_text()) for p in sorted((output/'jobs').glob('*.json')) if not p.name.endswith('.job.json')]
    jobs=[];municipal=[];score_rows=[];frames=[]
    for r in records:
        job=r['job'];jobs.append({**job,**r['diagnostics'],'elapsed_seconds':r['elapsed_seconds']})
        for row in r.get('municipal_flows',[]):municipal.append({**row,**job})
        for row in r.get('scores',[]):score_rows.append({**row,**job,'status':r['diagnostics']['status']})
        if r.get('flow_file') and job['scenario']=='observed' and job['phase']!='profile':
            frame=pd.read_csv(output/r['flow_file']);frames.append(frame[frame.support.ne('geographic_group')])
    job_frame=pd.DataFrame(jobs);job_frame.to_csv(output/'fit_status.csv',index=False)
    scores=pd.DataFrame(score_rows);scores.to_csv(output/'simulation_metrics.csv.gz',index=False)
    all_real=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    muni=pd.DataFrame(municipal)
    # Simulations retain municipal flow records in JSON; observed local rows
    # come from immutable per-fit exports. No estimated individual ballots.
    inputs=[]
    if len(muni):inputs.append(muni[muni.scenario.ne('observed') | muni.phase.eq('profile')])
    if len(all_real):inputs.append(all_real)
    comparisons=pd.concat(inputs,ignore_index=True) if inputs else pd.DataFrame()
    agreement=[];matrices=[]
    keys=['phase','municipality_code','population_bin','scenario','replicate','support','unit']
    if len(comparisons):
        primary=comparisons[comparisons.variant.eq('primary')]
        for key,block in primary.groupby(keys,sort=False):
            tags=dict(zip(keys,key));electorate=float(block.electorate.iloc[0])
            matrix={}
            for family,rows in block[block.family.isin(FAMILIES)].groupby('family'):
                if len(rows)==20:matrix[family]=rows.sort_values(['origin','destination']).estimate.to_numpy().reshape(5,4)
            if tags['support']=='municipality':
                for pair in matrix_comparisons(matrix,electorate):matrices.append({**tags,**pair})
            for (g,k),cell in block.groupby(['origin','destination']):
                expected=cell[cell.family.isin(FAMILIES)]
                origin=float(cell.origin_voters.iloc[0])
                if not np.allclose(cell.electorate,electorate) or not np.allclose(cell.origin_voters,origin):raise ValueError('Mismatched electorates')
                if expected.family.duplicated().any():raise ValueError('Duplicate model result')
                result=flow_agreement(dict(zip(expected.family,expected.estimate)),origin,electorate,int(g),int(k))
                good=expected[expected.status.eq('ok')].family.tolist()
                validated=[] # Assigned only by independent full validation, never point agreement.
                row={**tags,'origin':int(g),'destination':int(k),'origin_voters':origin,'electorate':electorate,
                     **result,'diagnostic_ok_families':good,'independently_validated_families':validated}
                if 'truth' in expected and expected.truth.notna().any():
                    truth=float(expected.truth.dropna().iloc[0])
                    if not np.allclose(expected.truth.dropna(),truth):raise ValueError('Mismatched simulated truth')
                    errors={r.family:abs(r.estimate-truth) for r in expected.itertuples()}
                    wrong={f:(e/electorate>.02 or (origin>=100 and e/origin>.1)) for f,e in errors.items()}
                    # Separate raw agreement from agreement among numerically valid fits.
                    lookup={tuple(sorted([p['first'],p['second']])):p['agrees'] for p in result['pairwise']}
                    triples=[list(c) for size in [3,4] for c in combinations(result['available_models'],size)
                             if all(lookup[tuple(sorted(pair))] for pair in combinations(c,2))]
                    eligible=[c for c in triples if all(f in good for f in c)]
                    row.update(truth=truth,agreeing_subset_count=len(triples),
                        all_agreeing_models_wrong=bool(eligible and any(all(wrong[f] for f in c) for c in eligible)),
                        eligible_consensus=bool(eligible),
                        consensus_subsets=[{'families':c,'diagnostic_ok':c in eligible,'all_materially_wrong':all(wrong[f] for f in c)} for c in triples])
                agreement.append(row)
    save(output/'flow_agreement.json',agreement)
    pd.DataFrame(matrices).to_csv(output/'matrix_comparisons.csv',index=False)
    resampling=[];prior=[];influence=[];stability=[]
    if len(all_real):
        unitkeys=['municipality_code','family','support','unit','origin','destination']
        for key,selected in all_real.groupby(unitkeys,sort=False):
            b=selected[selected.phase.eq('observed') & selected.variant.eq('primary')]
            if b.empty:continue
            ref=b.iloc[0];tags=dict(zip(unitkeys,key))
            boot=selected[selected.phase.eq('bootstrap')]
            origin=ref.origin_voters
            vals=boot.estimate.to_numpy(float)/origin*100 if origin else np.array([])
            resampling.append({**tags,'completed_with_estimates':len(boot),'diagnostic_ok':int(boot.status.eq('ok').sum()),
                'planned_pilot_replicates':m['resampling']['pilot_replicates'],
                'rate_sd_pp':float(np.std(vals,ddof=1)) if len(vals)>1 else None,
                'rate_p025_pp':float(np.quantile(vals,.025)) if len(vals) else None,
                'rate_p975_pp':float(np.quantile(vals,.975)) if len(vals) else None,
                'interval_type':'empirical perturbation range, not a calibrated confidence interval'})
            variants=selected[selected.phase.eq('observed')]
            complete=set(variants.variant)=={'primary','tighter','wider'}
            shift=float(variants.estimate.max()-variants.estimate.min()) if complete else None
            prior.append({**tags,'complete':complete,'all_diagnostic_ok':bool(complete and variants.status.eq('ok').all()),
                'shift_electorate_pp':100*shift/ref.electorate if shift is not None else None})
            deletion=selected[selected.phase.eq('deletion')]
            if len(deletion):influence.append({**tags,'buildings_removed':len(deletion),
                'maximum_shift_rate_pp':float(abs(deletion.estimate-ref.estimate).max()/origin*100) if origin else None,
                'scope':'two largest buildings, not all-building influence'})
    pd.DataFrame(resampling).to_csv(output/'resampling_stability.csv.gz',index=False)
    pd.DataFrame(prior).to_csv(output/'prior_sensitivity.csv.gz',index=False)
    pd.DataFrame(influence).to_csv(output/'deletion_influence.csv.gz',index=False)
    for original in records:
        j=original['job']
        if j['phase']!='observed' or j['variant']!='primary' or 'membership_mode' not in original:continue
        for other in records:
            o=other['job']
            if o['phase']!='bootstrap' or o['family']!=j['family'] or o['municipality_code']!=j['municipality_code'] or 'membership_mode' not in other:continue
            matches=cluster_stability(original['membership_mode'],other['membership_mode'],np.asarray(other['weights'])>0)
            old={(r['first'],r['second']):r['probability'] for r in original['coassignment']}
            delta=[abs(r['probability']-old[(r['first'],r['second'])]) for r in other['coassignment'] if r['both_in_sample']]
            stability.append({**o,'jaccard_by_reference_cluster':matches,'mean_coassignment_shift':float(np.mean(delta)) if delta else None,
                'scope':'in-bag sections; mode Jaccard and posterior co-assignment reported separately'})
    save(output/'cluster_stability.json',stability)
    # Pairwise/three-family stability uses identical bootstrap cases. Failed
    # models stay in attempted-case denominators; pending cases are not failures.
    boot_frequency=[]
    if len(job_frame):
        base_agreement=[a for a in agreement if a['phase']=='observed']
        boot_lookup={}
        for b in agreement:
            if b['phase']=='bootstrap':boot_lookup.setdefault(tuple(b[k] for k in ['municipality_code','support','unit','origin','destination']),[]).append(b)
        complete_by_city={}
        for code,case in job_frame[job_frame.phase.eq('bootstrap') & job_frame.family.isin(FAMILIES)].groupby('municipality_code'):
            complete_by_city[code]={r for r,b in case.groupby('replicate') if set(b.family)==set(FAMILIES)}
        for a in base_agreement:
            complete=complete_by_city.get(a['municipality_code'],set())
            matches=[b for b in boot_lookup.get(tuple(a[k] for k in ['municipality_code','support','unit','origin','destination']),[]) if b['replicate'] in complete]
            subsets=list(combinations(FAMILIES,3))+[FAMILIES]
            for subset in subsets:
                hits=sum(any(set(subset)<=set(c) for c in b['maximum_subsets']) for b in matches)
                valid_hits=sum(any(set(subset)<=set(c) for c in b['maximum_subsets']) and set(subset)<=set(b['diagnostic_ok_families']) for b in matches)
                boot_frequency.append({k:a[k] for k in ['municipality_code','support','unit','origin','destination']} |
                    {'families':list(subset),'completed_paired_cases':len(complete),'cases_with_flow_estimates':len(matches),
                     'agreement_fraction':hits/len(complete) if complete else None,'diagnostic_ok_agreement_fraction':valid_hits/len(complete) if complete else None})
    save(output/'resampling_agreement.json',boot_frequency)
    validation=[]
    if len(scores):
        valid=scores[scores.status.eq('ok')]
        for key,block in scores.groupby(['phase','population_bin','scenario','family','support','origin','destination']):
            phase,b,scenario,family,support,g,k=key
            good=block[block.status.eq('ok')]
            baseline=valid[(valid.phase==phase)&(valid.population_bin==b)&(valid.scenario==scenario)&(valid.family=='municipal_wls')&
                (valid.support==support)&(valid.origin==g)&(valid.destination==k)]
            evidence=gate_cell(good,baseline,m['acceptance'],phase,len(block)) if len(good) else {'reasons':['no_diagnostically_valid_fits']}
            validation.append({'phase':phase,'population_bin':int(b),'scenario':scenario,'family':family,'support':support,'origin':int(g),'destination':int(k),
                'datasets_with_scores':len(block),'valid_datasets':len(good),**evidence,'qualified':False})
    save(output/'validation_metrics.json',validation)
    consensus_truth=[]
    cases={}
    for a in agreement:
        if 'truth' not in a or a['support']!='municipality':continue
        key=(a['phase'],a['population_bin'],a['scenario'],a['municipality_code'],a['replicate'])
        cases.setdefault(key,[]).append(a)
    by_scenario={}
    for key,rows in cases.items():
        selected=[r for r in rows if r.get('eligible_consensus')]
        by_scenario.setdefault(key[:3],[]).append({'selected_cells':len(selected),
            'fraction_wrong':sum(r['all_agreeing_models_wrong'] for r in selected)/len(selected) if selected else None})
    for key,rows in by_scenario.items():
        observed=[r['fraction_wrong'] for r in rows if r['fraction_wrong'] is not None]
        consensus_truth.append({'phase':key[0],'population_bin':key[1],'scenario':key[2],'independent_datasets':len(rows),
            'datasets_with_eligible_consensus':len(observed),'conditional_wrong_fraction':mc_summary(observed),
            'scope':'mean per-dataset fraction of selected municipal cells with a mutually agreeing subset all materially wrong; not a probability for an observed city'})
    save(output/'consensus_truth.json',consensus_truth)
    source_ok=all(sha256(ROOT/p)==h for p,h in m['sources'].items())
    decision={'decision':'insufficient_evidence','independent_validation_complete':False,'sources_unchanged':source_ok,
        'completed_fit_attempts':len(jobs),'status_counts':job_frame.status.value_counts().to_dict() if len(job_frame) else {},
        'known_flow_datasets':len(cases),'note':'No consensus or bootstrap-stability result certifies individual-flow accuracy. Full acceptance remains uncompleted.'}
    save(output/'decision.json',decision)
    cities=[c for c in m['sample'] if any(j['municipality_code']==c['municipality_code'] and j['scenario']=='observed' for j in jobs)]
    codes={c['municipality_code'] for c in cities}
    geometry=json.loads((ROOT/'docs/data/maps/municipality.geojson').read_text())
    geometry['features']=[f for f in geometry['features'] if int(f['properties']['key']) in codes]
    local=all_real[all_real.phase.eq('observed') & all_real.variant.eq('primary')] if len(all_real) else pd.DataFrame()
    from elections.spatial_experiment import data_arrays
    sections=pd.read_csv(ROOT/'results/2026/spatial_pooling/sample_sections.csv.gz')
    locations=[]
    for code,s in sections[sections.municipality_code.isin(codes)].groupby('municipality_code'):
        s=s.reset_index(drop=True);_,_,points,admin=data_arrays(s)
        for support,labels in [('section',np.arange(len(s))),('original_place',admin),('municipality',np.zeros(len(s),int))]:
            for unit in np.unique(labels):
                locations.append({'municipality_code':int(code),'support':support,'unit':int(unit),
                    'latitude':float(points[labels==unit,0].mean()),'longitude':float(points[labels==unit,1].mean())})
    payload={'cities':cities,'families':list(FAMILIES),'jobs':jobs,'flows':local.to_dict('records'),
        'agreement':[a for a in agreement if a['phase']=='observed'],'bootstrap':boot_frequency,'resampling':resampling,
        'prior':prior,'influence':influence,'geometry':geometry,'locations':locations,'decision':decision,'simulation':consensus_truth}
    # CSV/JSON data retain full precision. HTML is an offline view of actual runs.
    save(output/'visualization_data.json',payload)
    template=(ROOT/'web/agreement/template.html').read_text();script=(ROOT/'web/agreement/app.js').read_text()
    encoded=json.dumps(clean(payload),ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('</','<\\/')
    (output/'report.html').write_text(template.replace('/*__DATA__*/','const DATA='+encoded+';').replace('/*__APP__*/',script))
    (ROOT/'MODEL_AGREEMENT_RESULTS.md').write_text('\n'.join([
        '# Model-agreement extension: current execution','',
        '**Decision: insufficient evidence.** Independent calibration is not complete.','',
        f"Completed fit attempts: {len(jobs)}. Statuses: {decision['status_counts']}.",
        f"Completed known-flow municipal datasets with exported flows: {len(cases)}. Repeated models and resamples are not independent datasets.",
        f"Frozen source hashes unchanged: {source_ok}.",'',
        'The four families share composition effects and DM moment overdispersion. Behavioural and combined models jointly infer two section regimes. The original WLS estimator is an additional, unmatched benchmark.',
        'Whole-building resamples are paired across models. Groups are rebuilt; original fixed reporting supports and denominators are preserved. Sections omitted from mixture fitting use prior component membership, without reading their second-round outcomes for assignment.',
        'Posterior intervals, empirical resampling ranges, model agreement and known-flow accuracy are distinct evidence. Mode-cluster Jaccard and posterior co-assignment stability are reported separately.',
        'Inspect `results/2026/model_agreement/execution_state.json` for current progress and a measured runtime ETA. A completed pilot is not full five-bin validation.','',
        'Report: `results/2026/model_agreement/report.html`. Raw fit attempts, flows, calibration metrics, consensus failures, priors, cluster stability and resampling diagnostics are exported alongside it.','']))
    return decision


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=OUT)
    print(json.dumps(build(p.parse_args().output),indent=2))
