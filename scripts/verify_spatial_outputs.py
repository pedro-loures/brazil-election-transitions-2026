"""Verify original hashes, frozen splits, every grouping and persisted posterior."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from elections.spatial import OUT,KEY,diameter,partition
from elections.spatial_experiment import prepare,data_arrays
from elections.spatial_runner import save,config_parts
from elections.spatial_model import flow_draws


def verify(output=OUT):
    output=Path(output);manifest=prepare(output)
    sample=pd.read_csv(output/'sample.csv')
    assert len(sample)==48 and not sample.municipality_code.duplicated().any()
    geometry=json.loads((ROOT/'docs/data/maps/municipality.geojson').read_text())
    assert set(sample.municipality_code)<=set(int(f['properties']['key']) for f in geometry['features'])
    for b in range(1,6):
        block=sample[sample.population_bin==b]
        assert block.split.eq('development').sum()==(5 if b==5 else 6)
        assert block.split.eq('validation').sum()==(3 if b==5 else 4)
    sections=pd.read_csv(output/'sample_sections.csv.gz')
    assert not sections.duplicated(KEY).any()
    groupings=0
    for code,s in sections.groupby('municipality_code',sort=True):
        keys=s[KEY].astype(str).agg(':'.join,axis=1).to_numpy(str)
        with np.load(output/'groupings'/f'{code}.npz') as z:
            assert np.array_equal(z['section_keys'],keys)
            points=s[['latitude_1','longitude_1']].to_numpy()
            for target in manifest['targets']:
                for cap in manifest['diameters_km']:
                    labels=z[f'n{target}_d{cap}']
                    assert len(labels)==len(s)
                    for g in np.unique(labels):assert diameter(np.unique(points[labels==g],axis=0))<=cap+1e-8
                    # Co-located observations cannot be split by arbitrary order.
                    joined=pd.DataFrame({'latitude':points[:,0],'longitude':points[:,1],'group':labels})
                    assert joined.groupby(['latitude','longitude']).group.nunique().max()==1
                    groupings+=1
    audit=json.loads((output/'likelihood_audit.json').read_text())
    for row in audit['extension_exact_dm']:
        assert abs(row['probability_sum']-1)<1e-10
        assert row['mean_max_error']<1e-9 and row['covariance_max_error']<1e-9
    checked_posteriors=0;checked_intervals=0;confirmed_datasets=0
    for path in sorted((output/'fits').glob('*.npz')):
        result=json.loads((output/'jobs'/(path.stem+'.json')).read_text())
        job=result['job'];s=sections[sections.municipality_code.eq(job['municipality_code'])]
        x,y,points,admin=data_arrays(s)
        if job['scenario']!='observed':
            from elections.spatial_validation import generate
            x,y,truth,realized,points=generate(x,admin,points,job['scenario'],result['data_seed'])
        if job['phase']=='confirmation':
            source={**job,'phase':'development'}
            source_path=output/'jobs'/f"development-b{job['population_bin']}-{job['municipality_code']}-{job['scenario']}-r{job['replicate']:04d}-{job['method']}-{job['config']}-{job['variant']}.json"
            original=json.loads(source_path.read_text())
            assert result['data_seed']==original['data_seed']
            confirmed_datasets+=1
        target,cap=config_parts(job['config']);geographic=partition(points,target,cap)
        common=job['method']=='municipal_bayes';extended=job['method'].endswith('_extended')
        group=admin if job['method'].startswith('administrative') else geographic
        if common:group=np.zeros(len(x),int)
        with np.load(path) as saved:posterior={name:saved[name] for name in saved.files}
        grouped=flow_draws(posterior,x,group,{'municipality':np.zeros(len(x),int),'original_place':admin,'geographic_group':geographic},extended,common)
        municipal=grouped['municipality'][:,0]
        for name in ['original_place','geographic_group']:
            assert np.allclose(grouped[name].sum(1),municipal,atol=1e-7)
        assert np.allclose(municipal.sum(2),x.sum(0),atol=1e-7)
        for record in result.get('estimates',[]):
            d=grouped[record['support']][:,record['unit'],record['origin'],record['destination']]
            assert np.isclose(d.mean(),record['estimate'],atol=1e-7)
            assert np.allclose(np.quantile(d,[.025,.975]),[record['low'],record['high']],atol=1e-7)
            checked_intervals+=1
        checked_posteriors+=1
    gates=json.loads((output/'validation_gate.json').read_text())
    assert gates['baseline_hashes_unchanged']
    result={'passed':True,'sample_municipalities':len(sample),'grouping_configurations_checked':groupings,
        'baseline_and_frozen_input_hashes_unchanged':True,'exact_dm_moment_checks':True,
        'persisted_posteriors_checked':checked_posteriors,'exported_intervals_checked':checked_intervals,
        'confirmation_jobs_reuse_original_data':confirmed_datasets,
        'scope':'Software/data consistency, not hidden-flow reliability validation.'}
    save(output/'checks.json',result);print(json.dumps(result,indent=2));return result


if __name__=='__main__':verify()
