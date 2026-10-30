"""Compare the saved municipal experiment with the user-supplied screenshots.

Thread figures below are a manual transcription, not independently observed
individual transitions. Counterfactual fits never overwrite official inputs.
"""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from elections.analysis import paired_sections
from elections.model import ORIGINS, DESTINATIONS, fit_transition

CODE = 81914
THREAD_FLOW = np.array([
    [2818, 0, 0, 81],
    [0, 3189, 0, 56],
    [13, 292, 57, 94],
    [194, 0, 119, 0],
    [478, 0, 6, 1340],
], dtype=float)
LABELS = {"a": "Lula", "b": "Flávio", "other": "Other candidates",
          "invalid": "Blank/null", "abstention": "Abstention"}


def unweighted_fit(x, y):
    """Same probability/margin constraints as baseline; loss uses equal count weights."""
    assert np.allclose(x.sum(1), y.sum(1))
    gram, cross = x.T @ x / len(x), x.T @ y / len(x)
    eq = np.zeros((8, 20))
    for i in range(5):
        eq[i, i*4:(i+1)*4] = 1
    for j in range(3):
        eq[5+j, j::4] = x.sum(0) / x.sum()
    rhs = np.r_[np.ones(5), y.sum(0)[:3] / x.sum()]

    def objective(z):
        p = z.reshape(5, 4)
        return np.sum(p * (gram @ p)) - 2*np.sum(p*cross)

    def gradient(z):
        return (2*(gram @ z.reshape(5, 4)-cross)).ravel()

    result = minimize(objective, np.tile(y.sum(0)/x.sum(), (5, 1)).ravel(),
        jac=gradient, method="SLSQP", bounds=Bounds(np.zeros(20), np.ones(20)),
        constraints=LinearConstraint(eq, rhs, rhs), options={"ftol": 1e-9, "maxiter": 1000})
    if not result.success or np.max(np.abs(eq @ result.x-rhs)) > 1e-7:
        raise RuntimeError(f"Sensitivity fit failed: {result.message}")
    p = result.x.reshape(5, 4)
    return {"flows": x.sum(0)[:, None]*p,
            "rmse_votes": float(np.sqrt(np.mean((x@p-y)**2)))}


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                       "| " + " | ".join("---" for _ in headers) + " |",
                       *("| " + " | ".join(map(str, row)) + " |" for row in rows)])


def main():
    out = ROOT / "results/twitter_comparison"
    out.mkdir(parents=True, exist_ok=True)
    cols = ["uf", "municipality_code", "municipality", "zone", "section", "round",
            "polling_place", "section_usable", "a", "b", "other", "invalid",
            "abstention", "eligible", "turnout", "valid"]
    rounds = pd.read_csv(ROOT / "data/processed/2026/section_rounds.csv.gz", usecols=cols)
    rounds = rounds[rounds.municipality_code.eq(CODE)]
    s = paired_sections(rounds).sort_values("section").reset_index(drop=True)
    city = pd.read_csv(ROOT / "results/2026/municipalities.csv")
    city = city[city.municipality_code.eq(CODE)].iloc[0]
    flows = pd.read_csv(ROOT / "results/2026/estimated_flows.csv.gz")
    flows = flows[flows.municipality_code.eq(CODE) & flows.model.eq("full")]
    assert len(s) == 30 and int(s.analysis_eligible.sum()) == 29
    assert city.reference_all_totals_match and int(city.sections_analyzed) == 29
    baseline = flows.pivot(index="origin", columns="destination", values="estimated_voters").reindex(
        index=ORIGINS, columns=DESTINATIONS).to_numpy()

    observed = []
    thread_counts = {"a": [2899, 3503], "b": [3245, 3481], "other": [456, 0],
                     "invalid": [313, 182], "valid": [6600, 6984],
                     "turnout": [6913, 7166], "abstention": [1824, 1571], "eligible": [8737, 8737]}
    for key, values in thread_counts.items():
        for turn, expected in enumerate(values, 1):
            actual = int(s[f"{key}_{turn}"].sum())
            assert actual == int(city[f"{key}_{turn}"])
            observed.append({"metric": key, "round": turn, "thread": expected,
                             "experiment": actual, "difference": actual-expected})
    pd.DataFrame(observed).to_csv(out / "observed_totals.csv", index=False)
    delta_other_required = s.delta_a - s.a_1/(s.a_1+s.b_1)*s.net_new_valid
    s["proportional_required_other_a_recomputed"] = delta_other_required
    s.to_csv(out / "lebon_sections.csv", index=False)
    corr_a = float(s.net_new_valid.corr(s.delta_a))
    corr_b = float(s.net_new_valid.corr(s.delta_b))
    upper_fail = int(delta_other_required.gt(s.other_1+1e-8).sum())
    lower_fail = int(delta_other_required.lt(-1e-8).sum())
    assert (upper_fail, lower_fail) == (12, 1)
    assert int((s.delta_a-s.other_1).clip(lower=0).sum()) == 206
    assert int(s.delta_a.gt(s.other_1).sum()) == 16
    assert round(corr_a, 2) == .83 and round(corr_b, 2) == .02
    assert [int(s.delta_a.gt(0).sum()), int(s.delta_b.gt(0).sum()),
            int(s.delta_b.eq(0).sum()), int(s.delta_b.lt(0).sum())] == [30,25,2,3]
    assert s.groupby(s.a_1.gt(s.b_1))[["delta_a", "delta_b"]].sum().to_numpy().tolist() == [[337,218],[267,18]]
    assert s[s.polling_place_1.eq(1198)][["delta_a", "delta_b"]].sum().tolist() == [126,-4]

    # Explicit counterfactual: match the thread's unchanged electorate/abstention.
    # Only second-round abstention changes, in the one mismatched section.
    x = s[[k+"_1" for k in ORIGINS]].to_numpy(float)
    y = s[[k+"_2" for k in DESTINATIONS]].to_numpy(float)
    gap = y.sum(1)-x.sum(1)
    assert int(np.count_nonzero(gap)) == 1 and gap.sum() == 1
    assert s.loc[gap != 0, "section"].tolist() == [57]
    y[:, -1] -= gap
    assert np.all(y >= 0) and np.array_equal(x.sum(1), y.sum(1))
    assert np.array_equal(THREAD_FLOW.sum(1), x.sum(0))
    assert np.array_equal(THREAD_FLOW.sum(0), y.sum(0))
    weighted = fit_transition(x, y)
    assert weighted["status"] == "ok"
    unweighted = unweighted_fit(x, y)
    sensitivity = []
    for i, origin in enumerate(ORIGINS):
        for j, destination in enumerate(DESTINATIONS):
            row = {"origin": origin, "destination": destination, "thread": THREAD_FLOW[i,j],
                   "saved_29_weighted": baseline[i,j], "scenario_30_weighted": weighted["flows"][i,j],
                   "scenario_30_unweighted": unweighted["flows"][i,j]}
            original = flows[flows.origin.eq(origin) & flows.destination.eq(destination)].iloc[0]
            row.update(saved_bootstrap_p025=original.bootstrap_p025,
                       saved_bootstrap_p975=original.bootstrap_p975)
            sensitivity.append(row)
    pd.DataFrame(sensitivity).to_csv(out / "flow_comparison.csv", index=False)
    distances = {}
    for name, fit in [("scenario_30_weighted", weighted), ("scenario_30_unweighted", unweighted)]:
        assert np.allclose(fit["flows"].sum(1), x.sum(0), atol=.001)
        assert np.allclose(fit["flows"].sum(0), y.sum(0), atol=.001)
        distance = float(np.abs(fit["flows"]-THREAD_FLOW).sum()/2)
        distances[name] = {"half_L1_voters": distance, "electorate_percentage": 100*distance/x.sum(),
                           "section_rmse_votes": fit["rmse_votes"]}
    summary = {"source": "Manual transcription of the user-supplied thread screenshots",
               "municipality": "Lebon Régis", "municipality_code": CODE,
               "full_section_correlations": {"lula": corr_a, "flavio": corr_b},
               "proportional_upper_failures": upper_fail, "proportional_lower_failures": lower_fail,
               "saved_analyzed_sections": 29, "all_sections": 30,
               "counterfactual_change": "Section 57 round-2 abstention 40 -> 39; no official files changed",
               "distances_from_rounded_thread_matrix": distances,
               "timing_comparison": "Not verified: raw machine logs not processed"}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    counts_rows = []
    for key in ["a", "b", "other", "valid", "turnout", "invalid", "abstention", "eligible"]:
        expected = thread_counts[key]
        actual = [int(s[f"{key}_{t}"].sum()) for t in [1,2]]
        counts_rows.append([LABELS.get(key,key.title()), f"{expected[0]:,} → {expected[1]:,}",
                            f"{actual[0]:,} → {actual[1]:,}", "Exact" if expected == actual else "One voter differs in round 2"])
    selected = [("abstention","a"),("invalid","a"),("other","a"),("other","b"),
                ("a","abstention"),("b","abstention"),("other","invalid"),
                ("other","abstention"),("abstention","invalid")]
    flow_rows = []
    for origin,destination in selected:
        i,j = ORIGINS.index(origin),DESTINATIONS.index(destination)
        flow_rows.append([f"{LABELS[origin]} → {LABELS[destination]}",f"{THREAD_FLOW[i,j]:.0f}",
            f"{baseline[i,j]:.1f}",f"{weighted['flows'][i,j]:.1f}",f"{unweighted['flows'][i,j]:.1f}"])
    bflow = flows[flows.origin.eq("other") & flows.destination.eq("b")].iloc[0]
    new_a = float((s.a_1/(s.a_1+s.b_1)*s.net_new_valid).sum())
    text = f"""# Validation against the Twitter thread: Lebon Régis

**Finding:** The observed election results and most descriptive calculations reproduce the thread. The saved flow estimates agree in broad direction but are not an exact numerical replication. Section selection and loss weighting matter.

This compares the existing **municipality-level experiment**, not the proposed hierarchical extension, against the [thread](https://x.com/fiuzaemello/status/2114763737425211824). Thread figures were transcribed from the screenshots supplied in this conversation. Several posts were partially cropped, so absent material is not treated as verified. No new election data was downloaded for this comparison.

## 1. Observed totals

{table(['Quantity','Thread: round 1 → round 2','Official-data experiment: round 1 → round 2','Agreement'],counts_rows)}

Both finalists' gains (+604 Lula; +236 Flávio), the 384 increase in valid votes, and the 840 combined gain reconcile exactly. The first-round third-candidate counts also match: Cury 203, Renan 144, Caiado 90, Zema 9, and the remaining candidates 10.

The saved experiment's full municipal totals use all 30 sections, but its flow model and analyzed-section statistics use 29. Section 57 has 265 eligible voters in round one and 266 in round two, so the equal-electorate screen excludes it. Its vote changes are Lula +8 and Flávio +14. Accordingly, the 29-section model describes gains of **596 and 222**, not the full municipality's 604 and 236.

The official section data and independent municipal reference both give second-round abstention **1,572**, compared with the thread's **1,571**. This is why the thread-compatible sensitivity scenario below is explicitly counterfactual rather than an official correction.

## 2. Descriptive claims reproduced using all 30 sections

| Claim | Thread | Recomputed | Assessment |
|---|---|---|---|
| Lula gain vs net new valid votes: Pearson correlation | 0.83 | {corr_a:.6f} | Matches to the reported precision |
| Flávio gain vs net new valid votes: Pearson correlation | 0.02 | {corr_b:.6f} | Matches to the reported precision |
| Lula gains exceed all first-round third-candidate votes | 16 sections | 16 | Exact |
| Sum of positive excess gains over third-candidate votes | 206 | 206 | Exact arithmetic; source attribution is conditional |
| Sections where Lula gained votes | 30 | 30 | Exact |
| Flávio gained / unchanged / lost | 25 / 2 / 3 | 25 / 2 / 3 | Exact |
| Gains in the 10 sections initially led by Lula | Lula +267; Flávio +18 | +267; +18 | Exact |
| Gains in the other 20 sections | Lula +337; Flávio +218 | +337; +218 | Exact |
| Polling place 1198, three sections | Lula +126; Flávio −4 | +126; −4 | Exact |
| Section 153 | Lula +50; Flávio −5 | +50; −5 | Exact |
| Section 40 | Lula +45; Flávio +10 | +45; +10 | Exact |
| Section 142 | Lula +43; Flávio −2 | +43; −2 | Exact |

The saved 29-section correlations are **0.827992 and 0.048293**. Their difference from the all-section values is explained by the exclusion, not a failed reproduction of the reported correlation formula.

**Interpretive qualification:** the number 206 becomes a lower bound specifically on arrivals from abstention/blank-null voting only if transfers from Flávio to Lula are excluded. With unrestricted switching, our summed section-level lower bound on this source group is **zero** in Lebon Régis. Reproducing the arithmetic does not validate the stronger origin claim or establish a campaign effect. See [the literature review](LITERATURE_REVIEW.md).

## 3. The apparent 12-versus-13 proportional-allocation discrepancy

Allocating net additional valid votes according to each section's first-round finalist shares gives Lula **{new_a:.3f}** and Flávio **{384-new_a:.3f}**, reproducing the thread's approximately 192 each. Lula then requires **{604-new_a:.3f}** of the 456 third-candidate votes, approximately 90%.

The thread's particular claim also reproduces: **12 sections** would require more Lula transfers from third candidates than those sections contain. Our exported count is **13** because it checks both directions of infeasibility: one additional section, **52**, would require a negative allocation to Lula from third candidates (about −1.31 votes). Thus the narrower 12-section claim and our broader 13-section diagnostic are compatible.

The production check marks a section with declining net valid votes untestable for the additional-voter interpretation. That section does not account for the extra infeasibility here.

## 4. Estimated flows: baseline versus two transparent sensitivities

The thread's whole flow matrix is internally balanced, including its 1,571 abstentions. The original fitting objective, weighting, and complete resampling specification remain unknown.

The comparison uses three columns:

1. **Saved 29 / weighted:** the existing national experiment, unchanged. Its smaller electorate makes its absolute flows only partially comparable to the 30-section thread.
2. **Scenario 30 / weighted:** all 30 sections, using our existing estimator. In a temporary in-memory copy only, section 57's round-two abstention is reduced from 40 to 39 to make the electorate and aggregate abstention match the thread. This is a sensitivity assumption, not a justified alteration to the official data.
3. **Scenario 30 / unweighted:** the identical temporary scenario and the identical probability/margin constraints, but minimize unweighted squared count residuals instead of dividing each section's squared residual by its electorate.

{table(['Estimated movement','Thread','Saved 29 / weighted','Scenario 30 / weighted','Scenario 30 / unweighted'],flow_rows)}

Our full saved model allows finalist switching, but the fitted point estimates for both cross-finalist directions are effectively zero. This is a boundary solution of a model, not direct evidence that no person switched.

The unweighted 30-section sensitivity is considerably closer to the thread: half the sum of absolute differences across the full 20-cell matrices is **{distances['scenario_30_unweighted']['half_L1_voters']:.2f} expected voters**, or **{distances['scenario_30_unweighted']['electorate_percentage']:.3f}%** of the shared electorate. For the weighted 30-section scenario, the corresponding distance is **{distances['scenario_30_weighted']['half_L1_voters']:.2f}**, or **{distances['scenario_30_weighted']['electorate_percentage']:.3f}%**.

These are distances from the thread's rounded estimates, **not errors against known true individual flows**. This is an exploratory, post-hoc sensitivity comparison. Closeness does not establish the author's exact algorithm or validate either estimator's substantive accuracy. It does show that the broad explanation can be reproduced closely using a conventional alternative loss, and that some individual cells are sensitive to weighting.

The saved model's section prediction RMSE is **{city.full_rmse_votes:.3f} votes per destination cell**, with maximum absolute section-cell residual **{city.full_max_section_error_votes:.3f}**. Exact municipal destination totals are imposed during fitting; our estimated section destinations need not match all observed section destinations exactly. The thread's accounting identity closing in every section is a different statement from model residuals being zero.

## 5. Uncertainty and timing

- Our saved Lebon Régis fit has 150 successful bootstrap resamples. For third-candidate votes going to Flávio, its percentile range is approximately **{bflow.bootstrap_p025:.1f}–{bflow.bootstrap_p975:.1f}**, compared with the thread's visible reported range **209–321**. They overlap, but our range is wider and is based on 29 sections and our own estimator. Overlap is not a test of agreement or evidence of calibrated coverage.
- Other reported uncertainty details are partially cropped in the supplied screenshots. We cannot validate a full interval-by-interval replication from those images.
- We have **not** verified the thread's last-vote time, zero second-round votes after 17:00, first-round late-vote count, or early-morning share. Raw machine logs have not been processed in this project. BU receipt times cannot substitute for vote-event times.
- The thread analyzes one municipality. Similarity here does not establish that its proposed mechanism applies to all Brazilian municipalities.

## Conclusion

**Yes: the totals, reported correlations, geographic descriptions, and proportional-allocation calculation reproduce well.** The existing weighted 29-section model supports a similar qualitative fitted decomposition—Lula's arrivals mostly from previous abstention/blank-null voting and Flávio's mostly from third candidates—but it does **not** reproduce all flow counts or uncertainty ranges exactly. A documented 30-section unweighted sensitivity comes much closer, without resolving which original estimator was used or whether its implied individual flows are correct.

## Reproduce and inspect

```bash
python scripts/compare_twitter_thread.py
```

Generated comparison files:

- [Observed totals](results/twitter_comparison/observed_totals.csv)
- [All section diagnostics](results/twitter_comparison/lebon_sections.csv)
- [Every transition cell and saved bootstrap range](results/twitter_comparison/flow_comparison.csv)
- [Machine-readable summary and scenario definitions](results/twitter_comparison/summary.json)

The script checks key descriptive claims, matrix margins, and the scope of the one-voter scenario. Official input files, the estimator used for the saved national run, and existing experiment outputs are not modified.
"""
    (ROOT / "TWITTER_COMPARISON.md").write_text(text)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Report: {ROOT / 'TWITTER_COMPARISON.md'}")


if __name__ == "__main__":
    main()
