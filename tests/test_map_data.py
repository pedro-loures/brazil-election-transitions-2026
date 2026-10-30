"""Audit generated map data against observed results, independently of models."""
import csv
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
MAPS=ROOT/"results/2026/flowcharts/data/maps"
pytestmark=pytest.mark.skipif(not (MAPS/"manifest.json").exists(),reason="Local map data has not been built")


def test_all_municipality_colors_match_full_observed_counts():
    with (ROOT/"results/2026/municipalities.csv").open() as stream:
        cities={str(int(row["municipality_code"])):row for row in csv.DictReader(stream)}
    data=json.loads((MAPS/"municipality.geojson").read_text())
    features=data["features"]
    assert len(features)==len(cities)==5571
    assert {f["properties"]["key"] for f in features}==set(cities)
    assert len({f["properties"]["ibge_code"] for f in features})==5571
    for f in features:
        p=f["properties"];row=cities[p["key"]]
        a1,a2,b1,b2=[int(float(row[key])) for key in ["a_1","a_2","b_1","b_2"]]
        assert p["delta_a"]==a2-a1
        assert p["delta_b"]==b2-b1
        assert p["margin_change"]==(a2-b2)-(a1-b1)
        assert p["uf"]==row["uf"]
        assert f["geometry"]["type"] in ["Polygon","MultiPolygon"]
        assert f["geometry"]["coordinates"]
    lebon=next(f["properties"] for f in features if f["properties"]["key"]=="81914")
    assert lebon["margin_change"]==604-236==368
    assert any(f["properties"]["key"]=="73709" for f in features)


def test_state_and_region_color_data_partition_domestic_totals():
    manifest=json.loads((MAPS/"manifest.json").read_text())
    assert manifest["unmatched_election_municipalities"]==0
    assert manifest["boundary_vintage"]==2025
    for level,expected in [("state",27),("region",5)]:
        features=json.loads((MAPS/f"{level}.geojson").read_text())["features"]
        assert len(features)==expected
        assert len({f["properties"]["key"] for f in features})==expected
        for field in ["a_1","a_2","b_1","b_2"]:
            assert sum(f["properties"][field] for f in features)==manifest["observed_totals"][field]
        for f in features:
            p=f["properties"]
            assert p["margin_change"]==p["delta_a"]-p["delta_b"]
            assert f["geometry"]["type"] in ["Polygon","MultiPolygon"]
