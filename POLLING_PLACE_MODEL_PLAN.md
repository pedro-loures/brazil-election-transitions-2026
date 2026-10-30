# Plan: polling-place voter transitions with partial pooling

Created: **30 October 2026**. Status: **planning only; the hierarchical model has not been implemented or fitted**.

## Objective and agreed direction

Evaluate whether allowing transition probabilities to vary by polling place improves recovery of voter movements and uncertainty calibration compared with the existing municipality-wide model.

Use sections as observations, nested within polling places, nested within municipalities. Estimate municipal patterns and polling-place deviations jointly. Smaller or weakly informative places should receive more regularization toward the municipal pattern; well-informed places may differ when supported by the data. This is **partial pooling**, not simply fitting the existing model separately to every polling place.

The user requested this plan to continue the work in another chat. This document preserves the proposed work; it does not authorize claims that the new model already works or that local transition estimates identify individual ballots or campaign effects.

## Existing project and completed work

Project root: `/scratch2/pedro.loures/elections_twitter`.

| Resource | Purpose |
|---|---|
| [README.md](README.md) | Current methods, commands, data preparation, outputs, and limitations |
| [LITERATURE_REVIEW.md](LITERATURE_REVIEW.md) | Seventeen academic sources supporting or challenging specific components |
| [elections/model.py](elections/model.py) | Current constrained common-transition model and section bootstrap |
| [elections/analysis.py](elections/analysis.py) | Round matching, eligibility, bounds, correlations, and municipal analysis |
| [elections/data.py](elections/data.py) | Official TSE bulk-data ingestion and ballot classification |
| [elections/report.py](elections/report.py) | Existing report generation |
| [results/2026/run.json](results/2026/run.json) | Baseline run settings and software versions |
| [results/2026/report.html](results/2026/report.html) | Existing nationwide report |

The completed baseline uses the **2026 presidential election** shown in the original screenshots. It includes all 5,571 domestic municipality units represented in the files, with 442,108 eligible paired sections out of 497,897 domestic sections. Flow models were fitted for 5,134 municipalities; 437 had too few eligible sections. All 11,142 municipal-round reference comparisons reconcile. Seventeen tests passed in the completed baseline work.

The current model estimates one common 5×4 transition-rate matrix per municipality, using constrained weighted least squares and exact municipal destination margins. Its alternative fit prohibits finalist switching. Its 150-resample bootstrap measures conditional model sensitivity; it has not been shown to deliver calibrated coverage under contextual heterogeneity or dependence.

Raw downloads and their provenance are cached under `data/raw/2026/`; prepared inputs are under `data/processed/2026/`. Reuse these snapshots initially. Keep the existing national results intact and write experimental outputs to a separate directory.

The nationwide machine-log timing audit is unfinished and **outside this model-extension plan**. The original Twitter estimator remains incompletely specified; the existing code is an explicit reconstruction, not the author's recovered implementation.

## Evidence motivating the extension

A read-only grouping of currently eligible paired sections by **UF + municipality + zone + polling-place code** found:

- 92,725 polling-place groups with usable sections.
- Median: four usable sections per group.
- 11,972 groups, about 13%, have at least ten usable sections.
- About 59% have fewer than five usable sections.

These figures concern usable groups in the current snapshot, not a census of every registered polling place. Confirm the grouping definition before interpreting a group as a unique physical building. The existing polling-place export groups without zone; audit whether including zone splits a building or prevents code collisions.

The current ten-section cutoff is an operational screen, not a theorem. With four observed destination categories, a section supplies only three independent destination counts. Many places cannot support an unrestricted local 5×4 model without assumptions. Partial pooling regularizes that problem; it does not create missing information or guarantee that a local estimate is data-driven.

## Phase 1 — Validate geography and define the pilot

1. Read the existing methodology and literature review, and verify the saved source manifests and baseline run metadata.
2. Inspect section-to-place mappings across rounds. Check code reuse across zones, polling-place relocations, aggregated sections, and whether equal electorate counts plausibly describe the same population. Retain explicit exclusion reasons.
3. Produce a place-level inventory: section counts, electorate, first-round composition variation, missing categories, design rank/conditioning, and coverage. Distinguish information about a place from its sheer voter count.
4. Select a reproducible pilot of approximately 10–20 municipalities spanning size, geographic context, coverage, number of places, and composition variation. Include Lebon Régis for comparison with the thread. Avoid selecting only municipalities where the proposed model looks favorable.
5. Freeze the pilot list, source snapshot, random seeds, targets, and evaluation criteria before comparing models.

Deliverable: a pilot inventory and a short statistical specification. No national refit at this stage.

## Phase 2 — Specify a joint hierarchical transition model

For first-round origin category `g`, second-round destination `k`, municipality `m`, and polling place `p`, a candidate parameterization is:

```text
P[m,p,g,:] = softmax(mu[m,g,:] + u[m,p,g,:])
```

Use one reference destination, or equivalent identifiability constraints, for the logits. A five-origin/four-destination matrix has fifteen free row-probability parameters. Start with a parsimonious distribution for place deviations, with shrinkage scales documented and tested through prior-predictive simulation. A full unrestricted covariance matrix is not the default.

Important design choices:

- Estimate municipal baselines and local deviations in **one joint model**. Do not use the same section outcomes once to create a fixed municipal prior and a second time as supposedly independent evidence.
- Decide where heterogeneity scales can be learned. Municipalities with few places cannot reliably estimate their own elaborate variance structure. Consider shared scales across the pilot, or clearly stated regularizing priors; assess sensitivity before adding more levels.
- Describe the baseline correctly: a softmax of the municipal logits is a reference pattern, not automatically the arithmetic mean of local probabilities or the electorate-weighted municipal transition matrix. Compute municipal flow summaries from the local quantities.
- Keep finalist switching allowed in the primary model. A no-switch variant may be a labeled sensitivity analysis, not an observed fact.
- Identify which summaries are driven mainly by local evidence, municipal pooling, or prior assumptions. Small intervals caused by strong regularization do not establish identification.

### Observation model and computational decision

A principled candidate is to let each section's latent origin-to-destination counts have multinomial rows with known first-round row totals and local transition probabilities. The observed second-round counts constrain the column sums. The likelihood sums over compatible latent tables; it is not a likelihood for directly observed individual transitions.

Evaluate feasibility on small pilot cases before selecting a computational backend. Exact likelihood calculations, latent-table sampling, or approximations have different costs and assumptions. If using an approximation to count means or covariances, document it and check it against exact small cases. Do not equate an expected flow table with a realized table satisfying every section margin.

Do not automatically carry over the current estimator's hard constraint on expected municipal destination margins. The new model must distinguish observation likelihood, expected counts, and reconstructed latent counts. Observed municipal totals are sums of section outcomes, not an additional independent dataset. Any post-fit calibration must be disclosed and its consequences evaluated.

Deliverable: an explicit generative/observation model, prior specification, computational justification, and definitions of every estimated quantity.

## Phase 3 — Build validation cases with known flows

Compare at least these specifications on the **same simulated datasets**:

1. Existing common-matrix municipal estimator.
2. Independent polling-place estimates where estimable, with failures reported rather than silently excluded.
3. The proposed partial-pooling model.

Simulations should preserve realistic section sizes and first-round compositions while generating known individual transition tables. Include:

- No place heterogeneity, where unnecessary flexibility should not improve results automatically.
- Moderate and strong place heterogeneity.
- Transitions related to first-round composition, a direct contextual-bias stress test.
- Additional variation between sections within a place, testing misspecification of the proposed grouping.
- Weak composition variation, small origin categories, and near-collinear designs.
- One-section and other sparse places; municipalities with few places.
- True zero/near-zero transitions and genuine finalist switching.
- Electorate mismatch or turnover scenarios, treated separately from the initial closed-electorate analysis.

Measure bias, absolute/RMSE flow error, interval coverage and width, boundary behavior, fitting failures, and computational cost. Evaluate both local and municipal summaries; report sparse-place performance separately. Inspect how much uncertainty changes with priors and heterogeneity assumptions. Predefine practically meaningful comparison criteria; do not select the winning method only by observed-total fit.

The literature review identifies relevant benchmarks: Brown–Payne-style heterogeneous models, R×C methods, and LPHOM-family algorithms. Adding a published comparator is desirable where a defensible implementation is available; do not present our baseline as representative of every ecological-inference method.

Deliverable: a reproducible simulation report showing where partial pooling helps, where it hurts, and where results remain weakly identified.

## Phase 4 — Implement and fit the real-data pilot

Proposed code additions, subject to the specification above:

- A geography/inventory component that creates audited nested groups.
- A separate hierarchical-model module; preserve the current estimator for comparison.
- Pilot fitting and simulation commands, with source hashes, configurations, seeds, software versions, and saved fit diagnostics.
- Exports for local and electorate-weighted municipal flow summaries, uncertainty, coverage, and sensitivity results.

Select the statistical backend only after checking existing packages, numerical requirements, and pilot costs. If simulation-based Bayesian inference is used, inspect chain convergence, effective sample sizes, divergences, posterior geometry, and prior sensitivity. A successful optimizer or sampler exit is not sufficient validation.

Use posterior/model predictive checks for section-level outcomes and assess residual patterns by polling place. Held-out section or place prediction can test prediction of observed aggregates, but **cannot by itself verify hidden voter movements**. Independent transition information, if available, requires separate assessment of sampling, recall, and nonresponse error.

Compare pilot estimates to the existing model on the identical retained electorate. Show how exclusions affect coverage. Recompute unrestricted bounds independently of the model and investigate discrepancies between expected-flow summaries and feasible realized-flow ranges.

Deliverable: pilot model outputs and a comparison report. Keep uncertainty under the hierarchy distinct from the old section-bootstrap ranges.

## Phase 5 — Decide whether to scale

Proceed to a wider run only if:

- The statistical model and computation pass known-flow recovery and diagnostic checks.
- Simulations show useful accuracy and uncertainty performance across relevant scenarios, including sparse places and misspecification.
- Prior/shrinkage choices do not conceal substantial sensitivity.
- Pilot resource measurements support a practical national execution strategy.
- Failures and insufficient-information cases have explicit statuses, with no substitution of zero flows for missing results.

If these conditions do not hold, report that result and refine the model or narrow the claims. National execution is a decision after validation, not the default conclusion of implementing a hierarchical model.

For any wider run, retain resumable outputs, source/configuration manifests, coverage summaries, and clear separation of observed counts, deterministic bounds, fitted rates, and reconstructed counts. Extend the searchable report with a municipality → polling-place view and plain-language uncertainty explanations.

## Boundaries on interpretation

Smaller geographic groups may reduce some heterogeneity but may also reduce information. More flexible models can fit aggregates better without recovering transitions more accurately. Neither partial pooling nor a national run guarantees removal of the ecological fallacy. No model here reveals individual ballots or identifies the causal effect of campaign mobilization.

## First steps in the next chat

1. Open this plan, the README, and the literature review in the existing project.
2. Verify the saved baseline and audit the polling-place keys using cached data.
3. Produce the pilot inventory and select a representative pilot.
4. Resolve the observation model and shrinkage specification before implementing the new estimator.
5. Implement and evaluate simulations before making substantive claims from real-data local flow estimates.

The next executable work is **Phase 1**, followed by the statistical specification. No hierarchical fit, new nationwide run, or raw-log collection was performed while preparing this handoff.
