import numpy as np
import pandas as pd
import pytest
from scipy.optimize import linprog

from elections.analysis import paired_sections, city_statistics
from elections.model import fit_transition, model_city


def section(round_, a, b, other, invalid, absent, **extra):
    n = a+b+other+invalid+absent
    return {"uf": "SC", "municipality_code": 81914, "municipality": "LEBON RÉGIS",
            "zone": 77, "section": 1, "round": round_, "polling_place": 1001,
            "a": a, "b": b, "other": other, "invalid": invalid, "abstention": absent,
            "eligible": n, "turnout": n-absent, "valid": a+b+other,
            "section_usable": True, **extra}


def test_accounting_does_not_imply_mobilization():
    # 30 A gains can include 20 B->A switches + 10 other->A; zero mobilization.
    p = paired_sections(pd.DataFrame([
        section(1, 100, 100, 10, 30, 60), section(2, 130, 80, 0, 30, 60)]))
    r = p.iloc[0]
    assert r.accounting_residual == 0
    assert r.a_mobilization_lower == 0
    assert r.a_lower_if_no_cross == 20
    assert r.a_mobilization_upper == 90


def test_net_turnout_does_not_measure_gross_arrivals():
    # Thread's displayed gross arrivals (484) - departures (231) = 253.
    p = paired_sections(pd.DataFrame([
        section(1, 2899, 3245, 456, 313, 1824),
        section(2, 3503, 3481, 0, 182, 1571)]))
    assert p.iloc[0].delta_turnout == 253
    assert p.iloc[0].accounting_residual == 0
    assert 484-231 == 253


def test_unmatched_and_changed_electorates_are_not_imputed():
    d = pd.DataFrame([
        section(1, 100, 100, 10, 30, 60),
        section(2, 130, 81, 0, 30, 60),  # +1 eligible
        section(1, 90, 100, 20, 30, 60, section=2)])
    p = paired_sections(d)
    assert len(p) == 2
    assert p.analysis_eligible.sum() == 0
    assert city_statistics(p)["sections_excluded"] == 2


def test_changed_polling_place_is_flagged():
    p = paired_sections(pd.DataFrame([
        section(1, 100, 100, 10, 30, 60),
        section(2, 130, 80, 0, 30, 60, polling_place=1002)]))
    assert not p.iloc[0].analysis_eligible


def test_declining_valid_votes_do_not_receive_new_voter_hypothesis():
    p = paired_sections(pd.DataFrame([
        section(1, 100, 100, 10, 30, 60), section(2, 95, 100, 0, 30, 75)]))
    assert not p.iloc[0].proportional_testable


def test_mobilization_bounds_are_sharp_against_linear_programming():
    rng = np.random.default_rng(19)
    for _ in range(12):
        table = rng.integers(0, 20, (5, 4))
        x, y = table.sum(axis=1), table.sum(axis=0)
        eq, rhs = [], []
        for i in range(5):
            row = np.zeros((5, 4)); row[i, :] = 1
            eq.append(row.ravel()); rhs.append(x[i])
        for j in range(3):
            row = np.zeros((5, 4)); row[:, j] = 1
            eq.append(row.ravel()); rhs.append(y[j])
        cost = np.zeros((5, 4)); cost[3:, 0] = 1
        low = linprog(cost.ravel(), A_eq=eq, b_eq=rhs, bounds=(0, None), method="highs")
        high = linprog(-cost.ravel(), A_eq=eq, b_eq=rhs, bounds=(0, None), method="highs")
        assert low.success and high.success
        assert low.fun == pytest.approx(max(0, y[0]-x[:3].sum()))
        assert -high.fun == pytest.approx(min(y[0], x[3:].sum()))


def synthetic_counts():
    rng = np.random.default_rng(17)
    x = rng.integers(10, 150, (40, 5)).astype(float)
    p = np.array([[.91, .02, .02, .05], [.03, .9, .02, .05],
                  [.3, .5, .1, .1], [.4, .2, .3, .1], [.25, .15, .05, .55]])
    return x, x @ p, p


def test_model_recovers_identified_synthetic_rates_and_margins():
    x, y, true = synthetic_counts()
    fit = fit_transition(x, y)
    assert fit["status"] == "ok"
    assert np.allclose(fit["p"], true, atol=1e-4)
    assert np.allclose(fit["p"].sum(axis=1), 1)
    assert np.all(fit["p"] >= -1e-7)
    assert np.allclose(fit["flows"].sum(axis=0), y.sum(axis=0), atol=1e-4)
    assert np.allclose(fit["flows"].sum(axis=1), x.sum(axis=0), atol=1e-4)


def test_model_sensitivity_allows_comparison_to_no_switch_assumption():
    x, y, _ = synthetic_counts()
    fit = fit_transition(x, y, no_cross=True)
    assert fit["status"] == "ok"
    assert abs(fit["p"][0, 1]) < 1e-7
    assert abs(fit["p"][1, 0]) < 1e-7
    assert fit["rmse_votes"] > .1


def test_incompatible_electorates_raise_instead_of_forcing_a_fit():
    x, y, _ = synthetic_counts(); y[0, 0] += 1
    with pytest.raises(ValueError, match="equal section electorates"):
        fit_transition(x, y)


def test_small_or_rank_deficient_cities_are_explicit():
    x, y, _ = synthetic_counts()
    result, flows = model_city(("SC", 81914, x[:4], y[:4], 0, 1, 10))
    assert result["model_status"] == "too_few_sections" and not flows
    x = np.tile(x[0], (20, 1)); y = np.tile(y[0], (20, 1))
    result, flows = model_city(("SC", 81914, x, y, 0, 1, 10))
    assert result["model_status"] == "rank_deficient" and not flows


def test_bootstrap_is_reproducible_and_labels_model_dependence():
    x, y, _ = synthetic_counts()
    task = ("SC", 81914, x, y, 5, 110, 10)
    first, flows1 = model_city(task)
    second, flows2 = model_city(task)
    assert first == second
    assert flows1 == flows2
    assert first["bootstrap_successful"] == 5
    assert any("bootstrap_p025" in row for row in flows1)
