# Validation against the Twitter thread: Lebon Régis

**Finding:** The observed election results and most descriptive calculations reproduce the thread. The saved flow estimates agree in broad direction but are not an exact numerical replication. Section selection and loss weighting matter.

This compares the existing **municipality-level experiment**, not the proposed hierarchical extension, against the [thread](https://x.com/fiuzaemello/status/2114763737425211824). Thread figures were transcribed from the screenshots supplied in this conversation. Several posts were partially cropped, so absent material is not treated as verified. No new election data was downloaded for this comparison.

## 1. Observed totals

| Quantity | Thread: round 1 → round 2 | Official-data experiment: round 1 → round 2 | Agreement |
| --- | --- | --- | --- |
| Lula | 2,899 → 3,503 | 2,899 → 3,503 | Exact |
| Flávio | 3,245 → 3,481 | 3,245 → 3,481 | Exact |
| Other candidates | 456 → 0 | 456 → 0 | Exact |
| Valid | 6,600 → 6,984 | 6,600 → 6,984 | Exact |
| Turnout | 6,913 → 7,166 | 6,913 → 7,166 | Exact |
| Blank/null | 313 → 182 | 313 → 182 | Exact |
| Abstention | 1,824 → 1,571 | 1,824 → 1,572 | One voter differs in round 2 |
| Eligible | 8,737 → 8,737 | 8,737 → 8,738 | One voter differs in round 2 |

Both finalists' gains (+604 Lula; +236 Flávio), the 384 increase in valid votes, and the 840 combined gain reconcile exactly. The first-round third-candidate counts also match: Cury 203, Renan 144, Caiado 90, Zema 9, and the remaining candidates 10.

The saved experiment's full municipal totals use all 30 sections, but its flow model and analyzed-section statistics use 29. Section 57 has 265 eligible voters in round one and 266 in round two, so the equal-electorate screen excludes it. Its vote changes are Lula +8 and Flávio +14. Accordingly, the 29-section model describes gains of **596 and 222**, not the full municipality's 604 and 236.

The official section data and independent municipal reference both give second-round abstention **1,572**, compared with the thread's **1,571**. This is why the thread-compatible sensitivity scenario below is explicitly counterfactual rather than an official correction.

## 2. Descriptive claims reproduced using all 30 sections

| Claim | Thread | Recomputed | Assessment |
|---|---|---|---|
| Lula gain vs net new valid votes: Pearson correlation | 0.83 | 0.832615 | Matches to the reported precision |
| Flávio gain vs net new valid votes: Pearson correlation | 0.02 | 0.021942 | Matches to the reported precision |
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

Allocating net additional valid votes according to each section's first-round finalist shares gives Lula **191.512** and Flávio **192.488**, reproducing the thread's approximately 192 each. Lula then requires **412.488** of the 456 third-candidate votes, approximately 90%.

The thread's particular claim also reproduces: **12 sections** would require more Lula transfers from third candidates than those sections contain. Our exported count is **13** because it checks both directions of infeasibility: one additional section, **52**, would require a negative allocation to Lula from third candidates (about −1.31 votes). Thus the narrower 12-section claim and our broader 13-section diagnostic are compatible.

The production check marks a section with declining net valid votes untestable for the additional-voter interpretation. That section does not account for the extra infeasibility here.

## 4. Estimated flows: baseline versus two transparent sensitivities

The thread's whole flow matrix is internally balanced, including its 1,571 abstentions. The original fitting objective, weighting, and complete resampling specification remain unknown.

The comparison uses three columns:

1. **Saved 29 / weighted:** the existing national experiment, unchanged. Its smaller electorate makes its absolute flows only partially comparable to the 30-section thread.
2. **Scenario 30 / weighted:** all 30 sections, using our existing estimator. In a temporary in-memory copy only, section 57's round-two abstention is reduced from 40 to 39 to make the electorate and aggregate abstention match the thread. This is a sensitivity assumption, not a justified alteration to the official data.
3. **Scenario 30 / unweighted:** the identical temporary scenario and the identical probability/margin constraints, but minimize unweighted squared count residuals instead of dividing each section's squared residual by its electorate.

| Estimated movement | Thread | Saved 29 / weighted | Scenario 30 / weighted | Scenario 30 / unweighted |
| --- | --- | --- | --- | --- |
| Abstention → Lula | 478 | 424.0 | 457.1 | 482.7 |
| Blank/null → Lula | 194 | 206.7 | 206.6 | 197.8 |
| Other candidates → Lula | 13 | 31.3 | 14.5 | 8.0 |
| Other candidates → Flávio | 292 | 241.7 | 256.8 | 294.2 |
| Lula → Abstention | 81 | 66.0 | 74.2 | 84.4 |
| Flávio → Abstention | 56 | 19.7 | 20.8 | 58.2 |
| Other candidates → Blank/null | 57 | 51.3 | 58.8 | 57.3 |
| Other candidates → Abstention | 94 | 114.7 | 125.9 | 96.5 |
| Abstention → Blank/null | 6 | 27.3 | 16.7 | 9.5 |

Our full saved model allows finalist switching, but the fitted point estimates for both cross-finalist directions are effectively zero. This is a boundary solution of a model, not direct evidence that no person switched.

The unweighted 30-section sensitivity is considerably closer to the thread: half the sum of absolute differences across the full 20-cell matrices is **22.53 expected voters**, or **0.258%** of the shared electorate. For the weighted 30-section scenario, the corresponding distance is **110.65**, or **1.266%**.

These are distances from the thread's rounded estimates, **not errors against known true individual flows**. This is an exploratory, post-hoc sensitivity comparison. Closeness does not establish the author's exact algorithm or validate either estimator's substantive accuracy. It does show that the broad explanation can be reproduced closely using a conventional alternative loss, and that some individual cells are sensitive to weighting.

The saved model's section prediction RMSE is **5.279 votes per destination cell**, with maximum absolute section-cell residual **13.756**. Exact municipal destination totals are imposed during fitting; our estimated section destinations need not match all observed section destinations exactly. The thread's accounting identity closing in every section is a different statement from model residuals being zero.

## 5. Uncertainty and timing

- Our saved Lebon Régis fit has 150 successful bootstrap resamples. For third-candidate votes going to Flávio, its percentile range is approximately **147.3–324.3**, compared with the thread's visible reported range **209–321**. They overlap, but our range is wider and is based on 29 sections and our own estimator. Overlap is not a test of agreement or evidence of calibrated coverage.
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
