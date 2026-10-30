"""Build a locally served, dependency-free municipality flow explorer."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from elections.aggregates import aggregate_records


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False))


def build(output, aggregates_only=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    data = output / "data"
    (data / "municipalities").mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "web" / "flowcharts").iterdir():
        if source.is_file():
            shutil.copyfile(source, output / source.name)
    results = ROOT / "results" / "2026"
    cities = pd.read_csv(results / "municipalities.csv")
    flow_rows = pd.read_csv(results / "estimated_flows.csv.gz")
    aggregate_dir = data / "aggregates"
    aggregate_dir.mkdir(exist_ok=True)
    aggregates = aggregate_records(cities, flow_rows)
    aggregate_index = []
    for name, record in aggregates.items():
        write_json(aggregate_dir / f"{name}.json", record)
        aggregate_index.append({**record["aggregate"], "file": name+".json"})
    write_json(aggregate_dir / "index.json", aggregate_index)
    if aggregates_only:
        shutil.copyfile(ROOT / "README.md", output / "methodology.md")
        result = {"output": str(output), "geographic_aggregates": len(aggregates)}
        print(json.dumps(result, indent=2))
        return result
    origins = ["a", "b", "other", "invalid", "abstention"]
    destinations = ["a", "b", "invalid", "abstention"]
    matrices = {}
    for (uf, code, model), group in flow_rows.groupby(["uf", "municipality_code", "model"]):
        model_data = {}
        for field, key in [("estimated_voters", "matrix"), ("bootstrap_p025", "low"), ("bootstrap_p975", "high")]:
            if group[field].notna().any():
                table = group.pivot(index="origin", columns="destination", values=field).reindex(index=origins, columns=destinations)
                model_data[key] = np.maximum(table.to_numpy(), 0).round(6).tolist()
        matrices.setdefault((uf, int(code)), {})[model] = model_data
    index = []
    for row in cities.to_dict("records"):
        # JSON nulls remain null; missing model quantities must not become zeros.
        row = {key: (None if pd.isna(value) else value) for key, value in row.items()}
        code = int(row["municipality_code"])
        row["municipality_code"] = code
        models = matrices.get((row["uf"], code), {})
        for model in models.values():
            matrix = np.array(model["matrix"])
            source_totals = np.array([row[f"analyzed_{key}_1"] for key in origins])
            destination_totals = np.array([row[f"analyzed_{key}_2"] for key in destinations])
            if not (np.allclose(matrix.sum(axis=1), source_totals, atol=1e-3)
                    and np.allclose(matrix.sum(axis=0), destination_totals, atol=1e-3)):
                raise ValueError(f"Flow margins do not reconcile for {code}")
        write_json(data / "municipalities" / f"{code}.json", {"city": row, "models": models})
        index.append({key: row[key] for key in ["uf", "municipality_code", "municipality", "model_status",
            "sections_analyzed", "sections_union", "electorate_coverage", "delta_a", "delta_b"]})
    write_json(data / "index.json", index)
    reference = {
        "label": "Twitter thread reference · Lebon Régis",
        "provenance": "Transcribed from the user-provided screenshots of posts 5–7, not re-estimated from the current TSE snapshot.",
        "matrix": [[2818, 0, 0, 81], [0, 3189, 0, 56], [13, 292, 57, 94],
                   [194, 0, 119, 0], [478, 0, 6, 1340]],
        "origins": [2899, 3245, 456, 313, 1824],
        "destinations": [3503, 3481, 182, 1571],
        "sections": 30, "eligible": 8737,
    }
    matrix = np.array(reference["matrix"])
    assert np.array_equal(matrix.sum(axis=1), reference["origins"])
    assert np.array_equal(matrix.sum(axis=0), reference["destinations"])
    write_json(data / "thread-reference.json", reference)
    write_json(data / "summary.json", json.loads((results / "summary.json").read_text()))
    shutil.copyfile(ROOT / "README.md", output / "methodology.md")
    # Provide existing computed outputs without copying multi-megabyte raw archives.
    for name in ["municipalities.csv", "estimated_flows.csv.gz", "reference_audit.csv"]:
        shutil.copyfile(results / name, output / name)
    result = {"output": str(output), "municipalities": len(index), "modeled": len(matrices),
              "thread_reference_conserves_votes": True, "geographic_aggregates": len(aggregates)}
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "results" / "2026" / "flowcharts"))
    parser.add_argument("--aggregates-only", action="store_true", help="Update aggregate data and page assets without rewriting municipal files")
    args = parser.parse_args()
    build(args.output, args.aggregates_only)
