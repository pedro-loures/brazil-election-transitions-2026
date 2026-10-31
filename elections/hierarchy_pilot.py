"""Resumable pilot fits, comparable expected flows, reliability, and red flags."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd

from .hierarchy import fit_hierarchy, expected_flows, likelihood_audit, predictive_checks
from .hierarchy_inventory import DEFAULT_OUTPUT, ROOT, GROUP, arrays, prepare, write_json
from .model import ORIGINS, DESTINATIONS


def summarize(draws, denominator):
    mean=draws.mean(0)
    low,high=np.quantile(draws,[.025,.975],axis=0)
    return mean,low,high


def _fit_city(task):
    output,manifest,city=task
    output=Path(output)
    folder=output/"fits"
    sections=pd.read_csv(output/"pilot_sections.csv.gz")
    code=int(city["municipality_code"])
    s=sections[sections.municipality_code.eq(code)]
    x,y,place,keys=arrays(s)
    for variant_no,(variant,config) in enumerate(manifest["variants"].items()):
        prefix=folder/f"{code}-{variant}"
        if prefix.with_suffix(".json").exists():
            continue
        seed=manifest["seed"]+code+variant_no*1000000
        fit=fit_hierarchy(x,y,place,seed=seed,**config,**manifest["sampling"])
        checks=predictive_checks(x,y,place,fit["probabilities"],seed+100) if variant=="primary" else {}
        diagnostics={**fit["diagnostics"],**checks,"uf":city["uf"],"municipality_code":code,
                     "variant":variant,"seed":seed,"place_keys":keys,"n_sections":len(x)}
        # Save draws before the completion marker; interrupted fits will rerun.
        np.savez_compressed(prefix.with_suffix(".npz"),local=fit["local_draws"],municipal=fit["municipal_draws"],
                            mu=fit["posterior"]["mu"],tau=fit["posterior"]["tau"],z=fit["posterior"]["z"])
        fit["parameter_diagnostics"].to_csv(folder/f"{code}-{variant}-parameters.csv")
        write_json(prefix.with_suffix(".json"),diagnostics)
        print(json.dumps({k:diagnostics[k] for k in ["municipality_code","variant","status","rhat_max","ess_bulk_min","elapsed_seconds"]}),flush=True)
    return code


def fit_pilot(output=DEFAULT_OUTPUT,workers=4,only=None):
    output=Path(output)
    manifest=prepare(output)
    folder=output/"fits"
    folder.mkdir(exist_ok=True)
    sections=pd.read_csv(output/"pilot_sections.csv.gz")
    inventory=pd.read_csv(output/"polling_place_inventory.csv.gz")
    write_json(output/"likelihood_audit.json",likelihood_audit())
    prior_predictive=[]
    rng=np.random.default_rng(manifest["seed"])
    from scipy.special import softmax
    for name,config in manifest["variants"].items():
        mu=rng.normal(0,config["mu_sd"],(2000,1,5,3))
        tau=abs(rng.normal(0,config["tau_scale"],(2000,1,1,1)))
        logits=mu+tau*rng.normal(size=(2000,9,5,3))
        p=softmax(np.concatenate([logits,np.zeros((*logits.shape[:-1],1))],axis=-1),axis=-1)
        prior_predictive.append({"variant":name,"prior_probability_below_001":float((p<.01).mean()),
                                 "prior_probability_above_099":float((p>.99).mean()),
                                 "tau_p025":float(np.quantile(tau,.025)),"tau_p975":float(np.quantile(tau,.975)),
                                 "note":"Neutral broad logits do not assume voter retention. Inspect posterior sensitivity; this is not substantive prior evidence."})
    write_json(output/"prior_predictive.json",prior_predictive)
    tasks=[(str(output),manifest,city) for city in manifest["pilot"] if only is None or int(city["municipality_code"]) in only]
    if workers==1:
        for task in tasks:_fit_city(task)
    else:
        from concurrent.futures import ProcessPoolExecutor
        from multiprocessing import get_context
        # Spawn, never fork an initialized JAX runtime. Each city has disjoint files.
        with ProcessPoolExecutor(max_workers=workers,mp_context=get_context("spawn")) as executor:
            list(executor.map(_fit_city,tasks))
    complete=all((folder/f"{int(city['municipality_code'])}-{variant}.json").exists()
                 for city in manifest["pilot"] for variant in manifest["variants"])
    if not complete:
        print("Requested fit batch complete; waiting for the remaining pilot batches before export.",flush=True)
        return
    export_comparison(output)
    import jax,numpyro,arviz,scipy
    write_json(output/"run.json",{"completed_utc":datetime.now(timezone.utc).isoformat(),
               "manifest_sha256":__import__('hashlib').sha256((output/"manifest.json").read_bytes()).hexdigest(),
               "python":platform.python_version(),"numpy":np.__version__,"pandas":pd.__version__,
               "scipy":scipy.__version__,"jax":jax.__version__,"numpyro":numpyro.__version__,"arviz":arviz.__version__,
               "likelihood":"Three-dimensional normal approximation to sum of independent multinomial rows",
               "baseline_preserved":True,"scope":"12 municipalities; national expansion conditional on validation gate"})


def export_comparison(output):
    output=Path(output)
    manifest=json.loads((output/"manifest.json").read_text())
    sections=pd.read_csv(output/"pilot_sections.csv.gz")
    inventory=pd.read_csv(output/"polling_place_inventory.csv.gz")
    baseline=pd.read_csv(ROOT/"results/2026/estimated_flows.csv.gz")
    cities=pd.read_csv(ROOT/"results/2026/municipalities.csv")
    flow_rows,comparison_rows,municipal_rows,fit_rows,check_rows,investigations=[],[],[],[],[],[]
    for city in manifest["pilot"]:
        code=int(city["municipality_code"])
        s=sections[sections.municipality_code.eq(code)]
        x,y,place,keys=arrays(s)
        city_original=cities[cities.municipality_code.eq(code)].iloc[0]
        for i,g in enumerate(ORIGINS):
            if int(x[:,i].sum())!=int(city_original["analyzed_"+g+"_1"]):
                raise ValueError("Paired baseline electorate mismatch")
        for j,g in enumerate(DESTINATIONS):
            if int(y[:,j].sum())!=int(city_original["analyzed_"+g+"_2"]):
                raise ValueError("Paired baseline outcome mismatch")
        old=baseline[(baseline.municipality_code==code)&baseline.model.eq("full")]
        old=old.set_index(["origin","destination"]).reindex(pd.MultiIndex.from_product([ORIGINS,DESTINATIONS]))
        old_flows=old.estimated_voters.to_numpy().reshape(5,4)
        if not np.allclose(old_flows.sum(1),x.sum(0),rtol=0,atol=1e-4):
            raise ValueError("Baseline flow origins do not match common input")
        fitted={}
        diagnostics={}
        for variant in manifest["variants"]:
            prefix=output/"fits"/f"{code}-{variant}"
            # NpzFile re-decompresses on every indexing access. Materialize each
            # required array once, before the per-place/per-flow export loops.
            with np.load(prefix.with_suffix(".npz")) as archive:
                fitted[variant]={key:archive[key] for key in ["local","municipal"]}
            diagnostics[variant]=json.loads(prefix.with_suffix(".json").read_text())
            fit_rows.append(diagnostics[variant])
        primary=fitted["primary"]
        local=primary["local"]
        # Executable check of exact draw-by-draw aggregation, before quantiles.
        if not np.allclose(local.sum(1),primary["municipal"],rtol=0,atol=1e-7):
            raise ValueError("Municipal draws are not sums of local draws")
        local_origins=np.zeros((len(keys),5));np.add.at(local_origins,place,x)
        local_probability=np.divide(local.mean(0),local_origins[:,:,None],
                                    out=np.zeros_like(local.mean(0)),where=local_origins[:,:,None]>0)
        section_prediction=np.einsum("sg,sgk->sk",x,local_probability[place])
        means={k:v["municipal"].mean(0) for k,v in fitted.items()}
        local_means={k:v["local"].mean(0) for k,v in fitted.items()}
        delta=means["primary"]-old_flows
        rates_delta=np.divide(delta,x.sum(0)[:,None],out=np.full_like(delta,np.nan),where=x.sum(0)[:,None]>0)*100
        supported=x.sum(0)>=manifest["warnings"]["supported_origin_min_voters"]
        max_rate=float(abs(rates_delta[supported]).max()) if supported.any() else None
        distance=float(abs(delta).sum()/(2*x.sum()))
        key_difference=float(abs(delta[3:,:2]).max()/x.sum()*100)
        sensitivity=float(max(abs(means[v]-means["primary"]).max()/x.sum()*100 for v in ["tighter","wider"]))
        diag=diagnostics["primary"]
        old_rates=np.divide(old_flows,x.sum(0)[:,None],out=np.zeros_like(old_flows),where=x.sum(0)[:,None]>0)
        boundary_cells=int(((old_rates<1e-6)|(old_rates>1-1e-6)).sum())
        old_local=local_origins[:,:,None]*old_rates[None]
        local_contribution=abs(local.mean(0)-old_local).sum(axis=(1,2))/(2*x.sum())
        largest_places=[{"place_key":keys[int(p)],"sections":int((place==p).sum()),
                         "sum_absolute_local_cell_difference_over_2N":float(local_contribution[p])}
                        for p in np.argsort(local_contribution)[-3:][::-1]]
        flags=[]
        if distance>manifest["warnings"]["matrix_distance"]:flags.append("matrix_disagreement")
        if max_rate is not None and max_rate>manifest["warnings"]["supported_origin_max_rate_difference_pp"]:flags.append("origin_rate_disagreement")
        if key_difference>manifest["warnings"]["key_flow_difference_electorate_pp"]:flags.append("key_flow_disagreement")
        if sensitivity>manifest["warnings"]["sensitivity_electorate_pp"]:flags.append("prior_sensitivity")
        if diag["status"]!="ok":flags.append("sampling_diagnostics")
        if city["electorate_coverage"]<.9:flags.append("coverage_below_90pct")
        condition=city["design_condition"]
        notes=("Input and baseline origin/destination totals agree exactly; local draws sum to municipality. "
               "Baseline expected destination totals are hard-calibrated; hierarchical expectations are stochastic-model predictions. "
               f"Design condition {condition:.1f}; {city['sparse_places']} of {city['places']} places have fewer than five sections. "
               f"Largest prior-variant cell shift {sensitivity:.2f}% of electorate. "
               f"The baseline has {boundary_cells}/20 near-boundary rates; the primary softmax prior gives no exact structural zeros. "
               "Largest local contributions are descriptive allocations, not leave-one-place-out influence estimates. "
               "Hidden individual flows remain unidentified. Model disagreement requires known-flow validation; it does not choose a winning method.")
        investigations.append({"municipality_code":code,"municipality":city["municipality"],"flags":flags,
                               "source_and_electorate_alignment":"passed", "calibration_difference_disclosed":True,
                               "baseline_boundary_cells":boundary_cells,"design_condition":condition,
                               "sparse_places":int(city["sparse_places"]),"places":int(city["places"]),
                               "primary_sampling":diag["status"],
                               "variant_sampling":{v:d["status"] for v,d in diagnostics.items()},
                               "largest_prior_cell_shift_electorate_pp":sensitivity,
                               "largest_local_contributions":largest_places,
                               "remaining_identification":"No individual flow truth; nonlinearity/likelihood/prior effects cannot be separated by agreement of margins. Comparison changes both locality structure and estimator, so disagreement is not attributable solely to pooling.",
                               "resolution":"unresolved_model_dependence" if any(v.endswith("disagreement") for v in flags) else "no_material_disagreement"})
        municipal_rows.append({**city,"electorate":int(x.sum()),"matrix_distance":distance,
                               "max_supported_rate_difference_pp":max_rate,"key_flow_difference_electorate_pp":key_difference,
                               "max_prior_sensitivity_electorate_pp":sensitivity,"observed_input_totals_match":True,
                               "predicted_margin_error_votes":diag["expected_margin_max_error_votes"],
                               "rhat_max":diag["rhat_max"],"ess_bulk_min":diag["ess_bulk_min"],"ess_tail_min":diag["ess_tail_min"],
                               "rmse_votes":diag["rmse_votes"],"ppc_discrepancy_probability":diag["ppc_discrepancy_probability"],
                               "status":diag["status"],"flags":";".join(flags),"material_flag":any(v.endswith("disagreement") for v in flags),
                               "investigation_status":"unresolved_model_dependence" if any(v.endswith("disagreement") for v in flags) else "no_material_disagreement",
                               "investigation_notes":notes})
        for level,p,expected in [("municipality",None,primary["municipal"]),*[("place",p,local[:,p]) for p in range(len(keys))]]:
            subset=np.ones(len(x),dtype=bool) if p is None else place==p
            origin=x[subset].sum(0)
            n=origin.sum()
            mu,lo,hi=summarize(expected,origin)
            if p is None:
                coverage=city["electorate_coverage"]
                union=city["sections_union"]
                place_code,zone=None,None
            else:
                row=s.loc[subset].iloc[0]
                zone,place_code=int(row.zone),int(row.polling_place_1)
                inv=inventory[(inventory.municipality_code==code)&(inventory.zone==zone)&(inventory.polling_place_1==place_code)].iloc[0]
                coverage=float(inv.electorate_coverage);union=int(inv.sections_union)
            residual=expected.mean(0).sum(0)-y[subset].sum(0)
            z=x[subset]/x[subset].sum(1)[:,None]
            rank=int(np.linalg.matrix_rank(z))
            common={"uf":city["uf"],"municipality_code":code,"municipality":city["municipality"],"level":level,
                    "zone":zone,"polling_place":place_code,"electorate":int(n),"electorate_coverage":coverage,
                    "sections_included":int(subset.sum()),"sections_excluded":int(union-subset.sum()),"design_rank":rank,
                    "design_condition":float(np.linalg.cond(z)) if rank==5 else None,
                    "weak_design":bool(rank<5 or (rank==5 and np.linalg.cond(z)>100)),
                    "rhat_max":diag["rhat_max"],"ess_bulk_min":diag["ess_bulk_min"],"ess_tail_min":diag["ess_tail_min"],
                    "divergences":diag["divergences"],"tau_mean":diag["tau_mean"],"tau_p025":diag["tau_p025"],"tau_p975":diag["tau_p975"],
                    "fit_status":diag["status"],"expected_margin_error_votes":float(abs(residual).max()),
                    "rmse_votes":float(np.sqrt(np.mean((section_prediction[subset]-y[subset])**2))),
                    "municipal_matrix_distance":distance if level=="municipality" else None,
                    "municipal_flags":";".join(flags),"validation_status":"exploratory_not_certified"}
            for i,g in enumerate(ORIGINS):
                for j,dest in enumerate(DESTINATIONS):
                    prior_sensitivity=max(abs(means[v][i,j]-mu[i,j]) if p is None
                                          else abs(local_means[v][p,i,j]-mu[i,j]) for v in ["tighter","wider"])
                    flow_rows.append({**common,"method":"hierarchical","origin":g,"destination":dest,
                                      "origin_voters":int(origin[i]),"estimate":float(mu[i,j]),"p025":float(lo[i,j]),"p975":float(hi[i,j]),
                                      "interval_width_voters":float(hi[i,j]-lo[i,j]),
                                      "rate":float(mu[i,j]/origin[i]) if origin[i] else None,
                                      "rate_p025":float(lo[i,j]/origin[i]) if origin[i] else None,
                                      "rate_p975":float(hi[i,j]/origin[i]) if origin[i] else None,
                                      "interval_width_pp":float((hi[i,j]-lo[i,j])/origin[i]*100) if origin[i] else None,
                                      "prior_sensitivity_voters":float(prior_sensitivity),
                                      "prior_sensitivity_pp":float(prior_sensitivity/origin[i]*100) if origin[i] else None,
                                      "small_origin":bool(origin[i]<100),
                                      "interval_type":"pointwise 95% posterior credible interval; normal-approximation likelihood"})
            if level=="municipality":
                for i,g in enumerate(ORIGINS):
                    for j,dest in enumerate(DESTINATIONS):
                        oldrow=old.loc[(g,dest)]
                        lower,upper=float(oldrow.bootstrap_p025),float(oldrow.bootstrap_p975)
                        flow_rows.append({**common,"method":"municipal_baseline","origin":g,"destination":dest,
                                          "origin_voters":int(origin[i]),"estimate":float(old_flows[i,j]),"p025":lower,"p975":upper,
                                          "rate":float(oldrow.rate) if origin[i] else None,
                                          "rate_p025":lower/origin[i] if origin[i] else None,"rate_p975":upper/origin[i] if origin[i] else None,
                                          "interval_width_voters":upper-lower,"interval_width_pp":(upper-lower)/origin[i]*100 if origin[i] else None,
                                          "prior_sensitivity_voters":None,"prior_sensitivity_pp":None,
                                          "fit_status":"ok","rhat_max":None,"ess_bulk_min":None,"ess_tail_min":None,"divergences":None,
                                          "tau_mean":None,"tau_p025":None,"tau_p975":None,
                                          "expected_margin_error_votes":float(city_original.full_margin_error_votes),
                                          "rmse_votes":float(city_original.full_rmse_votes),
                                          "small_origin":bool(origin[i]<100),
                                          "interval_type":"150-resample section bootstrap percentile sensitivity range; coverage unvalidated"})
                        comparison_rows.append({"uf":city["uf"],"municipality_code":code,"origin":g,"destination":dest,
                                                "origin_voters":int(origin[i]),"common_electorate":int(n),"baseline":float(old_flows[i,j]),
                                                "hierarchical":float(mu[i,j]),"difference_voters":float(delta[i,j]),
                                                "absolute_difference_voters":float(abs(delta[i,j])),"rate_difference_pp":float(rates_delta[i,j]) if origin[i] else None,
                                                "supported_origin":bool(supported[i]),"matrix_distance":distance,
                                                "baseline_boundary_rate":bool(old_rates[i,j]<1e-6 or old_rates[i,j]>1-1e-6),
                                                "baseline_p025":lower,"baseline_p975":upper,"hierarchical_p025":float(lo[i,j]),"hierarchical_p975":float(hi[i,j]),
                                                "interval_overlap_is_test":False,"flags":";".join(flags)})
        # Section outcome predictions and observed-margin bounds remain separately labeled.
        counts=np.zeros((len(keys),5));np.add.at(counts,place,x)
        pp=np.divide(local.mean(0),counts[:,:,None],out=np.zeros_like(local.mean(0)),where=counts[:,:,None]>0)
        prediction=np.einsum("sg,sgk->sk",x,pp[place])
        for idx,row in enumerate(s.itertuples()):
            check_rows.append({"municipality_code":code,"zone":int(row.zone),"section":int(row.section),
                               "polling_place":int(row.polling_place_1),"rmse_votes":float(np.sqrt(np.mean((prediction[idx]-y[idx])**2))),
                               "observed_a_mobilization_lower":float(row.a_mobilization_lower),
                               "observed_a_mobilization_upper":float(row.a_mobilization_upper),
                               "hierarchical_expected_a_mobilization":float((x[idx,3:,None]*pp[place[idx],3:]).sum(axis=0)[0]),
                               "bounds_apply_to":"realized closed-electorate tables, not all expected-flow posterior draws"})
    pd.DataFrame(flow_rows).to_csv(output/"reliability.csv.gz",index=False)
    pd.DataFrame(comparison_rows).to_csv(output/"municipal_flow_comparison.csv",index=False)
    pd.DataFrame(municipal_rows).to_csv(output/"municipal_comparison.csv",index=False)
    pd.DataFrame(fit_rows).to_csv(output/"fit_diagnostics.csv",index=False)
    pd.DataFrame(check_rows).to_csv(output/"section_predictive_checks.csv",index=False)
    write_json(output/"municipal_investigations.json",investigations)
    checks=pd.DataFrame(check_rows)
    checks["squared_rmse"]=checks.rmse_votes**2
    by_place=checks.groupby(["municipality_code","zone","polling_place"]).agg(
        sections=("section","size"),mean_squared_section_rmse=("squared_rmse","mean"),
        max_section_rmse=("rmse_votes","max"))
    by_place["rmse_votes"]=np.sqrt(by_place.mean_squared_section_rmse)
    by_place.to_csv(output/"place_predictive_checks.csv")


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument("--workers",type=int,default=4)
    parser.add_argument("--only",type=int,nargs="+")
    args=parser.parse_args()
    fit_pilot(args.output,args.workers,args.only)
