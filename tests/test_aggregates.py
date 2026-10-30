import numpy as np
import pandas as pd
import pytest

from elections.aggregates import aggregate_records, COUNT_FIELDS, REGIONS, STATES
from elections.model import ORIGINS, DESTINATIONS

MATRIX = np.array([[10, 1, 0, 1], [2, 10, 1, 0], [3, 2, 1, 0], [1, 1, 2, 0], [2, 1, 0, 3]], float)


def city(uf, code, multiplier=1):
    matrix = MATRIX * multiplier
    source, target = matrix.sum(axis=1), matrix.sum(axis=0)
    row = {"uf": uf, "municipality_code": code, "municipality": str(code), "sections_union": 10, "sections_analyzed": 10}
    for key, value in zip(ORIGINS, source):
        row[key+"_1"] = value
    for key, value in zip(DESTINATIONS, target):
        row[key+"_2"] = value
    row["other_2"] = 0
    for turn in [1, 2]:
        row[f"eligible_{turn}"] = matrix.sum()
        row[f"turnout_{turn}"] = matrix.sum()-row[f"abstention_{turn}"]
        row[f"valid_{turn}"] = row[f"a_{turn}"]+row[f"b_{turn}"]+row[f"other_{turn}"]
    row.update({"analyzed_"+key: row[key] for key in COUNT_FIELDS})
    return row


def flows(uf, code, multiplier=1):
    return [{"uf": uf, "municipality_code": code, "model": "full", "origin": source,
             "destination": target, "estimated_voters": float(MATRIX[i, j]*multiplier)}
            for i, source in enumerate(ORIGINS) for j, target in enumerate(DESTINATIONS)]


def test_geographic_membership_is_a_partition():
    members = [uf for _, ufs in REGIONS.values() for uf in ufs]
    assert len(members) == len(set(members)) == 27
    assert set(members) == set(STATES)
    assert "MG" in REGIONS["southeast"][1]
    assert len(REGIONS["northeast"][1]) == 9


def test_aggregates_keep_unmodeled_cities_in_observed_totals_only():
    cities = pd.DataFrame([city("MG", 1), city("MG", 2, 2), city("BA", 3, 2)])
    records = aggregate_records(cities, pd.DataFrame(flows("MG", 1)+flows("BA", 3, 2)))
    mg = records["state-MG"]
    assert mg["aggregate"]["municipalities_total"] == 2
    assert mg["models"]["full"]["coverage"]["municipalities_modeled"] == 1
    assert mg["models"]["full"]["coverage"]["electorate_coverage"] == pytest.approx(1/3)
    assert mg["city"]["eligible_1"] == 3*MATRIX.sum()
    np.testing.assert_array_equal(mg["models"]["full"]["matrix"], MATRIX)
    np.testing.assert_array_equal(records["region-northeast"]["models"]["full"]["matrix"], MATRIX*2)
    np.testing.assert_array_equal(records["country-BR"]["models"]["full"]["matrix"], MATRIX*3)
    full = records["country-BR"]["models"]["full"]
    assert full["coverage"]["electorate_coverage"] == pytest.approx(.6)
    assert full["coverage"]["sections_analyzed"] == 20
    assert "low" not in full and "high" not in full


def test_no_fitted_cities_produces_no_matrix_in_that_state():
    records = aggregate_records(pd.DataFrame([city("MG", 1), city("BA", 3)]), pd.DataFrame(flows("BA", 3)))
    assert records["state-MG"]["models"] == {}
    assert records["state-MG"]["city"]["eligible_1"] == MATRIX.sum()


def test_aggregate_reconciliation_rejects_inconsistent_model_margins():
    row = city("MG", 1)
    row["analyzed_a_2"] += 10
    with pytest.raises(ValueError, match="margins do not reconcile"):
        aggregate_records(pd.DataFrame([row]), pd.DataFrame(flows("MG", 1)))
