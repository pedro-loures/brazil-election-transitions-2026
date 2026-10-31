"""Offline spatial-experiment report, comparisons and fail-closed decisions."""
import argparse
import base64
import gzip
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from elections.spatial import OUT, KEY, neighbour_edges
from elections.spatial_runner import consolidate, clean, save
from elections.hierarchy_inventory import sha256


def comparisons(output,estimates,manifest):
    records=[];investigations=[]
    if estimates.empty:return records,investigations
    # Prefer real fits; use full-diagnostic profile fits only where a real fit
    # has not yet been attempted. All comparisons use the same verified core.
    e=estimates[estimates.support.eq('municipality')].copy()
    e['phase_priority']=e.phase.map({'real':0,'profile':1}).fillna(2)
    e=e.sort_values('phase_priority').drop_duplicates(['municipality_code','method','config','variant','origin','destination'])
    for (code,method,config),block in e[e.variant.eq('primary')].groupby(['municipality_code','method','config']):
        baseline=e[e.municipality_code.eq(code)&e.method.eq('municipal_wls')&e.variant.eq('primary')].drop_duplicates(['origin','destination'])
        if len(block)!=20 or len(baseline)!=20 or method=='municipal_wls':continue
        block=block.sort_values(['origin','destination']);baseline=baseline.sort_values(['origin','destination'])
        if not np.array_equal(block.origin_voters.to_numpy(),baseline.origin_voters.to_numpy()):
            raise ValueError('Different origin electorate in comparison')
        n=float(block.electorate.iloc[0]);delta=block.estimate.to_numpy()-baseline.estimate.to_numpy()
        origin=block.origin_voters.to_numpy();supported=origin>=100
        rate=np.divide(delta,origin,out=np.zeros(20),where=origin>0)*100
        tv=float(abs(delta).sum()/(2*n))
        key=block.origin.isin([3,4])&block.destination.isin([0,1])
        key_shift=float(abs(delta[key.to_numpy()]).max()/n*100)
        prior=[]
        for variant in ['tighter','wider']:
            v=e[e.municipality_code.eq(code)&e.method.eq(method)&e.config.eq(config)&e.variant.eq(variant)].sort_values(['origin','destination'])
            if len(v)==20:prior.append(float(abs(v.estimate.to_numpy()-block.estimate.to_numpy()).max()/n*100))
        flags=[]
        if tv>.05:flags.append('allocation_distance')
        if supported.any() and abs(rate[supported]).max()>10:flags.append('supported_origin_rate')
        if key_shift>2:flags.append('key_flow_shift')
        if len(prior)<2:flags.append('prior_sensitivity_not_complete')
        elif max(prior)>2:flags.append('prior_sensitivity')
        row={'municipality_code':int(code),'method':method,'config':config,'electorate':n,
            'matrix_distance':tv,'max_supported_rate_difference_pp':float(abs(rate[supported]).max()) if supported.any() else None,
            'key_flow_shift_electorate_pp':key_shift,'prior_sensitivity_electorate_pp':max(prior) if len(prior)==2 else None,
            'flags':flags,'investigation_status':'unresolved' if flags else 'no_material_warning',
            'explanation':'Common verified electorate; WLS hard-calibrates expected municipal margins; Bayesian expected margins are stochastic. Aggregate data cannot determine which hidden flows are true.'}
        records.append(row)
        investigations.append({**row,'origin_inputs_match':True,'truth_observed':False,
            'prior_variants_available':len(prior),'computational_statuses':block.status.unique().tolist(),
            'largest_cell_differences':[{'origin':int(block.iloc[i].origin),'destination':int(block.iloc[i].destination),
                'difference_voters':float(delta[i]),'difference_origin_pp':float(rate[i])} for i in np.argsort(abs(delta))[-5:][::-1]]})
    return records,investigations


def local_prior_sensitivity(estimates):
    columns=['municipality_code','method','config','group','electorate','available_variants','complete',
             'sensitivity_electorate_pp','supported_origin_sensitivity_pp','investigation_status']
    if estimates.empty:return pd.DataFrame(columns=columns)
    data=estimates[estimates.phase.eq('real')&estimates.support.eq('geographic_group')&estimates.method.ne('municipal_wls')]
    rows=[]
    for (code,method,config,unit),block in data.groupby(['municipality_code','method','config','unit']):
        if block.electorate.nunique()!=1:raise ValueError('Prior variants use different local electorates')
        matrix=block.pivot(index=['origin','destination'],columns='variant',values='estimate')
        variants=['primary','tighter','wider']
        complete=(len(matrix)==20 and set(variants)<=set(matrix.columns) and
                  matrix[variants].notna().all().all() and block.status.eq('ok').all())
        n=float(block.electorate.iloc[0]);shift=None;origin_shift=None
        if complete:
            differences=np.maximum(abs(matrix.tighter-matrix.primary),abs(matrix.wider-matrix.primary))
            shift=float(differences.max()/n*100)
            origins=block[block.variant.eq('primary')].set_index(['origin','destination']).origin_voters.reindex(matrix.index)
            supported=origins.ge(100)
            if supported.any():origin_shift=float((differences[supported]/origins[supported]*100).max())
        rows.append({'municipality_code':int(code),'method':method,'config':config,'group':int(unit),
            'electorate':n,'available_variants':int(block.variant.nunique()),'complete':bool(complete),
            'sensitivity_electorate_pp':shift,'supported_origin_sensitivity_pp':origin_shift,
            'investigation_status':'insufficient_prior_evidence' if not complete else
                ('unresolved_prior_sensitivity' if shift>2 else 'no_material_warning')})
    return pd.DataFrame(rows,columns=columns)


def compact_estimates(frame):
    """One 5×4 matrix per reporting unit instead of repeated row metadata."""
    if frame.empty:return []
    keys=['municipality_code','phase','method','config','support','unit']
    output=[]
    for _,block in frame.groupby(keys,sort=True):
        block=block.sort_values(['origin','destination'])
        if len(block)!=20 or list(zip(block.origin,block.destination))!=[(g,k) for g in range(5) for k in range(4)]:
            raise ValueError('Display matrix is incomplete or duplicated')
        first=block.iloc[0]
        row={key:first[key] for key in keys}
        row.update(variant='primary',status=first.status,interval_type=first.interval_type,
            electorate=int(first.electorate),origin_counts=block.groupby('origin').origin_voters.first().astype(int).tolist(),
            point=block.estimate.round(8).tolist(),low=block.low.round(8).tolist(),high=block.high.round(8).tolist())
        output.append(row)
    return clean(output)


def build(output=OUT):
    output=Path(output)
    jobs,scores,estimates,summary,decisions=consolidate(output)
    from elections.spatial_information import analyze
    analyze(output)
    manifest=json.loads((output/'manifest.json').read_text())
    comp,investigations=comparisons(output,estimates,manifest)
    pd.DataFrame(comp).to_csv(output/'municipal_comparison.csv',index=False)
    save(output/'municipal_investigations.json',investigations)
    local_sensitivity=local_prior_sensitivity(estimates)
    local_sensitivity.to_csv(output/'local_prior_sensitivity.csv',index=False)
    groups=pd.read_csv(output/'group_inventory.csv.gz')
    real_gate={}
    for b in range(1,6):
        real_gate[str(b)]={}
        expected={c['municipality_code'] for c in manifest['sample'] if c['population_bin']==b}
        for method,config in sorted({(r['method'],r['config']) for r in decisions if r['population_bin']==b}):
            rows=[r for r in comp if r['municipality_code'] in expected and r['method']==method and r['config']==config]
            covered={r['municipality_code'] for r in rows}
            reasons=[]
            if covered!=expected:reasons.append('real_common_electorate_comparisons_incomplete')
            if any(r['flags'] for r in rows):reasons.append('material_disagreement_or_prior_investigation_unresolved')
            fit=jobs[(jobs.phase=='real')&jobs.municipality_code.isin(expected)&jobs.method.eq(method)&jobs.config.eq(config)] if len(jobs) else pd.DataFrame()
            if len(fit)!=len(expected)*3 or (len(fit) and fit.status.ne('ok').any()):
                reasons.append('real_prior_variant_computation_incomplete_or_failed')
            local=local_sensitivity[local_sensitivity.municipality_code.isin(expected)&local_sensitivity.method.eq(method)&local_sensitivity.config.eq(config)]
            expected_groups=groups[groups.municipality_code.isin(expected)&groups.config.eq(config)]
            if len(local)!=len(expected_groups) or (len(local) and not local.complete.all()):
                reasons.append('local_prior_sensitivity_incomplete')
            if len(local) and local.sensitivity_electorate_pp.gt(2).any():
                reasons.append('local_prior_sensitivity_unresolved')
            real_gate[str(b)][f'{method}:{config}']={'passed':not reasons,'reasons':reasons,'municipalities_compared':len(covered),'expected':len(expected)}
    save(output/'real_comparison_gate.json',real_gate)
    # Re-evaluate after writing the actual comparison evidence; missing evidence
    # cannot be bypassed by a simulation-only pass.
    if len(jobs) and jobs.phase.eq('validation').any():
        _,_,_,summary,decisions=consolidate(output)
    source_ok=all(sha256(ROOT/path)==digest for path,digest in manifest['sources'].items())
    geo=json.loads((output/'geography_audit.json').read_text())
    coordinates=pd.read_csv(output/'sample_sections.csv.gz')
    sites=[];networks=[]
    for (code,config),block in groups.groupby(['municipality_code','config']):
        point=block[['latitude','longitude']].to_numpy()
        sites.extend(block[['municipality_code','config','group','latitude','longitude','sections','electorate','diameter_km','undersized',
                            'target_sections','design_rank','design_condition','composition_sd',
                            'origin_a','origin_b','origin_other','origin_invalid','origin_abstention']].to_dict('records'))
        # These are analysis-group centroid links, never catchment boundaries.
        for distance,i,j in neighbour_edges(point,1):
            networks.append({'municipality_code':int(code),'config':config,'from':int(block.iloc[i].group),'to':int(block.iloc[j].group)})
    def records(frame):return json.loads(frame.to_json(orient='records'))
    geometry=json.loads((ROOT/'docs/data/maps/municipality.geojson').read_text())
    shortlist=json.loads((output/'candidate_configurations.json').read_text())['candidates']
    full=pd.read_csv(ROOT/'results/2026/municipalities.csv').set_index('municipality_code')
    view_cities=[]
    for city in manifest['sample']:
        total=float(full.loc[city['municipality_code'],'eligible_1'])
        coverage=city['electorate']/total
        if not 0<=coverage<=1+1e-8:raise ValueError('Included electorate exceeds full first-round reference')
        view_cities.append({**city,'full_electorate_1':total,'overall_electorate_coverage':coverage,
            'excluded_sections_union':int(full.loc[city['municipality_code'],'sections_union'])-city['sections']})
    pd.DataFrame(view_cities).to_csv(output/'sample_electorate_coverage.csv',index=False)
    shown_estimates=estimates[estimates.variant.eq('primary')&estimates.phase.isin(['real','profile'])] if len(estimates) else estimates
    shown_fits=jobs[jobs.scenario.eq('observed')] if len(jobs) else jobs
    payload={'cities':view_cities,'candidates':shortlist,'estimates':compact_estimates(shown_estimates),'fits':records(shown_fits),
             'local_sensitivity':records(local_sensitivity),
             'thresholds':decisions,'simulations':[r for r in summary if r['calibration_scope']=='bin'],'comparisons':comp,'geography_audit':geo,
             'groups':clean(sites),'networks':networks,'geo':geometry,'baseline_unchanged':source_ok}
    config={'default_origin':4,'default_destination':0,'default_method':'geographic_extended',
            'intervals':'Pointwise 95% conditional credible intervals; WLS bootstrap sensitivity ranges separately labelled.',
            'group_geometry':'Analysis-group points and proximity networks, not electoral catchment polygons.',
            'calibration_scope':'Simulation scenario/population/support evidence, not measured accuracy of a real location.',
            'estimate_layout':'One matrix per unit; point/low/high arrays use index=4*origin+destination. Display rounds to 8 decimals; estimates.csv.gz retains full precision.',
            'default_metric':'estimate','missing':'Not available; never numerical zero'}
    save(output/'visualization_config.json',config)
    save(output/'visualization_data.json',{k:v for k,v in payload.items() if k!='geo'})
    html=(ROOT/'web/spatial/template.html').read_text()
    script=(ROOT/'web/spatial/app.js').read_text()
    encoded=json.dumps(clean(payload),ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
    packed=base64.b64encode(gzip.compress(encoded,mtime=0)).decode('ascii')
    boot=('async function boot(){const bytes=Uint8Array.from(atob('+json.dumps(packed)+'),c=>c.charCodeAt(0));'
          "const DATA=await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).json();")
    finish="}\nboot().catch(error=>{document.getElementById('banner').textContent='Cannot load interactive data in this browser: '+error.message;});"
    (output/'report.html').write_text(html.replace('/*__DATA__*/',boot).replace('/*__APP__*/',script+finish))
    bybin=[]
    for b in range(1,6):
        rows=[r for r in decisions if r['population_bin']==b]
        status='scale' if any(r['decision']=='scale' for r in rows) else ('do_not_scale' if rows and all(r['decision']=='do_not_scale' for r in rows) else 'insufficient_evidence')
        bybin.append({'population_bin':b,'decision':status,'configurations':rows})
    save(output/'validation_gate.json',{'baseline_hashes_unchanged':source_ok,'bins':bybin,
        'national_expansion_performed':False,'note':'Software success is not validated hidden-flow recovery. Missing scenarios, priors, held-out validation or computations prevent scale.'})
    raw_jobs=pd.read_csv(output/'raw_fit_status.csv') if len(jobs) else jobs
    statuscounts=raw_jobs.status.value_counts().to_dict() if len(raw_jobs) else {}
    phase_counts=[]
    if len(jobs):
        for (phase,b,scenario),block in raw_jobs.groupby(['phase','population_bin','scenario']):
            phase_counts.append({'phase':phase,'population_bin':int(b),'scenario':scenario,
                'method_fits_attempted':len(block),'datasets':int(block.replicate.nunique()) if scenario!='observed' else None,
                'municipalities':int(block.municipality_code.nunique()),
                'diagnostic_statuses':block.status.value_counts().to_dict(),
                'independent_validation':phase=='validation',
                'confirmation_reuses_development_data':phase=='confirmation'})
    save(output/'execution_summary.json',{'study_status':'independent_validation_incomplete' if not len(jobs) or not jobs.phase.eq('validation').any() else 'see_validation_gate',
        'sample_municipalities':48,'phase_counts':phase_counts,'baseline_hashes_unchanged':source_ok,
        'note':'Method/configuration fits on the same generated data are not independent datasets. Confirmations reuse development datasets.',
        'full_calibration_complete':all(r['decision']=='scale' for r in bybin)})
    lines=['# Spatial pooling: execution results','','## Current decision','',
        'The spatial experiment is isolated from the original national results. Statistical validation and computation are reported separately.','',
        '| Population bin | Decision |','|---|---|']
    lines += [f"| {r['population_bin']} | {r['decision'].replace('_',' ')} |" for r in bybin]
    lines += ['', '## Completed data and software work','',
        f"- Frozen outcome-blind sample: {len(manifest['sample'])} municipalities; independent development/validation splits.",
        f"- Detailed IBGE boundary/register consistency: {geo['statuses']}; {geo['exceptions_resolved_by_detailed_mesh']} simplified-map exceptions resolved.",
        '- All 24 target/diameter combinations inventoried per sample municipality, including infeasible/undersized groups.',
        '- Matched municipal, administrative, geographic, contextual/overdispersion and literal-aggregation model arms implemented.',
        '- Section-level known-flow generators, fixed-support scoring, independent-stream validation, MC precision and fail-closed gates implemented.',
        '- Offline interactive map/report includes estimates, widths, coordinate coverage, sensitivity, computation and municipal disagreement.',
        f'- Frozen original source hashes unchanged: **{source_ok}**.',
        '', '## Executed fits and remaining evidence','',f'Raw fit-attempt statuses: `{statuscounts}`. See `raw_fit_status.csv` for original attempts and `fit_status.csv` for effective computation after same-data upgrades.',
        '', '| Phase | Bin | Scenario | Method fits | Generated datasets | Municipal designs |',
        '|---|---:|---|---:|---:|---:|']
    lines += [f"| {r['phase']} | {r['population_bin']} | {r['scenario']} | {r['method_fits_attempted']} | {r['datasets'] if r['datasets'] is not None else 'observed'} | {r['municipalities']} |" for r in phase_counts]
    lines += ['', 'Confirmation datasets repeat the corresponding development data and are not extra independent validation replications.',
        'See `simulation_metrics.csv.gz` and `simulation_summary.json` for actual executed datasets. Missing jobs/scenarios are not treated as successful replications. A geographic shortlist is not a validated reliability threshold.',
        'Development outcomes do not certify interval coverage. Held-out validation requires a frozen selection lock; no supported selection means expansion is withheld.',
        ('Independent calibration and real-comparison gates pass for every reported bin.' if all(r['decision']=='scale' for r in bybin) else
         'Full certification remains incomplete. Inspect phase counts and gates for missing development scenarios, selection, held-out validation, prior variants or unresolved failures; implemented stages are not automatically completed evidence.'),
        '', '## Interpretation and reproducibility','',
        'Coordinates identify polling sites, not voters’ residences. Verified means source and detailed-boundary consistency, not field confirmation. Equal electorate sizes do not establish identical voters.',
        'The extension uses composition covariates and Dirichlet-multinomial origin-row overdispersion with an approximate normal margin likelihood; these are additional assumptions, not a cure for ecological nonidentification.',
        'Overdispersion changes margin uncertainty; it does not reconstruct distinct latent section matrices. Reported flows use fitted mean probabilities. Section-level hidden-rate recovery remains an explicit robustness test.',
        'Local and municipal expected flows are summed draw by draw before intervals. A municipal pass cannot certify local flows. Exact zero flows receive separate boundary summaries.',
        'Run `.venv-hierarchy/bin/python -m elections.spatial_runner --help` for resumable stages and `python scripts/build_spatial_report.py` to rebuild this report.',
        'The accepted specification is `SPATIAL_POOLING_PLAN.md`; the feasibility/literature qualifications remain in `SPATIAL_POOLING_FEASIBILITY.md`.','']
    (ROOT/'SPATIAL_POOLING_RESULTS.md').write_text('\n'.join(lines))
    return payload


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT)
    build(parser.parse_args().output)
