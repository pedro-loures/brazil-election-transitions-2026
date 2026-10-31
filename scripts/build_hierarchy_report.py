"""Build an offline pilot map, paired comparison plots, and an honest scaling gate."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd

from elections.hierarchy_inventory import DEFAULT_OUTPUT, sha256, write_json


def evaluate_gate(folder):
    manifest=json.loads((folder/"manifest.json").read_text())
    city=pd.read_csv(folder/"municipal_comparison.csv")
    fits=pd.read_csv(folder/"fit_diagnostics.csv")
    simulation=pd.read_csv(folder/"simulation_summary.csv")
    reasons=[]
    primary=fits[fits.variant.eq("primary")]
    if primary.status.ne("ok").any():
        reasons.append(f"{int(primary.status.ne('ok').sum())}/{len(primary)} primary pilot fits fail the declared sampling diagnostics.")
    material=city.material_flag.astype(bool)
    if material.any():
        reasons.append(f"{int(material.sum())}/{len(city)} municipalities have material method disagreements unresolved by aggregate data.")
    prior=city.max_prior_sensitivity_electorate_pp.gt(manifest["warnings"]["sensitivity_electorate_pp"])
    if prior.any():
        reasons.append(f"{int(prior.sum())}/{len(city)} municipalities exceed the declared prior-sensitivity warning.")
    m=simulation[(simulation.method=="hierarchical")&(simulation.level=="municipality")]
    insufficient=m.replicates.lt(manifest["gate"]["min_simulation_replicates_per_scenario"])
    if insufficient.any():
        reasons.append("Initial 30-replicate simulation screen is insufficient to certify interval calibration; expansion requires at least 100 per relevant scenario.")
    low_coverage=m.coverage.lt(manifest["gate"]["min_simulation_coverage"])
    if low_coverage.any():
        reasons.append("Mean expected-flow interval coverage is below 90% in: "+", ".join(m.loc[low_coverage,"scenario"])+".")
    ratios=[]
    for row in m.itertuples():
        old=simulation[(simulation.method=="municipal_baseline")&(simulation.level=="municipality")&simulation.scenario.eq(row.scenario)].iloc[0]
        ratio=float(row.rmse_electorate_pp/old.rmse_electorate_pp)
        ratios.append({"scenario":row.scenario,"hierarchy_to_baseline_rmse_ratio":ratio})
    if any(r["hierarchy_to_baseline_rmse_ratio"]>1.1 for r in ratios):
        reasons.append("Hierarchical municipal RMSE exceeds 1.10 times the baseline in at least one scenario.")
    if m.unavailable_fraction.gt(.05).any():reasons.append("Simulation fit-unavailability exceeds 5% in at least one scenario.")
    verified=all(sha256(ROOT/path)==digest for path,digest in manifest["sources"].items())
    if not verified:reasons.append("Frozen input hash verification failed.")
    turnover=json.loads((folder/"turnover_check.json").read_text())
    if not turnover["unequal_population_rejected"]:reasons.append("Population mismatch rejection failed.")
    result={"status":"do_not_scale" if reasons else "eligible_for_expanded_validation",
            "national_hierarchical_run_performed":False,"reasons":reasons,"rmse_ratios":ratios,
            "baseline_hashes_unchanged":verified,
            "pilot_municipalities":len(city),"material_disagreements":int(material.sum()),
            "primary_diagnostic_warnings":int(primary.status.ne('ok').sum()),
            "interpretation":"This is a pilot decision, not proof that either model recovered individual ballots.",
            "next_decision":"Resolve model/coverage/sensitivity failures before spending resources on a national refit; increase simulation repetitions if the screen is otherwise adequate."}
    write_json(folder/"validation_gate.json",result)
    return result


def figures(folder):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    c=pd.read_csv(folder/"municipal_flow_comparison.csv")
    c=c[c.origin.eq("abstention")&c.destination.eq("a")]
    fig,axes=plt.subplots(1,3,figsize=(15,4))
    axes[0].hlines(c.hierarchical,c.baseline_p025,c.baseline_p975,alpha=.5)
    axes[0].vlines(c.baseline,c.hierarchical_p025,c.hierarchical_p975,alpha=.5)
    axes[0].scatter(c.baseline,c.hierarchical,alpha=.75)
    limit=max(c.baseline_p975.max(),c.hierarchical_p975.max())
    axes[0].plot([0,limit],[0,limit],color="gray",ls="--")
    axes[0].set(xlabel="Municipal baseline expected voters",ylabel="Hierarchical expected voters",title="Previous abstention → Lula")
    axes[1].scatter(c.common_electorate,c.difference_voters/c.common_electorate*100)
    axes[1].axhline(0,color="gray",ls="--")
    axes[1].set(xlabel="Common electorate",ylabel="Difference (% of electorate)",title="Size and disagreement")
    axes[2].hist(c.rate_difference_pp,bins=8)
    axes[2].set(xlabel="Origin-rate difference (percentage points)",ylabel="Municipalities",title="Method sensitivity")
    fig.suptitle("Expected flows; intervals are method-specific, not a formal agreement test")
    fig.tight_layout()
    fig.savefig(folder/"municipal_comparison.png",dpi=160)
    fig.savefig(folder/"municipal_comparison.pdf")
    plt.close(fig)


def build(folder=DEFAULT_OUTPUT):
    folder=Path(folder)
    gate=evaluate_gate(folder)
    flows=pd.read_csv(folder/"reliability.csv.gz")
    city=pd.read_csv(folder/"municipal_comparison.csv")
    comparison=pd.read_csv(folder/"municipal_flow_comparison.csv")
    simulation=pd.read_csv(folder/"simulation_summary.csv")
    audit=json.loads((folder/"geography_audit.json").read_text())
    manifest=json.loads((folder/"manifest.json").read_text())
    geo=json.loads((ROOT/"docs/data/maps/municipality.geojson").read_text())
    known_codes={int(f["properties"]["key"]) for f in geo["features"]}
    if not set(city.municipality_code)<=known_codes:raise ValueError("Unmatched pilot map keys")
    def records(frame):return json.loads(frame.to_json(orient="records",double_precision=10))
    confirmation=pd.read_csv(folder/"long_chain_confirmation.csv") if (folder/"long_chain_confirmation.csv").exists() else pd.DataFrame()
    payload={"flows":records(flows),"cities":records(city),"comparisons":records(comparison),
             "simulation":records(simulation),"confirmation":records(confirmation),"gate":gate,"geo":geo}
    configuration={"default_flow":{"origin":"abstention","destination":"a"},
                   "units":"counts or origin-conditional percentage points", "geography":"verified municipality polygons only",
                   "map_join":"TSE municipality code; pilot has zero unmatched codes",
                   "unfitted_geography":"gray, outside pilot; never zero",
                   "intervals":"pointwise method-specific; not simultaneous or independently comparable", "thresholds":manifest["warnings"]}
    write_json(folder/"visualization_config.json",configuration)
    write_json(folder/"visualization_data.json",{k:v for k,v in payload.items() if k!="geo"})
    script=(ROOT/"web/hierarchy/app.js").read_text()
    html=(ROOT/"web/hierarchy/template.html").read_text()
    data=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(",",":")).replace("</","<\\/")
    html=html.replace("/*__DATA__*/", "const DATA="+data+";").replace("/*__APP__*/",script)
    (folder/"report.html").write_text(html)
    figures(folder)
    m=simulation[(simulation.level=="municipality")&simulation.stratum.eq("all")]
    lines=["# Polling-place partial-pooling pilot: execution results", "", "Executed: 30 October 2026.", "",
           "**Decision: "+gate["status"].replace("_"," ")+".** The existing nationwide baseline is preserved. The new method was fitted only to the 12-municipality pilot.","",
           "## Findings and expansion decision", ""]
    lines += ["- "+reason for reason in gate["reasons"]]
    lines += ["", "A successful fit or similarity to the baseline does not establish hidden-flow recovery. Material disagreements remain unresolved rather than being called evidence for either method. The comparison changes likelihood, priors and expected-margin calibration as well as geographic pooling; disagreements cannot be attributed solely to adding polling places.", "",
              "## Geography and pilot", "",f"The audit retained {audit['retained_sections']:,} sections in {audit['retained_place_groups']:,} administrative place groups. It found {audit['place_codes_reused_across_zones']:,} municipality/place-code combinations reused across zones. The median group has four sections; {audit['places_below_5_sections']:,} have fewer than five. The experiment uses UF + municipality + zone + place code. Physical buildings and electorate membership were not independently verified.","",
              "| Municipality | Included sections | Places | Electorate coverage | Matrix distance | Max prior shift (% electorate) | Sampling | Investigation |",
              "|---|---:|---:|---:|---:|---:|---|---|"]
    for r in city.itertuples():
        lines.append(f"| {r.municipality} / {r.uf} | {r.sections_analyzed} / {r.sections_union} | {r.places} | {r.electorate_coverage:.1%} | {r.matrix_distance:.3f} | {r.max_prior_sensitivity_electorate_pp:.2f} | {r.status} | {r.investigation_status} |")
    lines += ["", "## Known-flow simulation screen", "",
              "Thirty repetitions per scenario use retained Lebon Régis first-round compositions and vary the transition process/nesting. Expected flows are the target; realized latent tables are retained separately. Counts, places, and cells within a repetition are dependent, so Monte Carlo standard errors are computed across repetitions. The 30-repetition screen can expose failures but cannot certify national calibration.","",
              "| Scenario | Method | RMSE (% electorate per cell) | 95% interval coverage | Coverage MCSE | Unavailable | Sampling warning fraction |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for r in m.itertuples():
        lines.append(f"| {r.scenario} | {r.method} | {r.rmse_electorate_pp:.3f} | {r.coverage:.1%} | {r.coverage_mcse:.1%} | {r.unavailable_fraction:.1%} | {r.diagnostic_warning_fraction:.1%} |")
    lines += ["", "Independent polling-place fits and sparse-place results, including all unavailable cases, are in `simulation_summary.csv`. Their ten-section/full-rank cutoff is an operational screen, not an identification theorem. No individual-level validation sample was available.", "",
              "The ninth, two-place scenario was added in a documented addendum before its outcomes were generated. It changes none of the original selection, priors or warning thresholds. The original screen has a short sampling budget and its warnings remain visible.", "",
              "### Longer-chain computational confirmation", "",
              "The first three datasets in each of the contextual, within-place and boundary scenarios were refitted after screening, using four chains, 1,000 warmup and 1,500 retained draws per chain with different MCMC seeds. These are the same data, not nine extra independent validation repetitions. They check whether the screening failures persist with better computational diagnostics.", "",
              "| Scenario | Datasets | Mean expected-flow coverage | Mean RMSE (% electorate/cell) | Fits passing diagnostics |",
              "|---|---:|---:|---:|---:|"]
    if not confirmation.empty:
        for scenario,b in confirmation.groupby("scenario"):
            lines.append(f"| {scenario} | {len(b)} | {b.coverage.mean():.1%} | {b.rmse_electorate_pp.mean():.3f} | {int(b.status.eq('ok').sum())}/{len(b)} |")
    lines += ["", "These targeted refits support a computational diagnosis, not a precise coverage estimate or a national validation claim. Their parameter diagnostics and protocol are in `confirmation/`; summary data are in `long_chain_confirmation.csv`.", "",
              "## What was delivered", "",
              "- `report.html`: offline municipality map with estimate/reliability color controls, municipal → place table, both methods' intervals, municipal disagreements and investigation notes, scatter/difference/distribution views, simulation evidence.",
              "- `reliability.csv.gz`: expected flows, pointwise intervals and widths, denominators, data coverage, information warnings, prior sensitivity, heterogeneity and sampling diagnostics; local and municipal levels.",
              "- `municipal_flow_comparison.csv`, `municipal_comparison.csv`: paired common-electorate comparison and flags. Inputs agree exactly; expected destination calibration differs by model. No interval-overlap agreement test is claimed.",
              "- `municipal_investigations.json`: each municipality's alignment, design, boundary, sensitivity, variant diagnostics and largest descriptive local contributions. These are not leave-one-place-out causal or influence estimates.",
              "- `fits/`: posterior parameter/local/municipal draws and parameter diagnostics for three prior variants per municipality.",
              "- `simulation_metrics.csv`, `simulation_summary.csv`, `simulation_flow_summary.csv`, `simulation_flows.csv.gz`, `simulations/`: reproducible replicate and flow-level known-truth results, sparse strata, failures, Monte Carlo errors and runtime.",
              "- `manifest.json`, `run.json`, `validation_gate.json`, `geography_audit.json`, `likelihood_audit.json`, `prior_predictive.json`: frozen provenance/configuration and diagnostic evidence.",
              "- `visualization_data.json`, `visualization_config.json`, `municipal_comparison.png/.pdf`: reviewable data and standalone figures.", "",
              "## Limitations and next changes", "",
              "The normal margin likelihood is an approximation. Exact small-count checks show meaningful errors; binary projection checks at larger counts do not establish accuracy of the full posterior. Expected flow intervals are conditional on this approximation, priors, grouping, and population closure. Tight intervals can be driven by assumptions. Structural zeros may need explicit prior mass or a different interval/decision formulation. Contextual and within-place misspecification require further model development or narrower claims. A second simulation design is needed to assess transfer beyond Lebon Régis. Scaling is withheld under the agreed validation gate.", "",
              "See [statistical specification](docs/hierarchy_specification.md) and [academic review](LITERATURE_REVIEW.md) in the project root. The [Wakefield et al. (2011) convolution/approximation comparison](https://doi.org/10.1002/sim.4214) motivates explicit likelihood checks; [Morris et al. (2019)](https://doi.org/10.1002/sim.8086) motivates known-truth evaluation with Monte Carlo error. These sources support the workflow, not a claim that this pilot is validated.","",
              "## Reproducibility checks", "",f"Frozen source hashes unchanged: **{gate['baseline_hashes_unchanged']}**. All pilot municipality map codes match existing verified geography. Draw-by-draw municipal aggregation is checked during export. The Python tests and browser checks are recorded in the execution handoff."]
    (ROOT/"HIERARCHY_PILOT_RESULTS.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(gate,indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    build(p.parse_args().output)
