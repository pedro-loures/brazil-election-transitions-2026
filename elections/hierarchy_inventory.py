"""Freeze a geography audit and an outcome-blind, stratified pilot manifest."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .model import ORIGINS, DESTINATIONS

ROOT = Path(__file__).resolve().parents[1]
GROUP = ["uf", "municipality_code", "zone", "polling_place_1"]
REGIONS = {**dict.fromkeys("AC AP AM PA RO RR TO".split(), "N"),
           **dict.fromkeys("AL BA CE MA PB PE PI RN SE".split(), "NE"),
           **dict.fromkeys("DF GO MT MS".split(), "CO"),
           **dict.fromkeys("ES MG RJ SP".split(), "SE"),
           **dict.fromkeys("PR RS SC".split(), "S")}
DEFAULT_OUTPUT = ROOT / "results/2026/hierarchy_pilot"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))


def arrays(sections):
    x = sections[[g+"_1" for g in ORIGINS]].to_numpy(float)
    y = sections[[g+"_2" for g in DESTINATIONS]].to_numpy(float)
    keys = sections[GROUP].astype(str).agg(":".join, axis=1)
    labels, unique = pd.factorize(keys, sort=True)
    return x, y, labels, unique.tolist()


def design(x):
    z = x / x.sum(axis=1, keepdims=True)
    rank = int(np.linalg.matrix_rank(z))
    condition = float(np.linalg.cond(z)) if rank == 5 else None
    return rank, condition


def prepare(output=DEFAULT_OUTPUT, seed=20261030):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists():
        manifest = json.loads((output / "manifest.json").read_text())
        for path, digest in manifest["sources"].items():
            if sha256(ROOT/path) != digest:
                raise ValueError(f"Frozen input changed: {path}")
        return manifest
    source_paths = ["results/2026/sections.csv.gz", "results/2026/municipalities.csv",
                    "results/2026/estimated_flows.csv.gz", "results/2026/run.json",
                    "data/processed/2026/metadata.json", "data/raw/2026/manifest.json",
                    "docs/data/maps/municipality.geojson", "docs/data/maps/manifest.json"]
    sources = {path: sha256(ROOT/path) for path in source_paths}
    published = json.loads((ROOT/"datasets/manifest.json").read_text())
    verified = []
    for entry in published["files"]:
        if entry["restore_path"] in sources:
            if sources[entry["restore_path"]] != entry["sha256"]:
                raise ValueError(f"Baseline disagrees with published hash: {entry['restore_path']}")
            verified.append(entry["restore_path"])
    sections = pd.read_csv(ROOT/source_paths[0])
    eligible = sections.loc[sections.analysis_eligible].copy()
    if eligible.duplicated(["uf", "municipality_code", "zone", "section"]).any():
        raise ValueError("Section key is not unique")
    places = []
    all_groups = sections.groupby(GROUP).agg(sections_union=("section", "size"), electorate=("eligible_1", "sum"))
    for key, s in eligible.groupby(GROUP, sort=True):
        x = s[[g+"_1" for g in ORIGINS]].to_numpy(float)
        rank, condition = design(x)
        all_s = all_groups.loc[key]
        places.append(dict(zip(GROUP, key), sections=len(s), sections_union=int(all_s.sections_union),
                           electorate=int(x.sum()), electorate_coverage=float(x.sum()/all_s.electorate),
                           design_rank=rank, design_condition=condition,
                           **{f"origin_{g}": int(x[:,i].sum()) for i,g in enumerate(ORIGINS)}))
    # No second-round outcome or fitted flow is used for selection.
    inventory = pd.DataFrame(places)
    inventory.to_csv(output/"polling_place_inventory.csv.gz", index=False)
    cities = pd.read_csv(ROOT/source_paths[1])
    counts = inventory.groupby(["uf", "municipality_code"]).agg(
        places=("sections", "size"), sparse_places=("sections", lambda x: int((x<5).sum())),
        median_place_sections=("sections", "median"))
    cities = cities.merge(counts, on=["uf", "municipality_code"], how="left")
    cities["region"] = cities.uf.map(REGIONS)
    rng = np.random.default_rng(seed)
    chosen = []
    for region in ["N", "NE", "CO", "SE", "S"]:
        for lo, hi, label in [(15, 50, "small"), (65, 160, "medium")]:
            pool = cities[(cities.region == region) & cities.sections_analyzed.between(lo,hi)
                          & cities.design_rank.eq(5) & cities.places.ge(3)
                          & cities.municipality_code.ne(81914)].sort_values("municipality_code")
            chosen.append((int(pool.iloc[int(rng.integers(len(pool)))].municipality_code), region+"_"+label))
    chosen.append((81914, "thread_reference"))
    pool = cities[cities.sections_analyzed.between(250,450) & cities.design_rank.eq(5)
                  & ~cities.municipality_code.isin([v[0] for v in chosen])].sort_values("municipality_code")
    chosen.append((int(pool.iloc[int(rng.integers(len(pool)))].municipality_code), "large"))
    pilot = cities[cities.municipality_code.isin([v[0] for v in chosen])].copy()
    pilot["selection_stratum"] = pilot.municipality_code.map(dict(chosen))
    pilot_cols = ["uf", "municipality_code", "municipality", "region", "selection_stratum", "sections_union",
                  "sections_analyzed", "places", "sparse_places", "electorate_coverage", "design_rank", "design_condition"]
    pilot[pilot_cols].to_csv(output/"pilot_inventory.csv", index=False)
    eligible[eligible.municipality_code.isin(pilot.municipality_code)].to_csv(output/"pilot_sections.csv.gz", index=False)
    reuse = inventory.groupby(["uf", "municipality_code", "polling_place_1"]).zone.nunique()
    audit = {"domestic_section_union": len(sections), "retained_sections": len(eligible),
             "retained_place_groups": len(inventory), "place_section_quantiles": inventory.sections.quantile([0,.25,.5,.75,.9,.95,1]).to_dict(),
             "places_below_5_sections": int(inventory.sections.lt(5).sum()),
             "place_codes_reused_across_zones": int(reuse.gt(1).sum()),
             "matched_sections": int(sections.matched.sum()),
             "changed_electorate_sections": int((sections.matched & ~sections.stable_electorate).sum()),
             "changed_place_sections": int((sections.matched & ~sections.stable_place).sum()),
             "excluded_sections": int((~sections.analysis_eligible).sum()),
             "exclusion_counts_overlap": True,
             "limitations": ["Equal electorate counts do not establish identical voters.",
                            "Zone + place code defines an administrative group, not a verified physical building.",
                            "Aggregated-section individual membership is unavailable in these prepared inputs.",
                            "No verified polling-place coordinates: map only municipality polygons."]}
    write_json(output/"geography_audit.json", audit)
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "seed": seed,
                "sources": sources, "verified_published_baseline_files": verified,
                "pilot": pilot[pilot_cols].replace({np.nan:None}).to_dict("records"),
                "selection": "Seeded region x section-count strata using first-round design and eligibility only; includes thread and larger-city case. Not a nationally representative sample.",
                "group_key": GROUP, "origins": ORIGINS, "destinations": DESTINATIONS,
                "estimand": "expected closed-electorate transition counts, not reconstructed ballots",
                "variants": {"primary": {"mu_sd":2., "tau_scale":.5},
                             "tighter": {"mu_sd":2., "tau_scale":.25},
                             "wider": {"mu_sd":3., "tau_scale":1.}},
                "sampling": {"chains":4, "warmup":700, "samples":700, "target_accept":.95, "max_tree_depth":10},
                "simulation": {"replicates":30, "chains":2, "warmup":300, "samples":400,
                               "scenarios":["homogeneous", "moderate", "strong", "contextual", "within_place", "weak_design", "sparse", "boundary"],
                               "turnover": "Separate rejection test: unequal section populations must be rejected; equal-size membership turnover remains undetectable."},
                "warnings": {"matrix_distance":.05, "supported_origin_min_voters":100,
                             "supported_origin_max_rate_difference_pp":10.,
                             "key_flow_difference_electorate_pp":2., "sensitivity_electorate_pp":2.},
                "gate": {"max_rhat":1.01, "min_bulk_tail_ess":400, "max_divergences":0,
                         "min_simulation_replicates_per_scenario":100,
                         "min_simulation_coverage":.90, "max_rmse_ratio_to_baseline":1.10,
                         "max_failure_fraction":.05, "max_unresolved_material_disagreements":0,
                         "note": "30 replicates are an initial falsification screen, insufficient to certify coverage. Expansion requires >=100/scenario plus checks; no national fit on an exploratory screen alone."}}
    write_json(output/"manifest.json", manifest)
    return manifest
