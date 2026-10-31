"""Frozen, resumable experiment preparation. Inputs and earlier results are immutable."""
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .spatial import (ROOT, OUT, AUDIT, KEY, TARGETS, DIAMETERS, REGIONS, distances,
                      neighbour_edges, partition, group_inventory, information, select_sample, seed_for)
from .hierarchy_inventory import sha256, write_json
from .model import ORIGINS, DESTINATIONS

SCENARIOS = ['homogeneous','smooth','strong_spatial','sharp_boundary','nonspatial','within_building',
             'contextual','sparse_origins','switching','zero_flows','coordinate_error']
METHODS = ['municipal_wls','municipal_bayes','administrative','administrative_extended',
           'geographic','geographic_extended','literal_aggregation']


def load_sections(output=OUT):
    s = pd.read_csv(ROOT/'results/2026/sections.csv.gz')
    s = s[s.analysis_eligible].copy()
    geo = pd.read_csv(Path(output)/'section_coordinates.csv.gz',low_memory=False)
    cols = KEY+['coordinate_status','coordinate_reason','latitude_1','longitude_1','population_bin','site_key']
    s = s.merge(geo[cols],on=KEY,validate='one_to_one')
    return s.sort_values(KEY).reset_index(drop=True)


def data_arrays(s):
    return (s[[g+'_1' for g in ORIGINS]].to_numpy(float),
            s[[g+'_2' for g in DESTINATIONS]].to_numpy(float),
            s[['latitude_1','longitude_1']].to_numpy(float),
            pd.factorize(s[['zone','polling_place_1']].astype(str).agg(':'.join,axis=1),sort=True)[0])


def prepare(output=OUT, seed=20261030):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output/'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for path, digest in manifest['sources'].items():
            if sha256(ROOT/path) != digest:
                raise ValueError('Frozen source changed: '+path)
        for filename, digest in manifest['frozen_artifacts'].items():
            if sha256(output/filename) != digest:
                raise ValueError('Frozen experimental design changed: '+filename)
        return manifest
    all_sections = load_sections(output)
    cities = pd.read_csv(AUDIT/'municipality_population_bins.csv')
    city_meta = cities.set_index('municipality_code')
    inventory = []
    for code, original in all_sections.groupby('municipality_code',sort=True):
        s = original[original.coordinate_status.eq('verified_register_boundary')]
        if s.empty:
            continue
        x,_,points,_ = data_arrays(s)
        site_coords = np.unique(points,axis=0)
        edges = neighbour_edges(site_coords,1)
        site_distance = float(np.median([e[0] for e in edges])) if edges else 0.
        info = information(x)
        meta = city_meta.loc[code]
        inventory.append({'uf':meta.uf, 'municipality_code':int(code),'municipality':meta.municipality,
            'population':int(meta.population),'population_bin':int(meta.population_bin),'region':REGIONS[meta.uf],
            **info, 'sites':len(site_coords),'median_neighbour_km':site_distance,
            'coordinate_coverage':float(x.sum()/original.eligible_1.sum()),
            'original_retained_sections':len(original),'original_retained_electorate':int(original.eligible_1.sum()),
            **{f'origin_share_{g}':float(x[:,i].sum()/x.sum()) for i,g in enumerate(ORIGINS)}})
    inventory = pd.DataFrame(inventory)
    inventory.to_csv(output/'municipality_inventory.csv',index=False)
    sample = select_sample(inventory,seed)
    if len(sample) != 48 or sample.municipality_code.duplicated().any():
        raise ValueError('Expected 48 unique sampled municipalities')
    sample.to_csv(output/'sample.csv',index=False)
    selected = sample.municipality_code.tolist()
    history = [] if 81914 in selected else [81914]
    subset = all_sections[all_sections.municipality_code.isin(selected+history)].copy()
    subset['split'] = subset.municipality_code.map(sample.set_index('municipality_code').split).fillna('historical')
    subset.to_csv(output/'sample_sections_all_coordinates.csv.gz',index=False)
    subset[subset.coordinate_status.eq('verified_register_boundary')].to_csv(output/'sample_sections.csv.gz',index=False)
    sources = ['results/2026/sections.csv.gz','results/2026/municipalities.csv','results/2026/estimated_flows.csv.gz',
               'results/2026/run.json','data/processed/2026/metadata.json','data/raw/2026/manifest.json',
               'data/raw/spatial_feasibility/manifest.json','results/2026/spatial_feasibility/audit.json',
               'data/raw/spatial_pooling/BR_Municipios_2025.zip','results/2026/hierarchy_pilot/manifest.json',
               'results/2026/hierarchy_pilot/validation_gate.json']
    manifest = {'created_utc':datetime.now(timezone.utc).isoformat(),'seed':seed,
        'sources':{path:sha256(ROOT/path) for path in sources},
        'frozen_artifacts':{name:sha256(output/name) for name in ['sample.csv','sample_sections.csv.gz','section_coordinates.csv.gz']},
        'sample':sample.replace({np.nan:None}).to_dict('records'),'historical_check':history,
        'selection':'Region-balanced farthest-first, first-round information and geographic availability only. Not a probability national sample.',
        'sample_splits':sample.groupby(['population_bin','split']).size().reset_index(name='municipalities').to_dict('records'),
        'bin_edges':json.loads((AUDIT/'audit.json').read_text())['population_bin_edges'],
        'targets':TARGETS,'diameters_km':DIAMETERS,'neighbours':8,'scenarios':SCENARIOS,'methods':METHODS,
        'sampling':{'chains':4,'warmup':700,'samples':700,'target_accept':.95,'depth':10},
        'screen_sampling':{'chains':2,'warmup':300,'samples':400,'target_accept':.95,'depth':10},
        'confirmation_sampling':{'chains':4,'warmup':1000,'samples':1500,'target_accept':.99,'depth':12},
        'variants':{'primary':{'mu_sd':2.,'tau_scale':.5,'beta_sd':.25,'rho_beta':19.},
                    'tighter':{'mu_sd':2.,'tau_scale':.25,'beta_sd':.125,'rho_beta':49.},
                    'wider':{'mu_sd':3.,'tau_scale':1.,'beta_sd':.5,'rho_beta':9.}},
        'simulation':{'development_replicates':30,'validation_stages':[100,500,1000],
                      'development_templates':'Round-robin through development municipalities; one dataset per replicate, never pooled cells as independent replicates.',
                      'validation_templates':'Round-robin through held-out municipalities, independent stream; no selection on validation outputs.'},
        'gate':{'max_rhat':1.01,'min_ess':400,'min_coverage_lower_mc_bound':.9,'max_coverage_mcse':.01,
                'max_cell_rmse_electorate_pp':2.,'min_origin_voters':100,'max_rate_rmse_pp':10.,
                'max_rmse_ratio':1.10,'max_median_width_rate_pp':20.,'max_failure_fraction':.05,
                'max_prior_shift_electorate_pp':2.},
        'resource_policy':{'parallel_workers':4,'fit_timeout_seconds':300,'max_fit_sections':None,
            'note':'Timeout is recorded per fit as unvalidated, never a successful fit. Profile full designs; no subsample certification.'},
        'estimand':'Expected closed-electorate transition counts, not realized latent tables.',
        'intervals':'Pointwise equal-tailed 95% conditional credible intervals; boundary flows additionally use 95% upper bounds.',
        'normal_likelihood':'Moment approximation, 1e-6 jitter; extension adds independent DM origin-row overdispersion and first-four-share contextual effects.',
        'zero_flow_policy':'Two-sided interior coverage is not a valid pass requirement for exact zeros under continuous priors. Export ordinary coverage and separately assess 95% upper limits and practical-zero false positives (lower endpoint above 1pp of origin).'}
    write_json(manifest_path,manifest)
    return manifest


def build_groupings(output=OUT):
    output = Path(output)
    manifest = prepare(output)
    sections = pd.read_csv(output/'sample_sections.csv.gz')
    folder = output/'groupings'
    folder.mkdir(exist_ok=True)
    records = []
    for code,s in sections.groupby('municipality_code',sort=True):
        path = folder/f'{code}.npz'
        csv = folder/f'{code}.csv.gz'
        if path.exists() and csv.exists():
            records.extend(pd.read_csv(csv).to_dict('records'))
            continue
        x,_,points,_ = data_arrays(s)
        labels = {}
        rows = []
        for target in manifest['targets']:
            for cap in manifest['diameters_km']:
                name = f'n{target}_d{cap}'
                group = partition(points,target,cap,manifest['neighbours'])
                labels[name] = group
                for row in group_inventory(x,points,group,target,cap):
                    row.update(config=name,municipality_code=int(code),population_bin=int(s.population_bin.iloc[0]),split=s.split.iloc[0])
                    rows.append(row)
        labels['section_keys'] = s[KEY].astype(str).agg(':'.join,axis=1).to_numpy(str)
        np.savez_compressed(path,**labels)
        pd.DataFrame(rows).to_csv(csv,index=False)
        records.extend(rows)
        print(json.dumps({'grouped_municipality':int(code),'sections':len(s),'configurations':24}),flush=True)
    inventory = pd.DataFrame(records)
    inventory.to_csv(output/'group_inventory.csv.gz',index=False)
    summaries=[]
    for (b,config,split), g in inventory.groupby(['population_bin','config','split']):
        summaries.append({'population_bin':int(b),'config':config,'split':split,'groups':len(g),
            'sections':int(g.sections.sum()),'undersized_fraction':float(g.undersized.mean()),
            'undersized_electorate_fraction':float(g.loc[g.undersized,'electorate'].sum()/g.electorate.sum()),
            'median_diameter_km':float(g.diameter_km.median()),'median_sections':float(g.sections.median()),
            'full_rank_fraction':float(g.design_rank.eq(5).mean()),'max_overshoot_sections':int(g.overshoot_sections.max())})
    pd.DataFrame(summaries).to_csv(output/'group_feasibility.csv',index=False)
    return inventory


def export_membership(output=OUT, selections=None):
    output=Path(output)
    sample=pd.read_csv(output/'sample_sections.csv.gz')
    rows=[]
    for code,s in sample.groupby('municipality_code',sort=True):
        b=int(s.population_bin.iloc[0])
        if selections is None or b not in selections:
            continue
        with np.load(output/'groupings'/f'{code}.npz') as z:
            for config in selections[b]:
                block=s[KEY+['population_bin','split','latitude_1','longitude_1','coordinate_status']].copy()
                block['config']=config;block['group']=z[config]
                rows.append(block)
    if rows:
        pd.concat(rows,ignore_index=True).to_csv(output/'section_group_membership.csv.gz',index=False)
