"""Post-screen longer-chain confirmation, not a replacement simulation benchmark."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from elections.hierarchy import fit_hierarchy
from elections.hierarchy_inventory import DEFAULT_OUTPUT,arrays,write_json
from elections.hierarchy_simulation import generate,score


def confirm(folder=DEFAULT_OUTPUT):
    folder=Path(folder)
    manifest=json.loads((folder/'manifest.json').read_text())
    sections=pd.read_csv(folder/'pilot_sections.csv.gz')
    x0,_,p0,_=arrays(sections[sections.municipality_code.eq(81914)])
    directory=folder/'confirmation';directory.mkdir(exist_ok=True)
    protocol={"purpose":"Post-screen computational confirmation of contextual/within-place failures and structural-zero interval behavior; not an independent calibration study.",
              "scenarios":["contextual","within_place","boundary"],"replicates":[0,1,2],
              "chains":4,"warmup":1000,"samples":1500,"target_accept":.95,
              "changes":"Same simulated counts/true transitions as screen. New independent MCMC seed and longer chains; no change to original 30-replicate results."}
    write_json(directory/'protocol.json',protocol)
    rows=[]
    for scenario in protocol['scenarios']:
        index=manifest['simulation']['scenarios'].index(scenario)
        for replicate in protocol['replicates']:
            path=directory/f'{scenario}-{replicate:03d}.json'
            if path.exists():rows.append(json.loads(path.read_text()));continue
            seed=manifest['seed']+100000+index*10000+replicate
            x,y,place,true,_=generate(x0,p0,scenario,seed)
            fit=fit_hierarchy(x,y,place,seed=seed+50000000,chains=4,warmup=1000,samples=1500)
            d=fit['municipal_draws'];metrics=score(d.mean(0),true.sum(0),d)
            old_path=folder/'simulations'/f'{scenario}-{replicate:03d}.json'
            old=json.loads(old_path.read_text()) if old_path.exists() else None
            previous=np.array([v['hierarchical_expected_voters'] for v in old['flows']]).reshape(5,4) if old else None
            result={"scenario":scenario,"replicate":replicate,**metrics,**fit['diagnostics'],
                    "max_mean_change_electorate_pp":float(abs(d.mean(0)-previous).max()/x.sum()*100) if previous is not None else None}
            fit['parameter_diagnostics'].to_csv(directory/f'{scenario}-{replicate:03d}-parameters.csv')
            write_json(path,result);rows.append(result)
            print(json.dumps(result),flush=True)
    pd.DataFrame(rows).to_csv(folder/'long_chain_confirmation.csv',index=False)


if __name__=='__main__':confirm()
