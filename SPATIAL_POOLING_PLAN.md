# Population-stratified spatial pooling of electoral sections

Accepted specification, 30 October 2026. Execution status and limitations are recorded separately in `SPATIAL_POOLING_RESULTS.md`; a completed software pipeline is not statistical validation.

## Objective and fixed decisions

Evaluate five logarithmic population bins → geolocation → conditional reliability thresholds → proximity grouping → independent validation → scaling decision. Preserve existing national results and the previous pilot. Write experimental artifacts to `results/2026/spatial_pooling/`.

Estimate expected closed-electorate 5×4 transitions, with pointwise intervals. Keep section observations within pooling groups; compare literal count aggregation separately. Individual ballots and campaign effects remain unobserved. A universal vote minimum is not assumed; no supported threshold is a valid result.

## Geography and sample

Reuse the audited IBGE population snapshot and bins: 857–5,775; 5,776–38,919; 38,920–262,282; 262,283–1,767,520; 1,767,521–11,911,337. Review coordinates using detailed official boundaries and register addresses, including the 3,559 simplified-polygon exceptions, relocations, aggregation, identifier collisions and precision. Use explicit verified/unresolved/missing statuses; verified means register/boundary consistency, not independent confirmation of election-day buildings. Never impute municipal centroids.

Select ten municipalities per bin 1–4, balancing regions and first-round design/coverage/spacing, and all eight in bin 5 (48 total). Split bins 1–4 six development/four held-out and bin 5 five/three. Freeze selection and seeds before generating outcomes. Add Lebon Régis as an external historical check if absent. Profile progressively larger municipalities; resource-limited designs remain unvalidated.

## Grouping and comparators

Inventory electorate, turnout, origin counts, section/site counts, composition variation, rank/conditioning and diameter. Candidate section targets: 5, 10, 20, 40, 80, 160; maximum diameters: 1, 5, 20, 50 km. Group co-located sections together using a sparse geodesic neighbour graph, deterministic merging and tie-breaking. Remain inside the municipality; retain zone in identifiers. Do not force distant mergers; export overshooting, undersized and isolated groups. Grouping cannot use second-round results or inferred transitions.

Compare constrained municipal WLS, matched Bayesian common matrix, administrative hierarchy, geographic hierarchy, administrative/geographic hierarchies with the same contextual/overdispersion extension, and literal summed-count aggregation on development data. Audit likelihoods and priors. Retain at most three development-selected configurations per bin; prefer the most local passing configuration.

## Simulation and acceptance

Generate individual transitions at section level before grouping. Include homogeneous, smooth/strong spatial patterns, sharp boundaries, proximity unrelated to behaviour, within-building differences, composition-related behaviour, sparse origins, finalist switching, zero flows and coordinate errors. Evaluate closure/turnover separately.

Start development with 30 independent datasets per bin/scenario. Freeze the complete selected pipeline before held-out evaluation. Start validation with 100 independent datasets per bin/scenario, extend to 500 then 1,000 if necessary. Report fixed-support municipality, original-place and section results, not only new groups. A municipal pass does not certify local reliability.

Defaults: R-hat ≤1.01; bulk/tail ESS ≥400; zero divergences/tree-depth saturation. Target 95% interval coverage with lower Monte Carlo confidence bound ≥90% and MCSE ≤1 percentage point. Cell RMSE ≤2% of relevant electorate; origin-rate RMSE ≤10 percentage points for origins ≥100; RMSE ratio to baseline ≤1.10; median 95% rate-interval width ≤20 percentage points; unavailable fits ≤5%. Investigate prior shifts >2% electorate. These are study choices, not academic universal thresholds. Assess rare/zero flows separately. Simulation datasets, not correlated cells, are the Monte Carlo units.

Investigate real municipal allocation distance >0.05, supported-origin rate differences >10 percentage points, or key-flow shifts >2% electorate. Agreement is not truth. Scale only independently passing information/population regimes; otherwise record do-not-scale or insufficient-evidence decisions.

## Deliverables and verification

Export source/configuration manifests, frozen splits, grouping membership/feasibility, coordinate statuses/coverage, five-bin threshold profiles, simulations/calibration/resource costs, municipal comparisons and investigations. Provide an offline interactive estimate/reliability map with selectable interval width, data coverage, prior sensitivity, computation and disagreement. Show groups as points/networks, not catchment polygons. Label calibration evidence by scenario/support and keep missing values separate from zero.

Test identifiers, distances/diameters, deterministic grouping, origin conservation, posterior aggregation before quantiles, held-out isolation, boundary summaries, failure denominators, resumption hashes and UI controls. Verify original outputs unchanged.

Academic basis and qualifications: [Bradley et al.](https://arxiv.org/abs/1502.01974), [Gnaldi et al.](https://arxiv.org/abs/1509.03055), [Cawley & Talbot](https://www.jmlr.org/papers/v11/cawley10a.html), and `SPATIAL_POOLING_FEASIBILITY.md`.

## Subsequent extension: behavioural pooling and cross-model stability

The user has requested behavioural pooling, resampling stability and comparison of agreement across models. Their design and separate execution protocol are recorded in [MODEL_AGREEMENT_EXTENSION.md](MODEL_AGREEMENT_EXTENSION.md). This extends the research plan; it does not retrospectively alter the frozen spatial experiment, its acceptance rules or its results. Implementation and completed evidence are reported separately.
