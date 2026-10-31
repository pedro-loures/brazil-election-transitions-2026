# Feasibility assessment: population-stratified spatial pooling

Assessed 30 October 2026. **Verdict: feasible as a staged experiment, with changes to the threshold and aggregation design. No new reliability threshold or spatial transition model has yet been validated.**

The source-data audit and coordinate linkage below are complete. Threshold calibration, proximity-based grouping, new model fits and scaling decisions are proposed next work. The existing national results and the failed polling-place pilot remain intact.

## 1. What the existing evidence says

The hypothesis that a single fitting rule is inappropriate across Brazil is plausible and worth testing. In the current retained data:

| Quantity | 10th percentile | Median | 90th percentile | Full range |
|---|---:|---:|---:|---:|
| Registered electorate per section | 230 | 325 | 387 | 20–534 |
| First-round turnout per section | 181 | 256 | 308 | 9–477 |
| Retained sections per municipality | 10 | 30 | 135 | 3–22,911 |

These describe the existing retained sections/municipal units, not every registered section in Brazil. Municipal differences in the **number of observations** are much larger than the central variation in individual section sizes. Total population, registered electorate, turnout and the number of sections must remain separate variables.

The previous simulations do **not** establish municipality-size variation as the principal cause of failure: most scenarios kept the same Lebon Régis first-round counts and sizes. Changing the transition process alone yielded these results:

| Scenario | Polling-place interval coverage | Municipal interval coverage |
|---|---:|---:|
| Homogeneous transitions | 98.5% | 91.8% |
| Strong between-place differences | 94.7% | 73.2% |
| Composition-related transitions | 86.3% | 45.8% |
| Differences between sections within a place | 67.2% | 88.7% |

These are averages over known expected-flow cells in 30 simulated datasets per scenario. Short Bayesian runs had computational warnings; longer converged refits of three within-place datasets still gave 61.7% average coverage. The previous study supports further work on **heterogeneity and model specification**, alongside size stratification. It cannot establish national accuracy. See [the pilot results](HIERARCHY_PILOT_RESULTS.md).

## 2. Five logarithmic population bins are implementable

I downloaded the official [IBGE 2026 population workbook](https://ftp.ibge.gov.br/Estimativas_de_Populacao/Estimativas_2026/POP2026_20261029.xlsx), with reference date 1 July 2026 and snapshot 29 October 2026. All **5,571 domestic TSE municipal units** matched through the existing official TSE–IBGE code crosswalk. Brasília is included as the corresponding municipal analysis unit.

For population `P`, define six edges:

```
edge[j] = exp(log(P_min) + j*(log(P_max)-log(P_min))/5), j=0,...,5
```

Intervals are left-closed/right-open, except the final interval includes the maximum. This is equal width in log population, **not** five quantile groups. Integer ranges and the actual audit are:

| Bin | Resident population range | Municipal units | Median retained sections per municipality |
|---|---:|---:|---:|
| 1 | 857–5,775 | 1,523 | 12 |
| 2 | 5,776–38,919 | 3,160 | 35 |
| 3 | 38,920–262,282 | 770 | 148 |
| 4 | 262,283–1,767,520 | 110 | 770 |
| 5 | 1,767,521–11,911,337 | 8 | 4,325.5 |

São Paulo shares the largest bin with Curitiba, Manaus, Belo Horizonte, Salvador, Fortaleza, Brasília and Rio de Janeiro. Logarithmic binning resolves the proposed singleton problem here, but **does not balance the number of municipalities**. The last bin has only eight municipal designs; repeated simulations of them do not create additional independent municipalities.

Use these five bins as the primary reporting and calibration strata. Also assess whether continuous log population, section count, origin composition and rural/urban spacing explain performance better. This is a sensitivity analysis, not a replacement of the requested five-bin analysis. Size-specific thresholds are a hypothesis to test, not an academic result established for this dataset.

## 3. Geolocating the sections is practical

I downloaded the official [TSE 2026 polling-place register](https://dadosabertos.tse.jus.br/dataset/eleitorado-2026/resource/300626b4-2b24-4d2e-b4fc-46b569cfffe5). Its national CSV contains section/round identifiers, polling-place identifiers, addresses, latitude, longitude, and section-aggregation fields. The downloaded register records generation on **25 October 2026 at 15:27:44**. Its retrospective round records must still be checked against election-day locations.

Using **UF + municipality + zone + section + round + polling-place code**, the preliminary join finds coordinates within Brazil's broad coordinate range in both rounds for **440,565 of 442,108 retained sections (99.65%)**. The remaining 1,543 have no such valid coordinate pair. This is coordinate availability, **not** independently verified physical location or statistical accuracy.

The audit exports a check against the existing simplified municipality polygons. **3,559 coordinate-linked sections fall outside the corresponding simplified polygon** and need review against unsimplified geometry, border cases and official addresses; they must not be automatically declared wrong. The other 437,006 linked sections pass that limited containment check. Also check coordinate precision, multiple place codes sharing a building, transfers/relocations, main/aggregated sections, duplicate records and source versions.

All sections in one administrative polling-place group currently share the same registered coordinate. Therefore proximity cannot distinguish those sections spatially. These are polling-building coordinates, not voter residences or electoral catchment boundaries. Do not infer individual residential locations from them.

Missing or suspect coordinates require explicit statuses and a sensitivity analysis. Do not fill them with municipal centroids. Preserve a nonspatial comparison for excluded locations and report how exclusions change coverage in each size bin.

## 4. Replace one vote-count threshold with a conditional information requirement

Estimate a threshold **profile** within each population bin, rather than assume a universal minimum votes per section:

- Number of distinct retained section observations in a proposed group.
- Total retained electorate and the size of each first-round origin category.
- Variation, rank and conditioning of the first-round composition design.
- Spatial diameter, separation of sites and plausible internal heterogeneity.
- Interval calibration, flow error and sensitivity under relevant simulated processes.

The municipal/bin population stratifies the experiment; the transition denominator remains the actual retained origin electorate. A large total can conceal a tiny origin group or near-identical compositions that provide little information about specific flows.

Search candidate group sizes and radii on **development simulations**. Evaluate the entire grouping-plus-estimator procedure. Select the smallest/most local admissible group size that meets calibration and error requirements with useful interval width. If no candidate works for a bin/information stratum, report **no supported threshold**. Do not force the existence of an ideal minimum or assume accuracy improves monotonically as groups grow.

The smallest bin has a median of only 12 retained sections per municipality. Some municipalities cannot form several well-informed local groups while retaining municipal boundaries. Their valid outcome may be one pooled group, broad uncertainty, or insufficient information—not a local reliability claim.

## 5. Group nearby observations without throwing their information away

The primary implementation should assign sections/sites to geographic pooling groups **while retaining each section's observed margins in the likelihood**. Summing 20 sections into one count vector does not provide 20 independent section observations; it removes the section-to-section variation used in ecological regression. Compare literal count aggregation as a separate experimental arm, not an assumed improvement.

Use a sparse distance/neighbour graph over unique validated polling sites. Keep co-located sections together as the primary grouping rule; they remain separate observations. Sections with identical coordinates offer no defensible distance-based ordering among themselves. Compare the current grouping with alternative group boundaries, without pretending that arbitrary splits at one building are geographic distinctions.

Constrain the partition to:

1. Stay within the municipality and preserve the paired electorate. Groups may cross electoral-zone boundaries within the municipality, but identifiers retain the zone to prevent code collisions.
2. Meet the bin-specific information requirement where feasible, with a bounded geographic radius/diameter and a documented tolerance for overshooting the target count.
3. Respect available barriers or urban/rural structure; use distance-based graph connectivity, not invented catchment contiguity. Test sensitivity to graph construction and distance caps.
4. Avoid forcing distant or behaviorally incompatible sites together merely to reach a count target. Flag geographically isolated or infeasible groups.
5. Build groups without second-round results or inferred real-world flows. Any use of first-round composition in grouping must be included in end-to-end validation. Do not optimize for identical first-round shares: that can remove design variation needed for transition estimation.

A practical objective minimizes distance and deviation from the validated size target, subject to those information/feasibility constraints. Spatial regionalization heuristics supply computational precedents; no solver can guarantee that nearby schools have homogeneous voter behavior.

**Important:** increasing a geographic group's size could make the earlier within-place failure worse. Compare a parsimonious section-level variation/overdispersion extension and composition-related effects. Do not simply replace the old polling-place label with a larger cluster label while retaining an unsupported homogeneity assumption. Added latent effects need their own identifiability, prior and likelihood checks.

## 6. Validation must separate geography changes from model changes

Use at least these comparators on identical inputs:

| Comparator | Purpose |
|---|---|
| Existing municipal constrained estimator | Historical benchmark; not presumed ground truth |
| Bayesian municipal common-rate model with matched likelihood/priors | Distinguish locality changes from estimator/likelihood changes |
| Existing administrative polling-place hierarchy | Direct comparison to the failed pilot |
| Adaptive geographic groups, section observations retained | Test the proposed grouping effect |
| Geographic groups with a validated residual-variation/contextual extension | Test whether correcting the observed failure helps |
| Administrative groups with the same extension | Separate model improvements from benefits of geographic regrouping |
| Literal summed-count aggregation, on a manageable subset | Measure the information cost of actual aggregation |

The matched Bayesian comparator is a proposed addition; it has not yet been implemented. Do not assume all expanded models are estimable. Profile cost and simplify before attempting a large benchmark.

If geolocation exclusions change eligibility, refit all comparators on the same common subset in a new directory. Keep original/full-coverage results separate. Expected-flow comparisons must use the same estimand and switching assumptions; preserve the distinction between calibrated expected destination totals and stochastic-model predictions.

Choose multiple municipal templates in **each of the five population bins**, with region, density, coverage, origin sparsity and composition variation represented. Include small/isolated municipalities and all eight largest-bin municipalities in the design inventory. Hold out municipal designs or use nested leave-municipality-out assessment where the bin is small. Report uncertainty about transfer to other municipalities; do not count repeated simulations as new geographic evidence. The previous single-city simulation template is insufficient.

Simulate known transitions at the original section level **before grouping**, preserving realistic first-round margins. Include:

- No, moderate and strong spatial dependence, plus no relationship between proximity and transition behavior.
- Smooth spatial patterns, sharp local boundaries and nonspatial within-building section heterogeneity.
- Composition-correlated transitions; weak designs and tiny/absent origins.
- True zero/near-zero flows and genuine finalist switching.
- Coordinate errors/missingness, relocations and alternative graph partitions.
- Electorate mismatch/turnover as a separate population-closure sensitivity.

Run grouping and threshold selection using only information available to the estimator. The simulator's true flows are reserved for scoring, never supplied to clustering.

Tune thresholds/model choices on development simulations; freeze the procedure, priors and criteria; then evaluate on new simulation seeds and held-out municipal designs. A threshold chosen and evaluated on the same simulations will give optimistic results.

Report signed bias, MAE/RMSE, pointwise interval coverage, interval width, failures, computation and prior sensitivity **by bin, scenario and supported flow**. Retain rare-origin/zero-flow results separately. Use one-sided uncertainty summaries where appropriate for boundary targets, with separate validation; do not hide zero-flow failures in a grand mean.

Compare accuracy on fixed supports—municipalities and original sites/sections as applicable—as well as the newly constructed groups. Otherwise larger groups can appear better merely because averaging hides errors. Calculate simulated truth for each candidate group by summing original section truth. Real-data local movements remain unobserved.

Monte Carlo uncertainty must use independent simulation datasets as units, with dependence among flow cells and places respected. Start with a small falsification screen, then at least 100 independent repetitions per relevant bin/scenario for surviving candidates; extend based on Monte Carlo precision. For one Bernoulli coverage indicator, about 500 repetitions give roughly one percentage-point MC standard error near 95% coverage. That calculation does not treat correlated cells as independent, nor prescribe an affordable total workload. More repetitions do not cure an unrepresentative template set.

## 7. Conditions for scaling

Before the new simulations, freeze substantive flow-error tolerances, meaningful interval widths, prior sensitivity limits, computational budgets and grouping rules. Carry forward the earlier convergence/ESS/divergence requirements and expected-flow comparison diagnostics, with the following additions:

- Target approximately 95% pointwise coverage; retain 90% as an explicit minimum floor and require Monte Carlo uncertainty small enough to assess that floor. Narrow width alone is never a pass.
- Meet absolute error tolerances for key flows as well as comparisons with other methods. Beating an unreliable baseline is insufficient.
- Do not accept a bin solely because its average looks good: investigate supported flows, municipal templates, sparse cases and critical heterogeneity scenarios separately.
- A material failure under within-building or contextual variation must either be resolved or excluded from the stated application scope with evidence. Larger groups alone are not a resolution.
- Investigate municipal disagreement on the common electorate. Agreement with the baseline is not ground truth; disagreement may reflect improvement, estimator differences, or failure.
- Validate sensitivity to bin boundaries, grouping seeds, geographic radius, coordinate omissions and priors. Record actual membership, target overshoot and computational cost.
- Profile São Paulo and other large cities. Their full-size computation is much larger than the previous 893-section pilot. A small subsample cannot certify full-city performance.

Scale only the population/information regimes that pass independent validation. A nationwide claim requires evidence for all applicable regimes and explicit treatment of insufficient-information/missing-coordinate cases. Model accuracy in real municipalities remains conditional until independent transition information is available.

The final interface should retain the requested estimate/reliability map selector and add population bin, group membership, original section count, origin counts, geographic diameter, coordinate-validation status and calibration scope. Show group points/networks as analysis groups, not verified electoral catchment polygons. No single universal confidence score should replace the individual diagnostics.

## 8. Academic basis: support and limitations

| Primary academic source | What supports the proposal | What it does not establish |
|---|---|---|
| Duque, Anselin & Rey (2012), *The Max-p-Regions Problem*, J. Regional Science 52, 397–419. [DOI](https://doi.org/10.1111/j.1467-9787.2011.00743.x); [author-hosted full paper](https://sergerey.org/gph596s16/pdfs/Duque2012.pdf) | Spatially constrained grouping with minimum extensive-attribute thresholds and heterogeneity objectives has an established computational formulation. | Its thresholds are predefined; it does not discover a reliable minimum for Brazilian voter transitions. Adapting area adjacency to polling-point graphs is our design choice. |
| Bradley, Wikle & Holan (2017), *Regionalization of Multiscale Spatial Processes by Using a Criterion for Spatial Aggregation Error*, JRSS B 79, 815–832. [DOI](https://doi.org/10.1111/rssb.12179); [author preprint](https://arxiv.org/abs/1502.01974) | Regionalization can be evaluated with statistical aggregation-error criteria. | Count-based regionalization is not protected from ecological fallacy. CAGE is a different spatial-process framework, not a ready-made validation theorem for our transitions. |
| Gnaldi, Tomaselli & Forcina (2018), *Ecological fallacy and covariates*, International Statistical Review 86, 119–135. [DOI](https://doi.org/10.1111/insr.12244); [author preprint](https://arxiv.org/abs/1509.03055) | Composition-related heterogeneity and covariates deserve explicit modeling and testing. | Population or proximity alone does not remove contextual bias; useful identification can remain weak. |
| Cawley & Talbot (2010), *On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation*, JMLR 11, 2079–2107. [Original article](https://www.jmlr.org/papers/v11/cawley10a.html) | Threshold/grouping selection needs assessment on independent data or a nested evaluation procedure. | This is general model-selection evidence, not validation of a particular spatial clustering rule. |
| Morris, White & Crowther (2019), *Using simulation studies to evaluate statistical methods*, Statistics in Medicine 38, 2074–2102. [Original open article](https://pmc.ncbi.nlm.nih.gov/articles/PMC6492164/) | Prespecify mechanisms, estimands and metrics; report failures and Monte Carlo uncertainty. | Neither a fixed repetition count nor a single successful simulated design establishes national reliability. |
| Wakefield et al. (2011), *Bayes computation for ecological inference*, Statistics in Medicine 30, 1381–1396. [Original paper](https://sites.stat.washington.edu/adobra/Files/Papers/wakefield-dobra-et.pdf) | Explicit margin likelihoods, approximation checks and auxiliary individual evidence are important. | More aggregation or a spatial hierarchy cannot be assumed to repair identification or likelihood-approximation failures. |

These sources support components and warn about interpretation; none validates the five specific population bins, an ideal vote-count threshold, or this proposed Brazilian study. Original papers/preprints were examined; publisher bibliographic records distinguish preprint and journal dates.

## 9. Execution sequence and saved artifacts

1. **Complete:** source downloads, population join, exact five logarithmic bins, administrative coordinate candidates and initial spatial consistency audit.
2. **Next:** review location exceptions; inventory section-level information and feasible groups in each bin; freeze representative development/test templates and resource budgets.
3. **Then:** run a controlled screen comparing current and residual-variation models; select candidate threshold profiles on development data.
4. **Then:** build and test proximity groups while retaining section observations, including a literal-aggregation comparison and sensitivity to grouping boundaries.
5. **Then:** independently validate the complete selection/grouping/model pipeline; build reliability maps; decide on scaling separately by regime.

The completed audit is reproducible with `python scripts/audit_spatial_feasibility.py` after the two public source files have been cached. It requires pandas, NumPy, openpyxl and Matplotlib. Source URLs, byte sizes and SHA-256 hashes are in `data/raw/spatial_feasibility/manifest.json`.

Files in `results/2026/spatial_feasibility/`:

- `municipality_population_bins.csv`, `population_bin_summary.csv`: complete population joins and bin definitions/counts.
- `section_coordinate_candidates.csv.gz`: retained sections with round-specific coordinate candidates, source addresses/aggregation metadata, population bin and simplified-mesh consistency flag.
- `coordinate_coverage_by_bin.csv`, `register_inventory.json`, `audit.json`: geographic coverage, source-generation details and audit scope.
- `population_unmatched.csv`: empty-data audit table; all 5,571 joins succeeded.

No threshold-calibration simulation or new spatial transition fit is claimed by these audit files. The previous national estimates have not been replaced.
