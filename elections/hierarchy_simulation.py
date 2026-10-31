"""Known-flow validation. Results include failures, not just successful fits."""
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from scipy.special import softmax

from .hierarchy import fit_hierarchy, validate_counts
from .hierarchy_inventory import DEFAULT_OUTPUT, arrays, prepare, write_json
from .model import fit_transition, model_city

BASE = np.array([[.88,.04,.02,.06],[.03,.88,.02,.07],[.35,.45,.07,.13],
                 [.30,.25,.25,.20],[.25,.20,.04,.51]])


def generate(x, place, scenario, seed):
    rng = np.random.default_rng(seed)
    x, place = x.copy().astype(int), place.copy()
    if scenario == "few_places":
        place=rng.permutation(np.arange(len(x)))%2
    if scenario == "sparse":
        # Same section count: five singleton places and four larger groups.
        place = np.r_[np.arange(5), 5+np.minimum(np.arange(len(x)-5)//6,3)]
    if scenario == "weak_design":
        n = x.sum(1)
        # Nearly collinear design; also a tiny origin category.
        proportions = np.array([.37,.37,.002,.038,.22])
        x = np.vstack([rng.multinomial(int(v),proportions) for v in n])
    tau = {"homogeneous":0.,"moderate":.4,"strong":1.,"contextual":.5,
           "within_place":.4,"weak_design":.4,"sparse":.5,"boundary":.4,"few_places":.5}[scenario]
    log_base = np.log(BASE[:,:3]/BASE[:,3:])
    z = rng.normal(size=(place.max()+1,5,3))
    logit = log_base[None]+tau*z
    if scenario == "contextual":
        composition = np.array([x[place==p,0].sum()/x[place==p].sum() for p in range(place.max()+1)])
        contextual = (composition-composition.mean())/(composition.std()+1e-8)
        logit[:,:,0] += contextual[:,None]*1.5
        logit[:,:,1] -= contextual[:,None]*1.5
    logit = logit[place]
    if scenario == "within_place":
        logit += rng.normal(0,.75,logit.shape)
    p = softmax(np.concatenate([logit,np.zeros((*logit.shape[:-1],1))],axis=-1),axis=-1)
    if scenario == "boundary":
        p[:,0,1] = p[:,1,0] = 0.
        p /= p.sum(axis=-1,keepdims=True)
    table = np.zeros_like(p)
    for s in range(len(x)):
        for g in range(5):
            table[s,g] = rng.multinomial(int(x[s,g]),p[s,g])
    expected = x[:,:,None]*p
    local_truth = np.zeros((place.max()+1,5,4))
    local_realized = np.zeros_like(local_truth)
    np.add.at(local_truth,place,expected)
    np.add.at(local_realized,place,table)
    return x,table.sum(1),place,local_truth,local_realized


def score(estimate, truth, draws=None):
    error = (estimate-truth)/truth.sum()
    result = {"allocation_conservation_residual_electorate_pp":float(error.mean()*100),
              "mae_electorate_pp":float(abs(error).mean()*100),
              "rmse_electorate_pp":float(np.sqrt(np.mean(error**2))*100),
              "matrix_distance_to_truth":float(abs(estimate-truth).sum()/(2*truth.sum())),
              "near_boundary_cells":int(((estimate<1e-5)|(estimate>truth.sum()-1e-5)).sum())}
    if draws is not None:
        low, high = np.quantile(draws,[.025,.975],axis=0)
        covered = (truth>=low)&(truth<=high)
        result.update(coverage=float(covered.mean()),width_electorate_pp=float((high-low).mean()/truth.sum()*100))
        result["abstention_to_a_covered"] = bool(covered[4,0])
    result["abstention_to_a_bias_electorate_pp"] = float((estimate[4,0]-truth[4,0])/truth.sum()*100)
    return result


def simulate(output=DEFAULT_OUTPUT, replicates=None, scenarios_only=None, fit_only=False):
    output = Path(output)
    manifest = prepare(output)
    config = manifest["simulation"]
    replicates = replicates or config["replicates"]
    folder = output/"simulations"
    folder.mkdir(exist_ok=True)
    sections = pd.read_csv(output/"pilot_sections.csv.gz")
    x0,y0,place0,_ = arrays(sections[sections.municipality_code.eq(81914)])
    completed = []
    extension=json.loads((output/"validation_extension.json").read_text()) if (output/"validation_extension.json").exists() else {}
    scenarios=config["scenarios"]+extension.get("additional_scenarios",[])
    for scenario_no, scenario in enumerate(scenarios):
        if scenarios_only is not None and scenario not in scenarios_only:
            continue
        for replicate in range(replicates):
            path = folder/f"{scenario}-{replicate:03d}.json"
            if path.exists():
                completed.extend(json.loads(path.read_text())["metrics"])
                continue
            started = time.monotonic()
            seed = manifest["seed"]+100000+scenario_no*10000+replicate
            x,y,place,local_true,local_realized = generate(x0,place0,scenario,seed)
            truth = local_true.sum(0)
            rows, error_rows = [],[]
            baseline_diagnostic, baseline_long = model_city(("SC",81914,x,y,150,seed,10))
            baseline = None
            if baseline_diagnostic["model_status"] == "ok":
                full = [v for v in baseline_long if v["model"] == "full"]
                baseline = np.array([v["estimated_voters"] for v in full]).reshape(5,4)
                low = np.array([v["bootstrap_p025"] for v in full]).reshape(5,4)
                high = np.array([v["bootstrap_p975"] for v in full]).reshape(5,4)
                metrics = score(baseline,truth)
                metrics.update(coverage=float(((truth>=low)&(truth<=high)).mean()),
                               width_electorate_pp=float((high-low).mean()/x.sum()*100))
                rows.append(dict(method="municipal_baseline",level="municipality",status="ok",**metrics))
                # Compare its implied local allocations too, without calling it an independent local fit.
                rate = baseline/x.sum(0)[:,None]
                for p in range(place.max()+1):
                    f=x[place==p].sum(0)[:,None]*rate
                    rows.append(dict(method="municipal_baseline",level="place",place=p,status="ok",
                                     sparse=bool((place==p).sum()<5),**score(f,local_true[p])))
            else:
                rows.append(dict(method="municipal_baseline",level="municipality",status=baseline_diagnostic["model_status"]))
            for p in range(place.max()+1):
                subset = place==p
                xp,yp=x[subset],y[subset]
                status="too_few_sections" if subset.sum()<10 else (
                    "rank_deficient" if np.linalg.matrix_rank(xp/xp.sum(1)[:,None])<5 else "estimable")
                independent=fit_transition(xp,yp) if status=="estimable" else {"status":status}
                metrics=score(independent["flows"],local_true[p]) if independent["status"]=="ok" else {}
                rows.append(dict(method="independent_place",level="place",place=p,
                                 sparse=bool(subset.sum()<5),status=independent["status"],**metrics))
            try:
                fitted=fit_hierarchy(x,y,place,seed=seed,chains=config["chains"],
                                     warmup=config["warmup"],samples=config["samples"])
                draws=fitted["municipal_draws"]
                estimate=draws.mean(0)
                metrics=score(estimate,truth,draws)
                disagreement=float(abs(estimate-baseline).sum()/(2*x.sum())) if baseline is not None else None
                metrics.update(matrix_disagreement=disagreement,
                               baseline_distance_to_truth=None if baseline is None else float(abs(baseline-truth).sum()/(2*x.sum())))
                rows.append(dict(method="hierarchical",level="municipality",status=fitted["diagnostics"]["status"],
                                 **metrics,**{k:v for k,v in fitted["diagnostics"].items() if k!="status"}))
                for p in range(place.max()+1):
                    d=fitted["local_draws"][:,p]
                    rows.append(dict(method="hierarchical",level="place",place=p,
                                     status=fitted["diagnostics"]["status"],sparse=bool((place==p).sum()<5),
                                     **score(d.mean(0),local_true[p],d)))
                for i in range(5):
                    for j in range(4):
                        low,high=np.quantile(draws[:,i,j],[.025,.975])
                        error_rows.append({"origin_index":i,"destination_index":j,
                                           "true_expected_voters":float(truth[i,j]),"true_realized_voters":float(local_realized.sum(0)[i,j]),
                                           "hierarchical_expected_voters":float(estimate[i,j]),"p025":float(low),"p975":float(high),
                                           "baseline_expected_voters":None if baseline is None else float(baseline[i,j])})
            except (ValueError, RuntimeError, FloatingPointError) as exc:
                rows.append(dict(method="hierarchical",level="municipality",status="fit_failed",reason=str(exc)))
            for row in rows:
                row.update(scenario=scenario,replicate=replicate,seed=seed)
            write_json(path,{"metrics":rows,"flows":error_rows,"elapsed_seconds":time.monotonic()-started})
            completed.extend(rows)
            print(json.dumps({"scenario":scenario,"replicate":replicate,"seconds":round(time.monotonic()-started,2)}),flush=True)
    if fit_only:
        return completed
    for row in completed:
        if "bias_electorate_pp" in row:
            # Early cached screen files used this legacy name for a conservation
            # residual that cancels across cells. It is not a flow-bias metric.
            row["allocation_conservation_residual_electorate_pp"]=row.pop("bias_electorate_pp")
    pd.DataFrame(completed).to_csv(output/"simulation_metrics.csv",index=False)
    individual=[]
    for path in sorted(folder.glob("*.json")):
        saved=json.loads(path.read_text())
        if not saved["metrics"]:continue
        label=saved["metrics"][0]
        if label["replicate"]>=replicates:continue
        for flow in saved["flows"]:
            individual.append({"scenario":label["scenario"],"replicate":label["replicate"],**flow})
    individual=pd.DataFrame(individual)
    individual.to_csv(output/"simulation_flows.csv.gz",index=False)
    detailed=[]
    for (scenario,origin,destination),b in individual.groupby(["scenario","origin_index","destination_index"]):
        truth=b.true_expected_voters
        for method,field in [("hierarchical","hierarchical_expected_voters"),("municipal_baseline","baseline_expected_voters")]:
            error=b[field]-truth
            row={"scenario":scenario,"origin_index":int(origin),"destination_index":int(destination),"method":method,
                 "replicates":len(b),"bias_voters":float(error.mean()),"mae_voters":float(abs(error).mean()),
                 "rmse_voters":float(np.sqrt(np.mean(error**2))),"bias_mcse_voters":float(error.std(ddof=1)/np.sqrt(len(error)))}
            if method=="hierarchical":
                covered=(truth>=b.p025)&(truth<=b.p975)
                row.update(coverage=float(covered.mean()),coverage_mcse=float(covered.std(ddof=1)/np.sqrt(len(covered))),
                           mean_interval_width_voters=float((b.p975-b.p025).mean()))
            detailed.append(row)
    pd.DataFrame(detailed).to_csv(output/"simulation_flow_summary.csv",index=False)
    # Replicates are the independent units for Monte Carlo errors, not the 20 correlated cells.
    metrics=pd.DataFrame(completed)
    summary=[]
    for (scenario,method,level),block in metrics.groupby(["scenario","method","level"]):
        for stratum in (["all","sparse","non_sparse"] if level=="place" else ["all"]):
            b=block if stratum=="all" else block[block["sparse"].eq(stratum=="sparse")]
            if b.empty:
                continue
            row={"scenario":scenario,"method":method,"level":level,"stratum":stratum,
                 "attempts":len(b),"replicates":int(b.replicate.nunique()),
                 "unavailable_fraction":float((~b.status.isin(["ok","diagnostic_warning"])).mean()),
                 "diagnostic_warning_fraction":float(b.status.eq("diagnostic_warning").mean())}
            for field in ["coverage","width_electorate_pp","mae_electorate_pp","rmse_electorate_pp",
                          "matrix_distance_to_truth","abstention_to_a_bias_electorate_pp","matrix_disagreement"]:
                if field in b:
                    # Average local places per replicate, then average independent replicates.
                    values=b.groupby("replicate")[field].mean().dropna()
                    row[field]=float(values.mean()) if len(values) else None
                    row[field+"_mcse"]=float(values.std(ddof=1)/np.sqrt(len(values))) if len(values)>1 else None
            summary.append(row)
    pd.DataFrame(summary).to_csv(output/"simulation_summary.csv",index=False)
    # Unequal electorate turnover is rejected before either new fit or likelihood.
    changed_y=np.array(y0);changed_y[0,0]+=1
    try:
        validate_counts(x0,changed_y,place0)
        rejection=False
    except ValueError:
        rejection=True
    write_json(output/"turnover_check.json",{"unequal_population_rejected":rejection,
               "equal_size_membership_turnover_identified":False,
               "conclusion":"Population closure remains an assumption; reject changes in totals, not hidden individual turnover."})
    return summary


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument("--replicates",type=int)
    parser.add_argument("--scenarios",nargs="+")
    parser.add_argument("--fit-only",action="store_true")
    args=parser.parse_args()
    simulate(args.output,args.replicates,args.scenarios,args.fit_only)
