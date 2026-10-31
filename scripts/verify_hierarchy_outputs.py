"""Audit exported estimates against posterior draws and the original electorate."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd

from elections.hierarchy_inventory import DEFAULT_OUTPUT,arrays,sha256,write_json
from elections.model import ORIGINS,DESTINATIONS


def verify(folder=DEFAULT_OUTPUT):
    folder=Path(folder)
    manifest=json.loads((folder/"manifest.json").read_text())
    for path,digest in manifest["sources"].items():assert sha256(ROOT/path)==digest,path
    reliability=pd.read_csv(folder/"reliability.csv.gz")
    comparisons=pd.read_csv(folder/"municipal_comparison.csv")
    sections=pd.read_csv(folder/"pilot_sections.csv.gz")
    assert comparisons.observed_input_totals_match.all()
    assert reliability.estimate.ge(0).all()
    assert reliability.p025.ge(0).all()
    assert reliability.p975.ge(reliability.p025).all()
    assert reliability.electorate_coverage.between(0,1).all()
    assert reliability.loc[reliability.origin_voters.eq(0),"rate"].isna().all()
    max_error=0.
    for city in manifest["pilot"]:
        code=int(city["municipality_code"])
        s=sections[sections.municipality_code.eq(code)]
        x,y,place,keys=arrays(s)
        for variant in manifest["variants"]:
            with np.load(folder/"fits"/f"{code}-{variant}.npz") as archive:
                draws={key:archive[key] for key in ["local","municipal"]}
            assert np.allclose(draws["local"].sum(1),draws["municipal"],atol=1e-7,rtol=0)
            assert np.allclose(draws["municipal"].sum(2),x.sum(0)[None],atol=1e-7,rtol=0)
            assert np.allclose(draws["municipal"].sum((1,2)),x.sum(),atol=1e-7,rtol=0)
            if variant!="primary":continue
            for level,p,d in [("municipality",None,draws["municipal"]),*[("place",p,draws["local"][:,p]) for p in range(len(keys))]]:
                r=reliability[reliability.municipality_code.eq(code)&reliability.method.eq("hierarchical")&reliability.level.eq(level)]
                if p is not None:
                    _,_,zone,local=keys[p].split(':')
                    r=r[r.zone.eq(int(zone))&r.polling_place.eq(int(local))]
                r=r.set_index(["origin","destination"]).reindex(pd.MultiIndex.from_product([ORIGINS,DESTINATIONS]))
                assert len(r)==20 and r.estimate.notna().all()
                mean=d.mean(0).ravel();lo,hi=np.quantile(d,[.025,.975],axis=0).reshape(2,-1)
                error=float(abs(r.estimate.to_numpy()-mean).max());max_error=max(max_error,error)
                assert error<1e-7
                assert np.allclose(r.p025,lo,atol=1e-7,rtol=0)
                assert np.allclose(r.p975,hi,atol=1e-7,rtol=0)
                assert np.allclose(r.interval_width_voters,hi-lo,atol=1e-7,rtol=0)
                origin=x.sum(0) if p is None else x[place==p].sum(0)
                nonzero=np.repeat(origin,4)>0
                assert np.allclose(r.rate.to_numpy()[nonzero],mean[nonzero]/np.repeat(origin,4)[nonzero],atol=1e-10,rtol=0)
    geometry=json.loads((ROOT/"docs/data/maps/municipality.geojson").read_text())
    assert set(comparisons.municipality_code)<=set(int(f['properties']['key']) for f in geometry['features'])
    result={"passed":True,"source_hashes_unchanged":True,"all_local_draws_aggregate":True,
            "quantiles_computed_after_aggregation":True,"municipalities":len(comparisons),
            "reliability_rows":len(reliability),"maximum_export_rounding_error_voters":max_error,
            "zero_origin_rates_unavailable":True,"map_join_unmatched":0}
    write_json(folder/"output_checks.json",result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    verify(parser.parse_args().output)
