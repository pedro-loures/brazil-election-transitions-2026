"""Build the nationwide replacement, preserving the old explorer as an archive."""
import argparse,csv,gzip,hashlib,json,shutil,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from elections.national_combined import OUT,verify
from elections.spatial_runner import save


def compact_city(record):
    r=record
    fields=['municipality_code','municipality','uf','population_bin','population','sections','sections_union',
        'original_retained_sections','electorate','full_electorate','coverage','sites','groups','design_rank','design_condition',
        'status','level','baseline_allocation_distance','latitude','longitude']
    result={k:r.get(k) for k in fields}
    result['diagnostics']=r.get('diagnostics',{})
    result['matrix']=r.get('matrix');result['low']=r.get('low');result['high']=r.get('high')
    result['origins']=r.get('origins',r.get('observed_origins'))
    result['observed_destinations']=r.get('observed_destinations')
    result['baseline_matrix']=r.get('baseline_matrix')
    result['destination_residual_votes']=r.get('destination_residual_votes')
    result['attempts']=r.get('attempts',[])
    result['interval_type']='Pointwise conditional posterior credible interval' if r.get('status')=='ok' else 'Provisional interval: sampling diagnostics have not passed' if r.get('matrix') is not None else None
    result['independent_validation_complete']=False
    if result['matrix'] is not None:
        a=np.asarray(result['matrix']);lo=np.asarray(result['low']);hi=np.asarray(result['high']);n=np.asarray(result['origins'])
        if a.shape!=(5,4) or not np.isfinite(a).all() or (a<0).any() or not np.allclose(a.sum(1),n):raise ValueError('Invalid published flow matrix')
        if (lo<0).any() or (hi<lo).any() or (hi>n[:,None]+1e-6).any():raise ValueError('Invalid published interval')
    return result


def build(results=OUT,site=None,baseline=None,preview=False):
    results=Path(results);site=Path(site or ROOT/'results/2026/national_candidate');baseline=Path(baseline or ROOT/'docs')
    if site.resolve()==baseline.resolve():raise ValueError('Build into an isolated candidate directory')
    checks=verify(results,require_complete=not preview)
    m=json.loads((results/'manifest.json').read_text())
    if not preview and not checks['complete']:raise ValueError('National run incomplete')
    site.mkdir(parents=True,exist_ok=True)
    shutil.copytree(baseline,site,dirs_exist_ok=True)
    # Existing data/map modules remain addressable by the archived explorer.
    if not (site/'baseline.html').exists():
        old=(baseline/'index.html').read_text().replace('src="app.mjs"','src="baseline-app.mjs"')
        (site/'baseline.html').write_text(old)
        shutil.copyfile(baseline/'app.mjs',site/'baseline-app.mjs')
    for source in (ROOT/'web/national').iterdir():
        if source.is_file():shutil.copy2(source,site/source.name)
    data=site/'data/national';(data/'municipalities').mkdir(parents=True,exist_ok=True)
    index=[];rows=[];status_counts={};complete_records=0
    origin_names=['a','b','other','invalid','abstention'];destination_names=['a','b','invalid','abstention']
    for item in m['inventory']:
        path=results/'cities'/f"{item['municipality_code']}.json"
        if path.exists():r=json.loads(path.read_text());complete_records+=1
        elif preview:r={**item,'status':'pending','diagnostics':{'status':'pending'}}
        else:raise ValueError('Missing municipal terminal record')
        c=compact_city(r);code=c['municipality_code'];save(data/'municipalities'/f'{code}.json',c)
        n=np.asarray(c['origins'],float) if c['origins'] is not None else None
        a=np.asarray(c['matrix']) if c['matrix'] is not None else None
        widths=(np.asarray(c['high'])-np.asarray(c['low'])) if a is not None else None
        index.append({k:v for k,v in c.items() if k not in ['low','high','baseline_matrix','attempts','interval_type','destination_residual_votes']} |
            {'width_voters':None if widths is None else widths.tolist()})
        status_counts[c['status']]=status_counts.get(c['status'],0)+1
        for g in range(5):
            for k in range(4):rows.append({'municipality_code':code,'municipality':c['municipality'],'uf':c['uf'],
                'origin':origin_names[g],'destination':destination_names[k],'estimated_voters':None if a is None else float(a[g,k]),
                'low':None if a is None else c['low'][g][k],'high':None if a is None else c['high'][g][k],
                'origin_voters':None if n is None else float(n[g]),'electorate':c['electorate'],'status':c['status'],
                'electorate_coverage':c['coverage'],'independent_validation_complete':False})
    if not preview and not any(c['matrix'] is not None for c in index):raise ValueError('No new-model estimates to publish')
    save(data/'index.json',index)
    with gzip.open(site/'national-estimates.csv.gz','wt',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    digest=hashlib.sha256((results/'manifest.json').read_bytes()).hexdigest()
    release={'release_id':digest[:20],'model':'combined geographic–behavioural','version':m['version'],
        'municipalities':len(index),'terminal_records':complete_records,'status_counts':status_counts,
        'estimated_municipalities':sum(c['matrix'] is not None for c in index),'preview':preview,
        'independent_validation_complete':False,'source_manifest_sha256':digest,'sampling':m['sampling'],
        'published_intervals':'Pointwise and conditional; provisional for warning fits. No nationwide bootstrap or prior-variant sensitivity has been computed.',
        'original_baseline':'baseline.html','raw_archives_included':False}
    save(data/'release.json',release);save(data/'manifest.json',m)
    save(data/'verification.json',checks)
    # Publish a small, readable evidence record rather than the 29-MB offline report.
    evidence=ROOT/'results/2026/model_agreement'
    for name in ['decision.json','consensus_truth.json','execution_state.json','output_checks.json']:
        if (evidence/name).exists():shutil.copy2(evidence/name,data/('pilot-'+name))
    for name in ['NATIONAL_COMBINED_RELEASE_PLAN.md','MODEL_AGREEMENT_EXTENSION.md','MODEL_AGREEMENT_RESULTS.md']:
        shutil.copy2(ROOT/name,site/name)
    (site/'.nojekyll').touch()
    save(results/('preview_build.json' if preview else 'publication_build.json'),{'site':str(site),'release':release})
    return release


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,default=OUT);p.add_argument('--site',type=Path)
    p.add_argument('--baseline',type=Path);p.add_argument('--preview',action='store_true')
    a=p.parse_args();print(json.dumps(build(a.results,a.site,a.baseline,a.preview),indent=2))
