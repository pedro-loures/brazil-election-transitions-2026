# Spatial-pooling experiment: implementation specification

The accepted scope is in `../SPATIAL_POOLING_PLAN.md`. Actual execution is in `../SPATIAL_POOLING_RESULTS.md` and the experiment output directory. These documents distinguish implemented software from statistical validation.

## Geography, grouping and study design

The closed-electorate section key is UF, TSE municipality, electoral zone and section. Reuse baseline eligibility and technical-null classification. Register joins also include round and place code. Verify coordinate range, round stability, normalized address stability, aggregation stability and containment in detailed IBGE 2025 geometry. `verified_register_boundary` means these checks passed, not independent confirmation of a building or election-day relocation history. Missing and unresolved coordinates remain separate statuses; all primary comparators use the same verified subset. Report omissions against the original retained electorate.

Use the frozen IBGE population bins. Select ten municipalities per bin 1–4 using region-balanced farthest-first selection on first-round information and geography; include all eight in bin 5. Region-balanced splits are six/four and five/three. An extra historical city does not enter threshold selection or held-out validation. The manifest is frozen before generating simulated outcomes.

Exact co-locations define initial groups. Construct a symmetrized eight-nearest-site graph using spherical chord neighbours and great-circle edge lengths. Process edges from shortest to longest, breaking ties by sorted coordinate identifiers. Merge different groups if at least one is undersized and the resulting exact maximum pairwise geodesic distance does not exceed the cap. Counts are soft targets; geographic caps and co-location preservation are hard constraints. Export every target/cap partition, group information and overshoot. No second-round results enter grouping.

The geometric shortlist takes one configuration from each target band {5,10}, {20,40}, {80,160}, minimizing development undersized-electorate fraction, then distance cap, then median diameter. It is a computational shortlist, not a validated threshold. Development simulations determine whether any shortlisted configuration is admissible. None is an allowed conclusion.

## Statistical models and expected flows

There are five origins and four destinations. With first-round counts x[s,g], municipal reference logits mu[g,k], geographic or administrative group G(s), and three non-reference destination logits:

```
eta[s,g,k] = mu[g,k] + tau*z[G(s),g,k]
```

The matched Bayesian municipal model omits tau and z. The extended hierarchy adds `sum_c w[s,c]*beta[c,g,k]`, where w consists of the first four origin shares, centered and scaled across the municipality. The fifth share is implied. Mu, group deviations and contextual effects are inferred jointly; the second-round observations are not fitted once to construct an empirical prior and reused as new evidence.

Primary priors are mu ~ Normal(0,2), z ~ Normal(0,1), tau ~ HalfNormal(0.5), beta ~ Normal(0,0.25), rho ~ Beta(1,19). Tighter/wider variants are recorded in the frozen manifest. These are study choices, not empirically established Brazilian transition priors. All finalist switching is allowed.

Abstention is the zero reference logit, so these logit priors are not exchangeable across destinations. The sensitivity variants vary their spreads; they do not remove that modeling choice. Development selection considers geographic models with and without the extension. Method and grouping freeze together; for equally local passing configurations, prefer the simpler model. Held-out performance cannot select a different winner.

The basic model has independent multinomial origin rows. The extension instead uses independent Dirichlet-multinomial origin rows with intraclass correlation rho. For the first three destination margins, the exact first two moments under this model are:

```
mean[s,k] = sum_g x[s,g]*p[s,g,k]
cov[s,k,l] = sum_g x[s,g]*(1+(x[s,g]-1)*rho)
              * (1[k=l]*p[s,g,k] - p[s,g,k]*p[s,g,l])
```

The fitted margin likelihood is a multivariate normal density using those moments and 1e-6 diagonal jitter. Rho=0 recovers the basic model. Exact small-count convolution and simulation checks validate the moments; they do not establish accuracy of the full approximate posterior. The exact audit records approximation errors instead of suppressing them.

For every posterior draw, section allocations are x[s,g]*p[s,g,k]. Sum these allocations within the desired support before calculating quantiles. Overdispersion changes the margin variance; outputs do not reconstruct separate latent section matrices or individual transition tables. Simulation recovery of genuinely different hidden section propensities is a robustness test of these fitted mean allocations.

Literal aggregation sums x and y within a geographic group before fitting. Its implied rates are then projected back onto the original sections for fixed-support evaluation. It is distinct from retaining section observations under a shared parameter hierarchy.

The historical comparator keeps its constrained WLS point estimate and 150 independent-section bootstrap sensitivity ranges. The WLS point estimate is not replaced by the bootstrap mean. Its implied local rates are evaluated without presenting it as an independently fitted local model.

## Simulation, calibration and selection

Generate section truth and realized row counts before grouping. Scenario mechanisms and independent deterministic streams are frozen. All comparators receive identical generated data for each bin/scenario/replicate. Replicates rotate through the appropriate municipal templates; repeated simulations do not create new independent geographic designs. Confirmation jobs preserve the generated dataset with `data_phase=development` and change the computational budget. They do not increase the independent replication count.

Score municipality, original administrative places, original sections and new groups. Report each origin/destination separately. Absent origins have unavailable rates; true zeros have separate upper-limit/practical-zero diagnostics. Exact zero recovery is not certified by a continuous-prior equal-tailed interval. Correlated units/cells are averaged within a dataset before Monte Carlo calculations.

Development uses point coverage ≥90% as a screen; 30 datasets cannot certify calibration. Monte Carlo bounds invert [Hoeffding (1963), Theorem 1, equation (2.1)](https://www.cs.rpi.edu/academics/courses/spring06/random/hoefding.pdf) for independent dataset summaries in [0,1]. The error budget covers both tails and the three planned admission looks. MCSE is bounded using the resulting mean interval; empirical MCSE is also exported. Completed-checkpoint records prevent interim peeking from approving scale. These are pointwise criteria, not simultaneous geographic guarantees.

Relative RMSE uses matched completed dataset identifiers, with explicit paired availability. Exact zero-flow cases with a zero-error reference use their absolute-error and boundary diagnostics instead of an undefined ratio. Absent origins have structurally zero counts and undefined rates; they are not failed interval-calibration tests. Supported flows elsewhere must still satisfy every gate.

Geographic-group qualification requires passing municipality and new-group assessments. Original-place and section performance is always scored on fixed supports and reported separately; those finer outputs do not inherit a group-level pass. Requiring recovery of every original section's hidden rates would defeat the purpose of evaluating a coarser reliable reporting unit. Their failures remain visible and limit the interpretation of fine allocations.

Only computationally sound fits contribute to pass decisions. Failed/warning jobs remain in availability denominators and their exploratory estimates remain exported. Held-out validation requires a frozen development selection lock. If no development procedure passes, no validation results may be invented. A simulation-only pass also cannot bypass the real prior-sensitivity and municipal-comparison gate.

Every sampling warning is scheduled for one prespecified longer-chain upgrade. For admission and method comparison, a completed upgrade replaces the short computation on the same dataset; it is not another independent replication. Original JSON results and `raw_fit_status.csv` retain every attempt. Effective tables include `original_status` and `status_source`; confirmation-phase summaries are separate computational diagnostics. Seed mismatches prevent promotion. Timeouts remain unavailable rather than being relabeled as accurate or statistically biased fits.

The supplementary information analysis compares fixed-penalty prediction of simulation error using direct design information, then adding population-bin indicators or continuous log population. It trains on development municipalities and evaluates held-out municipalities with equal municipality weighting. It requires multiple municipal designs and does not supply a causal explanation of reliability losses or replace threshold validation.

## Execution and artifact contract

`python -m elections.spatial_runner` provides prepare, group, profile, screen, select, validate, real, summarize and all stages. `scripts/run_spatial_pooling.py` orchestrates the complete workflow with explicit wall and worker-time budgets. Budgets stop new work honestly; timeouts are resource limitations, not statistical evidence of bias. Completed jobs resume after verifying frozen source and design hashes. A changed scientific procedure requires a separate experiment rather than selecting on held-out outputs.

- `manifest.json`: sources, hashes, frozen sample/splits, generators, models, priors, thresholds and seeds.
- `section_coordinates.csv.gz`, `coordinate_exceptions.csv.gz`: source metadata, statuses and reasons.
- `groupings/`, `group_inventory.csv.gz`, `section_group_membership.csv.gz`: reproducible labels, information, feasibility and shortlisted memberships.
- `jobs/`, `raw_fit_status.csv`: immutable job specifications, results, logs and original attempt statuses. Missing results and explicit failures are different.
- `simulation_metrics.csv.gz`, `fit_status.csv`: effective dataset-level cell/support scores and diagnostics after same-data computational upgrades. `flow_audits/` retains detailed first-replicate unit/cell checks.
- `selected_procedure.json`: immutable development-only selection. Empty candidates mean no selected threshold.
- `validation_checkpoints.json`: completed 100/500/1,000-replication admission looks, tied to the selected procedure. Live partial batches cannot authorize scale.
- `estimates.csv.gz`: actual completed observed-data expected flows, intervals, denominators, methods, supports and status.
- `municipal_comparison.csv`, `municipal_investigations.json`: common-electorate differences, prior sensitivity, flags and unresolved interpretations.
- `threshold_profiles.json`, `validation_gate.json`: configuration/bin decisions, including insufficient evidence. Resource limitations cannot become a pass.
- `report.html`, `visualization_data.json`, `visualization_config.json`: offline controls and exportable map data. Group points/networks are not catchment polygons. Missing diagnostics stay unavailable.

The detailed boundary source and original-result source hashes are recorded. Optional browser verification launches only the local report. No command deploys the experiment or overwrites the baseline/earlier pilot.
