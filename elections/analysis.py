from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
import scipy

from .data import KEY
from .model import model_city, ORIGINS, DESTINATIONS

CITY = ["uf", "municipality_code"]
COUNTS = ["a", "b", "other", "invalid", "eligible", "turnout", "abstention", "valid"]


def paired_sections(rounds):
    d1 = rounds[rounds["round"].eq(1)].drop(columns="round")
    d2 = rounds[rounds["round"].eq(2)].drop(columns="round")
    p = d1.merge(d2, on=KEY, suffixes=("_1", "_2"), how="outer", validate="one_to_one", indicator=True)
    p["matched"] = p._merge.eq("both")
    p["stable_electorate"] = p.eligible_1.eq(p.eligible_2)
    p["stable_place"] = p.polling_place_1.eq(p.polling_place_2)
    p["analysis_eligible"] = (p.matched & p.stable_electorate & p.stable_place
                              & p.section_usable_1.fillna(False).astype(bool)
                              & p.section_usable_2.fillna(False).astype(bool)
                              & p.eligible_1.gt(0) & p.other_2.eq(0))
    for col in ["a", "b", "turnout", "invalid", "valid", "abstention"]:
        p[f"delta_{col}"] = p[f"{col}_2"] - p[f"{col}_1"]
    p["net_new_valid"] = p.delta_turnout - p.delta_invalid
    p["accounting_residual"] = p.delta_a + p.delta_b - p.other_1 - p.net_new_valid
    for label, opposite in [("a", "b"), ("b", "a")]:
        # Sharp bounds on gross flows from invalid/abstention, unrestricted switching.
        p[f"{label}_mobilization_lower"] = (p[f"{label}_2"] - p.valid_1).clip(lower=0)
        p[f"{label}_mobilization_upper"] = np.minimum(p[f"{label}_2"], p.invalid_1 + p.abstention_1)
        p[f"{label}_lower_if_no_cross"] = (p[f"delta_{label}"] - p.other_1).clip(lower=0)
    p["no_cross_section_feasible"] = (p.a_2.le(p.eligible_1-p.b_1)
                                       & p.b_2.le(p.eligible_1-p.a_1))
    share = p.a_1 / (p.a_1 + p.b_1).replace(0, np.nan)
    p["proportional_required_other_a"] = p.delta_a - share * p.net_new_valid
    p["proportional_testable"] = p.analysis_eligible & share.notna() & p.net_new_valid.ge(0)
    p["proportional_joint_assumptions_infeasible"] = p.proportional_testable & (
        p.proportional_required_other_a.lt(-1e-8)
        | p.proportional_required_other_a.gt(p.other_1 + 1e-8))
    return p.drop(columns="_merge")


def correlation(a, b):
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def city_statistics(p):
    s = p[p.analysis_eligible]
    row = {"sections_union": len(p), "sections_matched": int(p.matched.sum()),
           "sections_analyzed": len(s), "sections_excluded": int((~p.analysis_eligible).sum()),
           "sections_electorate_changed": int((p.matched & ~p.stable_electorate).sum()),
           "sections_place_changed": int((p.matched & ~p.stable_place).sum()),
           "electorate_coverage": float(s.eligible_1.sum() / p.eligible_1.sum()) if p.eligible_1.sum() else np.nan,
           "corr_a_net_new_valid": correlation(s.net_new_valid, s.delta_a),
           "corr_b_net_new_valid": correlation(s.net_new_valid, s.delta_b),
           "accounting_failures": int(s.accounting_residual.ne(0).sum()),
           "no_cross_section_infeasible": int((~s.no_cross_section_feasible).sum()),
           "proportional_testable_sections": int(s.proportional_testable.sum()),
           "proportional_infeasible_sections": int(s.proportional_joint_assumptions_infeasible.sum()),
           "net_valid_declined_sections": int(s.net_new_valid.lt(0).sum())}
    for label in ["a", "b"]:
        row[f"{label}_gain_sections"] = int(s[f"delta_{label}"].gt(0).sum())
        row[f"{label}_loss_sections"] = int(s[f"delta_{label}"].lt(0).sum())
        row[f"{label}_gain_exceeds_other_sections"] = int(s[f"delta_{label}"].gt(s.other_1).sum())
        for bound in ["mobilization_lower", "mobilization_upper", "lower_if_no_cross"]:
            row[f"{label}_{bound}"] = float(s[f"{label}_{bound}"].sum())
    for turn in [1, 2]:
        for col in COUNTS:
            row[f"analyzed_{col}_{turn}"] = float(s[f"{col}_{turn}"].sum())
    return row


def analyze(processed, output, bootstrap=150, workers=4, seed=20261029, min_sections=10, only=None):
    processed, output = Path(processed), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((processed / "metadata.json").read_text())
    rounds = pd.read_csv(processed / "section_rounds.csv.gz")
    rounds = rounds[rounds.uf.ne("ZZ")].copy()
    if only is not None:
        rounds = rounds[rounds.municipality_code.isin(only)]
    pairs = paired_sections(rounds)
    pairs.to_csv(output / "sections.csv.gz", index=False)
    totals = rounds.groupby(CITY + ["round"])[COUNTS].sum().unstack("round")
    totals.columns = [f"{col}_{int(t)}" for col, t in totals.columns]
    totals = totals.reset_index()
    names = rounds[CITY + ["municipality"]].drop_duplicates(CITY)
    stats, tasks = [], []
    for (uf, code), p in pairs.groupby(CITY, sort=True):
        stats.append({"uf": uf, "municipality_code": code, **city_statistics(p)})
        s = p[p.analysis_eligible]
        x = s[[f"{c}_1" for c in ORIGINS]].to_numpy(float)
        y = s[[f"{c}_2" for c in DESTINATIONS]].to_numpy(float)
        tasks.append((uf, code, x, y, bootstrap, seed, min_sections))
    cities = totals.merge(names, on=CITY).merge(pd.DataFrame(stats), on=CITY)
    for label in ["a", "b", "turnout", "invalid", "valid", "abstention", "eligible"]:
        cities[f"delta_{label}"] = cities[f"{label}_2"] - cities[f"{label}_1"]
    cities["winner_1"] = np.where(cities.a_1.gt(cities.b_1), "a", np.where(cities.a_1.eq(cities.b_1), "tie", "b"))
    cities["winner_2"] = np.where(cities.a_2.gt(cities.b_2), "a", np.where(cities.a_2.eq(cities.b_2), "tie", "b"))
    cities["winner_changed"] = cities.winner_1.ne(cities.winner_2)
    reference = pd.read_csv(processed / "municipal_reference.csv")
    audit = rounds.groupby(CITY + ["round"], as_index=False)[
        ["eligible", "turnout", "abstention", "blank", "null", "valid"]].sum()
    audit = audit.merge(reference, on=CITY + ["round"], suffixes=("_sections", "_reference"), how="left", indicator=True)
    audit["reference_present"] = audit._merge.eq("both")
    for col in ["eligible", "turnout", "abstention", "blank", "null", "valid"]:
        audit[f"difference_{col}"] = audit[f"{col}_sections"] - audit[f"{col}_reference"]
    audit["all_totals_match"] = audit.filter(regex="^difference_").eq(0).all(axis=1) & audit.reference_present
    audit.drop(columns="_merge").to_csv(output / "reference_audit.csv", index=False)
    checks = audit.groupby(CITY).all_totals_match.all().rename("reference_all_totals_match").reset_index()
    cities = cities.merge(checks, on=CITY)
    cities.to_csv(output / "municipalities.csv", index=False)

    diagnostics, flows = [], []
    print(f"Analyzing {len(cities):,} municipalities; {bootstrap} bootstrap draws; {workers} workers", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, (diagnostic, flow_rows) in enumerate(pool.map(model_city, tasks, chunksize=4), 1):
            diagnostics.append(diagnostic)
            flows.extend(flow_rows)
            if i % 100 == 0:
                print(f"Models completed: {i:,}/{len(cities):,}", flush=True)
    cities = cities.merge(pd.DataFrame(diagnostics), on=CITY)
    cities.to_csv(output / "municipalities.csv", index=False)
    flow_columns = ["uf", "municipality_code", "model", "origin", "destination", "rate", "estimated_voters",
                    "bootstrap_p025", "bootstrap_median", "bootstrap_p975"]
    pd.DataFrame(flows).reindex(columns=flow_columns).to_csv(output / "estimated_flows.csv.gz", index=False)

    valid_places = pairs[pairs.analysis_eligible].copy()
    place_counts = [f"{c}_{t}" for c in COUNTS for t in [1, 2]]
    places = valid_places.groupby(CITY + ["polling_place_1"], as_index=False)[place_counts].sum()
    places.to_csv(output / "polling_places.csv.gz", index=False)
    metadata.update({"analysis_utc": datetime.now(timezone.utc).isoformat(), "bootstrap": bootstrap,
                     "seed": seed, "min_model_sections": min_sections,
                     "municipalities": len(cities), "domestic_section_union": len(pairs),
                     "analyzed_sections": int(pairs.analysis_eligible.sum()),
                     "model_status_counts": cities.model_status.value_counts().to_dict(),
                     "logs_status": "not_loaded", "model": "common-transition constrained least squares; not an exact reconstruction of thread"})
    metadata["software"] = {"python": platform.python_version(), "numpy": np.__version__,
                            "pandas": pd.__version__, "scipy": scipy.__version__}
    (output / "run.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    from .report import write_report
    write_report(cities, pd.DataFrame(flows), pairs, metadata, output)
    return metadata
