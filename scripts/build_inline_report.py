"""Pack the computed municipality results into a conversation-sized view."""
import argparse
import json
from pathlib import Path

import pandas as pd


def build(template, target):
    base = Path(__file__).resolve().parents[1] / "results" / "2026"
    cities = pd.read_csv(base / "municipalities.csv")
    flows = pd.read_csv(base / "estimated_flows.csv.gz")
    flows = flows[flows.model.eq("full")].pivot(
        index=["uf", "municipality_code"], columns=["origin", "destination"], values="estimated_voters")
    rows = []
    for r in cities.itertuples():
        key = r.uf, r.municipality_code
        point = None
        if key in flows.index:
            p = flows.loc[key]
            point = [p["other", "a"], p["invalid", "a"], p["abstention", "a"],
                     p["a", "invalid"] + p["a", "abstention"], p["b", "a"] - p["a", "b"],
                     p["other", "b"], p["invalid", "b"], p["abstention", "b"],
                     p["b", "invalid"] + p["b", "abstention"]]
            point = [round(v) for v in point]
        row = [r.uf, int(r.municipality_code), r.municipality,
               *[int(getattr(r, c)) for c in ["a_1", "a_2", "b_1", "b_2", "other_1",
                   "delta_turnout", "delta_invalid", "sections_union", "sections_analyzed"]],
               round(r.electorate_coverage * 1000),
               *[round(getattr(r, c) * 1000) if pd.notna(getattr(r, c)) else None
                 for c in ["corr_a_net_new_valid", "corr_b_net_new_valid"]],
               int(r.analyzed_a_2-r.analyzed_a_1), int(r.analyzed_b_2-r.analyzed_b_1),
               round(r.full_rmse_votes * 10) if pd.notna(r.full_rmse_votes) else None,
               int(r.bootstrap_successful) if pd.notna(r.bootstrap_successful) else None, point]
        rows.append(row)
    data = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    source = Path(template).read_text()
    if source.count("__MUNICIPAL_DATA__") != 1:
        raise ValueError("Template must contain one data placeholder")
    fragment = source.replace("__MUNICIPAL_DATA__", data)
    if len(fragment.encode()) >= 1_000_000:
        raise ValueError(f"Inline view exceeds 1 MB: {len(fragment.encode())}")
    Path(target).write_text(fragment)
    print(json.dumps({"municipalities": len(rows), "bytes": len(fragment.encode()), "file": target}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("template")
    parser.add_argument("output")
    args = parser.parse_args()
    build(args.template, args.output)
