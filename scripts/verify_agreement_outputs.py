"""Check paired data, fixed denominators and exported posterior aggregation."""
import argparse,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from elections.agreement_runner import OUT,prepare,case_data
from elections.agreement_model import prediction_chunks
from elections.spatial import seed_for
from elections.spatial_runner import save


def verify(output=OUT):
    output=Path(output);m=prepare(output)
    records=[json.loads(p.read_text()) for p in (output/'jobs').glob('*.json') if not p.name.endswith('.job.json')]
    paired={};rows=0;posterior_checks=0
    for r in records:
        j=r['job']
        if 'data_seed' in r:
            key=tuple(j[k] for k in ['phase','municipality_code','scenario','replicate'])
            signature=(r['data_seed'],r['weight_sha256'],r['electorate'],tuple(r['observed_round_totals']))
            if key in paired and paired[key]!=signature:raise ValueError('Models did not receive identical paired data')
            paired[key]=signature
        if not r.get('flow_file'):continue
        f=pd.read_csv(output/r['flow_file'])
        if f.duplicated(['support','unit','origin','destination']).any():raise ValueError('Duplicate flow identifier')
        if (f.high<f.low-1e-9).any() or (f.low<-1e-8).any() or (f.high>f.origin_voters+1e-8).any():raise ValueError('Invalid interval')
        for _,b in f.groupby(['support','unit','origin']):
            if len(b)!=4 or not np.isclose(b.estimate.sum(),b.origin_voters.iloc[0]):raise ValueError('Original origin total not preserved')
        rows+=len(f)
        posterior=output/'fits'/(Path(r['flow_file']).name.removesuffix('.csv.gz')+'.npz')
        if not posterior.exists():continue
        s,x,y,points,admin,weight,group,truth,data_seed=case_data(m,j)
        seed=seed_for(data_seed,j['family'],j['variant'],j['phase'],j['replicate'])
        p=dict(np.load(posterior));draws=np.zeros((m['sampling']['chains']*m['sampling']['samples'],5,4))
        for sl,prob,_,_ in prediction_chunks(p,x,y,group,j['family'],weight,seed+1):draws+=(prob*x[None,sl,:,None]).sum(1)
        municipal=f[f.support.eq('municipality')].sort_values(['origin','destination'])
        for column,reference in [('estimate',draws.mean(0)),('low',np.quantile(draws,.025,axis=0)),('high',np.quantile(draws,.975,axis=0))]:
            if not np.allclose(municipal[column].to_numpy(),reference.ravel(),atol=1e-8):raise ValueError('Posterior draws not aggregated before intervals')
            posterior_checks+=20
    result={'passed':True,'paired_cases_checked':len(paired),'exported_flow_rows_checked':rows,'posterior_cells_checked':posterior_checks,
            'frozen_sources_unchanged':True,'scope':'Software/data consistency, not statistical accuracy or calibration.'}
    save(output/'output_checks.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=OUT)
    print(json.dumps(verify(p.parse_args().output),indent=2))
