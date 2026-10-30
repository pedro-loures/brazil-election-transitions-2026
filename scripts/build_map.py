"""Join official TSE/IBGE codes and build local, observed-result choropleths.

Inputs are cached official files under data/raw/geography. Geometry libraries are
build-time only (requirements-map.txt); the browser has no external dependencies.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REGIONS = {"N": "north", "NE": "northeast", "SE": "southeast", "S": "south", "CO": "central-west"}
COUNTS = ("a_1", "a_2", "b_1", "b_2")


def observed_properties(rows, key, name, **metadata):
    counts = {field: sum(int(float(row[field])) for row in rows) for field in COUNTS}
    da, db = counts["a_2"] - counts["a_1"], counts["b_2"] - counts["b_1"]
    return {"key": str(key), "name": name, **metadata, **counts,
            "delta_a": da, "delta_b": db, "margin_change": da - db}


def code_crosswalk(config):
    result = {}
    for state in config["abr"]:
        uf = state["cd"].upper()
        if uf == "ZZ":
            continue
        for city in state["mu"]:
            key = (uf, int(city["cd"]))
            if key in result:
                raise ValueError(f"Duplicate municipality in TSE crosswalk: {key}")
            result[key] = str(city["cdi"])
    if len(set(result.values())) != len(result):
        raise ValueError("IBGE codes must be unique in the domestic TSE crosswalk")
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False))


def build(raw, output, tolerance=.008):
    import numpy as np
    import shapefile
    import shapely
    from shapely.geometry import shape, mapping

    raw, output = Path(raw), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    crosswalk = code_crosswalk(json.loads((raw / "tse.json").read_text()))
    with (ROOT / "results/2026/municipalities.csv").open() as stream:
        cities = list(csv.DictReader(stream))
    by_ibge = {}
    for row in cities:
        code = crosswalk[(row["uf"], int(row["municipality_code"]))]
        if code in by_ibge:
            raise ValueError(f"Duplicate official join: {code}")
        by_ibge[code] = row
    archive = raw / "BR_Municipios_2025.zip"
    geometries, records = [], []
    print("Reading official 2025 SIRGAS 2000 geographic boundaries", flush=True)
    with zipfile.ZipFile(archive) as z:
        reader = shapefile.Reader(shp=z.open("BR_Municipios_2025.shp"),
                                  shx=z.open("BR_Municipios_2025.shx"),
                                  dbf=z.open("BR_Municipios_2025.dbf"), encoding="utf-8")
        for entry in reader.iterShapeRecords():
            record = entry.record.as_dict()
            geometry = shape(entry.shape.__geo_interface__)
            if not geometry.is_valid:
                geometry = shapely.make_valid(geometry)
            records.append(record)
            geometries.append(geometry)
    codes = [record["CD_MUN"] for record in records]
    missing = set(by_ibge) - set(codes)
    if missing or len(codes) != len(set(codes)):
        raise ValueError(f"Boundary join is incomplete or duplicated: {sorted(missing)}")
    geoms = np.array(geometries, dtype=object)
    print(f"Simplifying {len(geoms)} polygons with shared boundaries", flush=True)
    # Coverage simplification preserves shared boundaries across municipalities.
    simplified = shapely.coverage_simplify(geoms, tolerance, simplify_boundary=True)
    # Round on a topology-aware precision grid before dissolving. Text-level
    # rounding of dissolved coordinates can introduce invalid touching rings.
    simplified = shapely.set_precision(simplified, grid_size=.000001)
    if not np.all(shapely.is_valid(simplified)):
        raise ValueError("Simplification produced invalid polygons")
    collections = {level: {"type": "FeatureCollection", "features": []} for level in ["municipality", "state", "region"]}
    for record, geometry in zip(records, simplified):
        code = record["CD_MUN"]
        if code not in by_ibge:
            continue  # The two operational water-body units have no election totals.
        row = by_ibge[code]
        if row["uf"] != record["SIGLA_UF"]:
            raise ValueError(f"UF disagreement for IBGE {code}")
        p = observed_properties([row], int(row["municipality_code"]), f'{record["NM_MUN"]} · {row["uf"]}',
                                uf=row["uf"], ibge_code=code, region=REGIONS[record["SIGLA_RG"]])
        collections["municipality"]["features"].append({"type": "Feature", "properties": p, "geometry": mapping(geometry)})
    print("Dissolving state and region boundaries", flush=True)
    for level, field in [("state", "SIGLA_UF"), ("region", "SIGLA_RG")]:
        for code in sorted({r[field] for r in records}):
            members = [i for i, r in enumerate(records) if r[field] == code]
            subset = [by_ibge[records[i]["CD_MUN"]] for i in members if records[i]["CD_MUN"] in by_ibge]
            name = records[members[0]]["NM_UF" if level == "state" else "NM_REGIAO"]
            key = code if level == "state" else REGIONS[code]
            # Robust union also includes the operational water units in outlines.
            geometry = shapely.union_all(simplified[members])
            if not geometry.is_valid or geometry.is_empty:
                raise ValueError(f"Invalid aggregate geometry: {key}")
            p = observed_properties(subset, key, name, **({"uf": code} if level == "state" else {}))
            collections[level]["features"].append({"type": "Feature", "properties": p, "geometry": mapping(geometry)})
    for level, data in collections.items():
        data["features"].sort(key=lambda f: f["properties"]["key"])
        write_json(output / f"{level}.geojson", data)
    totals = {field: sum(int(float(row[field])) for row in cities) for field in COUNTS}
    for data in collections.values():
        for field in [*COUNTS, "delta_a", "delta_b", "margin_change"]:
            expected = observed_properties(cities, "BR", "Brazil")[field]
            if sum(f["properties"][field] for f in data["features"]) != expected:
                raise ValueError(f"Geographic totals do not conserve {field}")
    urls = json.loads((raw / "urls.json").read_text())
    manifest = {"boundary_vintage": 2025, "coordinate_system": "SIRGAS 2000 geographic degrees",
                "projection": "Mercator for display only", "simplification": "Shapely coverage_simplify with shared boundaries",
                "tolerance_degrees": tolerance, "metric": "(a_2 - a_1) - (b_2 - b_1), full observed vote counts",
                "precision_grid_degrees": .000001,
                "join": "Official TSE municipality cd to IBGE cdi; no name matching",
                "counts": {level: len(data["features"]) for level, data in collections.items()},
                "unmatched_election_municipalities": 0, "observed_totals": totals,
                "excluded_mesh_units": [r["CD_MUN"] for r in records if r["CD_MUN"] not in by_ibge],
                "sources": [{"url": urls["tse"], "sha256": hashlib.sha256((raw / "tse.json").read_bytes()).hexdigest()},
                            {"url": urls["municipality_2025"], "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}]}
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"output": str(output), **manifest["counts"], "unmatched": 0}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default=str(ROOT / "data/raw/geography"))
    parser.add_argument("--output", default=str(ROOT / "results/2026/flowcharts/data/maps"))
    parser.add_argument("--tolerance", type=float, default=.008)
    args = parser.parse_args()
    build(args.raw, args.output, args.tolerance)
