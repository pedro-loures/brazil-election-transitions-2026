# Plan: polling-place voter transitions with partial pooling

Created: **30 October 2026**. Status: **pilot execution complete; national expansion withheld because validation failed**. The geography audit, 12-municipality fits with three prior variants, 270 known-flow simulations, nine longer-chain confirmation refits, comparison/reliability exports, and interactive report are complete. See [execution findings](HIERARCHY_PILOT_RESULTS.md) and [the statistical specification](docs/hierarchy_specification.md).

Updated: **30 October 2026** to require reliability layers in the final visualizations and an explicit municipal comparison between the existing and proposed methods.

## Objective and agreed direction

Evaluate whether allowing transition probabilities to vary by polling place improves recovery of voter movements and uncertainty calibration compared with the existing municipality-wide model.

Use sections as observations, nested within polling places, nested within municipalities. Estimate municipal patterns and polling-place deviations jointly. Smaller or weakly informative places should receive more regularization toward the municipal pattern; well-informed places may differ when supported by the data. This is **partial pooling**, not simply fitting the existing model separately to every polling place.

The user requested this plan to continue the work in another chat. This document preserves the proposed work; it does not authorize claims that the new model already works or that local transition estimates identify individual ballots or campaign effects.

Two additional requirements are mandatory:

1. Show reliability diagnostics alongside estimated vote/transition patterns, and allow maps to be colored by a selected reliability metric instead of the voting estimate.
2. Compare municipal estimates from both methods on the same electorate. Large disagreements are red flags requiring investigation before scaling; agreement alone does not establish that either method recovered the true transitions.

These are retrospective election results and inferred transitions, not surveyed or forecast voting intentions. Use those labels in the interface even when describing the requested voting-pattern view.

## Existing project and completed work

Project root: `/scratch2/pedro.loures/elections_twitter`.

| Resource | Purpose |
|---|---|
| [README.md](README.md) | Current methods, commands, data preparation, outputs, and limitations |
| [LITERATURE_REVIEW.md](LITERATURE_REVIEW.md) | Academic sources supporting or challenging specific components, with a supplement for the pilot |
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
5. Freeze the pilot list, source snapshot, random seeds, targets, and evaluation criteria before comparing models. Specify municipal disagreement measures, substantively meaningful warning thresholds, and the investigation process before inspecting which municipalities disagree.
6. Audit available map geometry. Preserve a verified mapping between TSE and geographic municipality identifiers. Polling-place point maps require verified locations; a polling-place code is not a coordinate or an electoral catchment boundary. Record unmatched geography and do not imply building-level spatial precision from municipal centroids.

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

Also measure the disagreement between the existing and hierarchical municipal estimates in each simulation. Determine whether a large difference corresponds to deterioration, an improvement over a biased baseline, or weak information. Use these results to assess warning thresholds and the likelihood of unnecessary flags. Similarity to the existing method is a robustness diagnostic, not the optimization target or a substitute for known-flow validation.

The literature review identifies relevant benchmarks: Brown–Payne-style heterogeneous models, R×C methods, and LPHOM-family algorithms. Adding a published comparator is desirable where a defensible implementation is available; do not present our baseline as representative of every ecological-inference method.

Deliverable: a reproducible simulation report showing where partial pooling helps, where it hurts, and where results remain weakly identified.

## Phase 4 — Implement and fit the real-data pilot

Proposed code additions, subject to the specification above:

- A geography/inventory component that creates audited nested groups.
- A separate hierarchical-model module; preserve the current estimator for comparison.
- Pilot fitting and simulation commands, with source hashes, configurations, seeds, software versions, and saved fit diagnostics.
- Exports for local and electorate-weighted municipal flow summaries, uncertainty, coverage, and sensitivity results.
- A common reliability-metric schema and a paired municipal-comparison export, with the definitions below.

Select the statistical backend only after checking existing packages, numerical requirements, and pilot costs. If simulation-based Bayesian inference is used, inspect chain convergence, effective sample sizes, divergences, posterior geometry, and prior sensitivity. A successful optimizer or sampler exit is not sufficient validation.

Use posterior/model predictive checks for section-level outcomes and assess residual patterns by polling place. Held-out section or place prediction can test prediction of observed aggregates, but **cannot by itself verify hidden voter movements**. Independent transition information, if available, requires separate assessment of sampling, recall, and nonresponse error.

Compare pilot estimates to the existing model on the identical retained electorate. Show how exclusions affect coverage. Recompute unrestricted bounds independently of the model and investigate discrepancies between expected-flow summaries and feasible realized-flow ranges.

### Required municipal comparison between the two methods

Compare the existing **municipal common-matrix model** with the proposed **polling-place hierarchical model aggregated to municipality**. This is required for the pilot and for any wider run.

1. **Align inputs and definitions.** Use identical source snapshots, category definitions, retained sections, electorate, and switching assumptions. If eligibility changes, refit the baseline on the common subset in a separate output directory. Preserve results for the extra sections as a distinct coverage extension. Mark municipalities where a paired fit is unavailable; do not silently discard them.
2. **Aggregate flows, not unweighted probabilities.** For each origin/destination pair, obtain hierarchical municipal expected flows by summing section origin counts multiplied by the corresponding local transition probabilities, draw by draw. Sum counts first; obtain origin-conditional municipal rates by dividing by that origin's municipal count. Do not average polling places equally or treat the municipal logit baseline as the population-weighted matrix. An absent origin category has an undefined rate, not a zero rate.
3. **Match the estimands.** Compare expected flow allocations with expected flow allocations. Keep posterior reconstructions of realized latent tables separate. The old estimator imposes exact municipal destination margins, whereas the proposed likelihood may not impose them on expected counts. Report that calibration distinction rather than hiding it through post-fit adjustment.
4. **Separate three checks.** Observed municipal vote totals must agree when inputs are identical: a mismatch is a data/preparation error. Differences in model-predicted destination totals assess prediction/calibration. Differences in the internal transition estimates assess dependence on modeling assumptions. Matching the observed or imposed destination totals does not validate the hidden flows.
5. **Export several disagreement measures.** Include signed/absolute differences in expected voter counts for each flow; origin-conditional rate differences in percentage points; maximum absolute rate differences for supported origin categories; and differences in key summaries such as previous abstainers or blank/null voters estimated to vote for each finalist. Show denominators and small-origin warnings.
6. **Include a size-normalized matrix distance.** For the common electorate `N_m`, compute `D_m = sum_gk(abs(F_hierarchical[m,g,k] - F_baseline[m,g,k])) / (2*N_m)`. This is the total-variation distance between the two expected flow allocations expressed as shares of the electorate. It measures disagreement between estimates, not the proportion of voters either model classified incorrectly. Do not confuse it with origin-conditional percentage-point differences.
7. **Compare uncertainty carefully.** Present each method's interval with its type and conditioning assumptions. Old bootstrap ranges and new posterior credible intervals are not interchangeable. Interval overlap alone is not a formal agreement test. If an interval for the difference is developed, justify a joint/paired procedure respecting the shared data instead of treating estimates as independent.
8. **Flag and investigate large disagreements.** Apply the predeclared, simulation-informed thresholds to substantive flow differences and matrix distance, with stronger attention to discrepancies stable across seeds, prior choices, and fitting variants. Inspect geography/matching, coverage, conditioning, convergence, boundary estimates, contextual heterogeneity, calibration choices, and influential places. Determine which method performs better in comparable known-flow scenarios. A flag is not evidence of fraud and is not automatic grounds to discard the hierarchical model.

Required comparison views: paired scatterplots with an equality line, difference-versus-size or mean plots, distributions of municipal flow/rate differences, and a municipality map of disagreement flags and magnitude. Include uncertainty and common-electorate coverage when inspecting a flagged municipality.

Deliverable: pilot model outputs, a reliability export, and a paired municipal comparison report with a table of flagged cases and investigation outcomes. Keep uncertainty under the hierarchy distinct from the old section-bootstrap ranges.

### Reliability metrics required in exports and final visualizations

Report these alongside each applicable municipal and polling-place estimate. A single unvalidated composite reliability score must not replace the individual diagnostics.

| Metric | Required interpretation and display |
|---|---|
| Point estimate and 95% interval | Show expected voters and/or a clearly defined transition rate, lower/upper endpoints, and interval method. Distinguish Bayesian credible intervals from the baseline's uncalibrated bootstrap sensitivity ranges. These are pointwise intervals, not automatically simultaneous guarantees across all places or flows. |
| Interval width | Show absolute width in voters and rate width in percentage points. A narrower interval is not automatically more reliable. Any relative-width measure must define its denominator and handle near-zero estimates without misleading infinities. |
| Data coverage and information | Show included electorate fraction, eligible/excluded section counts, local origin-group counts, and composition variation or weak-design warnings. Electoral-data coverage is distinct from statistical interval coverage. |
| Prior/pooling sensitivity | Show changes under the documented prior and pooling-strength variants, in comparable voter or percentage-point units. Provide an interpretable diagnostic of reliance on shared information; do not invent a universal pooling weight for a nonlinear model. |
| Local heterogeneity | Report estimated between-place variation and its uncertainty at the level actually modeled. Explain that variation is not itself a reliability score and that sparse data can leave it prior-sensitive. |
| Model fit and computation | Show relevant section predictive residual/error measures, predictive checks, and fitting/convergence status. For Bayesian simulation include appropriate chain and sampling diagnostics. Good aggregate fit does not establish accurate flows. |
| Simulation validation evidence | Report bias, flow error, interval coverage, interval width, and failure rates for the simulation scenarios relevant to the method and information level. True bias or interval coverage cannot be measured directly for a real municipality whose transitions are unobserved. If attaching a scenario/stratum result to a place, label its scope and applicability; otherwise show this evidence only in the validation view. |
| Between-method disagreement | Show the municipal flow/rate differences, normalized matrix distance, red-flag status, and investigation outcome defined above. Agreement is supporting robustness evidence, not ground truth. |

Suggested outputs include an estimate-level reliability table and a municipal-method-comparison table, linked by audited geographic keys, origin/destination, method, common-electorate scope, interval type, and run/configuration identifiers. Retain unavailable/not-estimable statuses and diagnostic reasons; do not encode missing reliability as zero or as high confidence.

## Phase 5 — Decide whether to scale

Proceed to a wider run only if:

- The statistical model and computation pass known-flow recovery and diagnostic checks.
- Simulations show useful accuracy and uncertainty performance across relevant scenarios, including sparse places and misspecification.
- Prior/shrinkage choices do not conceal substantial sensitivity.
- Municipal discrepancies between the methods have been measured, and cases above the predeclared warning thresholds have documented investigation outcomes. Unexplained material disagreements block an unqualified nationwide interpretation; resolve them, revise the model, or narrow its scope before scaling.
- Pilot resource measurements support a practical national execution strategy.
- Failures and insufficient-information cases have explicit statuses, with no substitution of zero flows for missing results.

If these conditions do not hold, report that result and refine the model or narrow the claims. National execution is a decision after validation, not the default conclusion of implementing a hierarchical model.

For any wider run, retain resumable outputs, source/configuration manifests, coverage summaries, and clear separation of observed counts, deterministic bounds, fitted rates, and reconstructed counts. Extend the searchable report with a municipality → polling-place view and plain-language uncertainty explanations.

### Required final map and comparison interface

- Add a **color-by selector** so the same map can show the selected voting/transition estimate or an applicable reliability metric: interval width, retained-electorate coverage, sensitivity to priors/pooling, model fit, computation status, or municipal between-method disagreement/flag status. Simulation-based coverage or error layers are allowed only when their scenario/stratum meaning and applicability are explicitly established; do not label them measured local accuracy.
- Include selectors for method, municipality versus polling-place level where verified geometry permits, candidate/flow, and rate/count units. Keep geography and denominators consistent during comparisons. Between-method municipal diagnostics must stay at the municipal level unless a comparable local baseline is actually available.
- Use metric-appropriate legends, including diverging scales for signed differences and explicit units. Fix comparable scales across methods when comparing the same quantity. Display missing data, failed fits, and insufficient information separately from numerical zero. Do not color a tight but unvalidated interval as proof of high reliability.
- Show the estimate, interval/type, interval width, data coverage, local information, sensitivity, model status, and relevant comparison flags in the selected area's tooltip or detail panel, even when color represents the voting estimate. Provide a side-by-side estimate/reliability view or equivalent interaction so users can inspect both together.
- Link flagged municipalities to paired flow tables, both methods' uncertainty displays, difference plots, common-electorate coverage, and investigation notes. Include filters for material disagreement and weak-information areas.
- Export the map's underlying values and configuration. Verify map-key joins, missing-value handling, interval labels, denominator consistency, switches between metric layers, and exact aggregation of local flow draws into municipal summaries.
- Treat a national map as a presentation of estimates and diagnostics, not a simultaneous confidence statement or an anomaly/fraud classifier.

Deliverable: an interactive estimate/reliability map and municipal-comparison view, with clear metric definitions and downloadable paired results. Map construction belongs to implementation after the pilot; this plan does not create or publish a map.

## Boundaries on interpretation

Smaller geographic groups may reduce some heterogeneity but may also reduce information. More flexible models can fit aggregates better without recovering transitions more accurately. Neither partial pooling nor a national run guarantees removal of the ecological fallacy. No model here reveals individual ballots or identifies the causal effect of campaign mobilization.

## First steps in the next chat

1. Open this plan, the README, and the literature review in the existing project.
2. Verify the saved baseline and audit the polling-place keys using cached data.
3. Produce the pilot inventory and select a representative pilot.
4. Resolve the observation model and shrinkage specification before implementing the new estimator.
5. Implement and evaluate simulations before making substantive claims from real-data local flow estimates.
6. Build the paired municipal comparison and reliability exports, investigate material differences, and expose those diagnostics alongside estimates and as selectable map layers before final delivery.

The sequence above records the original handoff. Execution used `results/2026/hierarchy_pilot/manifest.json` to freeze the 12-city pilot, input hashes, priors, thresholds, and seeds. A documented addendum added a two-place simulation before its outcomes were generated. [Final findings](HIERARCHY_PILOT_RESULTS.md) and `results/2026/hierarchy_pilot/validation_gate.json` record the decision **do not scale**: within-place misspecification produced 67.2% average interval coverage and 1.67 times the baseline's flow RMSE; municipal differences remain unresolved. The national baseline is preserved. All 31 Python tests, posterior/export checks, and offline browser checks passed; these software checks do not override the failed statistical validation. The timing audit remains outside this plan.
