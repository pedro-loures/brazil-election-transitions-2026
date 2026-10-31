# Polling-place partial-pooling pilot: execution results

Executed: 30 October 2026.

**Decision: do not scale.** The existing nationwide baseline is preserved. The new method was fitted only to the 12-municipality pilot.

## Findings and expansion decision

- 4/12 primary pilot fits fail the declared sampling diagnostics.
- 12/12 municipalities have material method disagreements unresolved by aggregate data.
- Initial 30-replicate simulation screen is insufficient to certify interval calibration; expansion requires at least 100 per relevant scenario.
- Mean expected-flow interval coverage is below 90% in: boundary, contextual, within_place.
- Hierarchical municipal RMSE exceeds 1.10 times the baseline in at least one scenario.

A successful fit or similarity to the baseline does not establish hidden-flow recovery. Material disagreements remain unresolved rather than being called evidence for either method. The comparison changes likelihood, priors and expected-margin calibration as well as geographic pooling; disagreements cannot be attributed solely to adding polling places.

## Geography and pilot

The audit retained 442,108 sections in 92,725 administrative place groups. It found 5,193 municipality/place-code combinations reused across zones. The median group has four sections; 54,293 have fewer than five. The experiment uses UF + municipality + zone + place code. Physical buildings and electorate membership were not independently verified.

| Municipality | Included sections | Places | Electorate coverage | Matrix distance | Max prior shift (% electorate) | Sampling | Investigation |
|---|---:|---:|---:|---:|---:|---|---|
| CODÓ / MA | 256 / 273 | 59 | 94.1% | 0.039 | 0.06 | diagnostic_warning | unresolved_model_dependence |
| MATÕES DO NORTE / MA | 30 / 30 | 11 | 100.0% | 0.075 | 0.23 | diagnostic_warning | unresolved_model_dependence |
| CONCEIÇÃO DOS OUROS / MG | 31 / 34 | 7 | 90.2% | 0.038 | 0.42 | ok | unresolved_model_dependence |
| BELA VISTA / MS | 65 / 67 | 18 | 96.5% | 0.083 | 0.22 | ok | unresolved_model_dependence |
| FELIZ NATAL / MT | 22 / 23 | 4 | 95.5% | 0.074 | 0.33 | ok | unresolved_model_dependence |
| CONCEIÇÃO DO ARAGUAIA / PA | 111 / 115 | 24 | 96.7% | 0.059 | 0.11 | diagnostic_warning | unresolved_model_dependence |
| SÃO JOSÉ DO EGITO / PE | 69 / 78 | 13 | 88.8% | 0.054 | 0.21 | ok | unresolved_model_dependence |
| FIGUEIRA / PR | 19 / 19 | 4 | 100.0% | 0.098 | 0.76 | ok | unresolved_model_dependence |
| CASIMIRO DE ABREU / RJ | 111 / 117 | 18 | 94.6% | 0.063 | 0.20 | ok | unresolved_model_dependence |
| VACARIA / RS | 135 / 151 | 38 | 89.3% | 0.087 | 0.12 | diagnostic_warning | unresolved_model_dependence |
| LEBON RÉGIS / SC | 29 / 30 | 9 | 97.0% | 0.095 | 0.75 | ok | unresolved_model_dependence |
| PEQUIZEIRO / TO | 15 / 16 | 6 | 93.3% | 0.068 | 0.78 | ok | unresolved_model_dependence |

## Known-flow simulation screen

Thirty repetitions per scenario use retained Lebon Régis first-round compositions and vary the transition process/nesting. Expected flows are the target; realized latent tables are retained separately. Counts, places, and cells within a repetition are dependent, so Monte Carlo standard errors are computed across repetitions. The 30-repetition screen can expose failures but cannot certify national calibration.

| Scenario | Method | RMSE (% electorate per cell) | 95% interval coverage | Coverage MCSE | Unavailable | Sampling warning fraction |
|---|---|---:|---:|---:|---:|---:|
| boundary | hierarchical | 0.777 | 87.5% | 0.7% | 0.0% | 100.0% |
| boundary | municipal_baseline | 1.347 | 85.5% | 1.8% | 0.0% | 0.0% |
| contextual | hierarchical | 1.598 | 86.3% | 1.1% | 0.0% | 100.0% |
| contextual | municipal_baseline | 2.848 | 45.8% | 0.6% | 0.0% | 0.0% |
| few_places | hierarchical | 0.702 | 97.3% | 1.0% | 0.0% | 100.0% |
| few_places | municipal_baseline | 1.021 | 91.8% | 1.5% | 0.0% | 0.0% |
| homogeneous | hierarchical | 0.664 | 98.5% | 0.4% | 0.0% | 100.0% |
| homogeneous | municipal_baseline | 0.853 | 91.8% | 1.2% | 0.0% | 0.0% |
| moderate | hierarchical | 0.955 | 96.3% | 1.1% | 0.0% | 100.0% |
| moderate | municipal_baseline | 1.603 | 80.2% | 2.4% | 0.0% | 0.0% |
| sparse | hierarchical | 0.736 | 96.5% | 1.2% | 0.0% | 100.0% |
| sparse | municipal_baseline | 1.413 | 89.7% | 2.0% | 0.0% | 0.0% |
| strong | hierarchical | 1.142 | 94.7% | 1.1% | 0.0% | 100.0% |
| strong | municipal_baseline | 2.731 | 73.2% | 1.9% | 0.0% | 0.0% |
| weak_design | hierarchical | 1.111 | 98.2% | 0.7% | 0.0% | 100.0% |
| weak_design | municipal_baseline | 2.141 | 90.8% | 1.2% | 0.0% | 0.0% |
| within_place | hierarchical | 3.759 | 67.2% | 1.6% | 0.0% | 100.0% |
| within_place | municipal_baseline | 2.253 | 88.7% | 1.7% | 0.0% | 0.0% |

Independent polling-place fits and sparse-place results, including all unavailable cases, are in `simulation_summary.csv`. Their ten-section/full-rank cutoff is an operational screen, not an identification theorem. No individual-level validation sample was available.

The ninth, two-place scenario was added in a documented addendum before its outcomes were generated. It changes none of the original selection, priors or warning thresholds. The original screen has a short sampling budget and its warnings remain visible.

### Longer-chain computational confirmation

The first three datasets in each of the contextual, within-place and boundary scenarios were refitted after screening, using four chains, 1,000 warmup and 1,500 retained draws per chain with different MCMC seeds. These are the same data, not nine extra independent validation repetitions. They check whether the screening failures persist with better computational diagnostics.

| Scenario | Datasets | Mean expected-flow coverage | Mean RMSE (% electorate/cell) | Fits passing diagnostics |
|---|---:|---:|---:|---:|
| boundary | 3 | 83.3% | 1.076 | 3/3 |
| contextual | 3 | 85.0% | 1.505 | 3/3 |
| within_place | 3 | 61.7% | 3.340 | 3/3 |

These targeted refits support a computational diagnosis, not a precise coverage estimate or a national validation claim. Their parameter diagnostics and protocol are in `confirmation/`; summary data are in `long_chain_confirmation.csv`.

## What was delivered

- `report.html`: offline municipality map with estimate/reliability color controls, municipal → place table, both methods' intervals, municipal disagreements and investigation notes, scatter/difference/distribution views, simulation evidence.
- `reliability.csv.gz`: expected flows, pointwise intervals and widths, denominators, data coverage, information warnings, prior sensitivity, heterogeneity and sampling diagnostics; local and municipal levels.
- `municipal_flow_comparison.csv`, `municipal_comparison.csv`: paired common-electorate comparison and flags. Inputs agree exactly; expected destination calibration differs by model. No interval-overlap agreement test is claimed.
- `municipal_investigations.json`: each municipality's alignment, design, boundary, sensitivity, variant diagnostics and largest descriptive local contributions. These are not leave-one-place-out causal or influence estimates.
- `fits/`: posterior parameter/local/municipal draws and parameter diagnostics for three prior variants per municipality.
- `simulation_metrics.csv`, `simulation_summary.csv`, `simulation_flow_summary.csv`, `simulation_flows.csv.gz`, `simulations/`: reproducible replicate and flow-level known-truth results, sparse strata, failures, Monte Carlo errors and runtime.
- `manifest.json`, `run.json`, `validation_gate.json`, `geography_audit.json`, `likelihood_audit.json`, `prior_predictive.json`: frozen provenance/configuration and diagnostic evidence.
- `visualization_data.json`, `visualization_config.json`, `municipal_comparison.png/.pdf`: reviewable data and standalone figures.

## Limitations and next changes

The normal margin likelihood is an approximation. Exact small-count checks show meaningful errors; binary projection checks at larger counts do not establish accuracy of the full posterior. Expected flow intervals are conditional on this approximation, priors, grouping, and population closure. Tight intervals can be driven by assumptions. Structural zeros may need explicit prior mass or a different interval/decision formulation. Contextual and within-place misspecification require further model development or narrower claims. A second simulation design is needed to assess transfer beyond Lebon Régis. Scaling is withheld under the agreed validation gate.

See [statistical specification](docs/hierarchy_specification.md) and [academic review](LITERATURE_REVIEW.md) in the project root. The [Wakefield et al. (2011) convolution/approximation comparison](https://doi.org/10.1002/sim.4214) motivates explicit likelihood checks; [Morris et al. (2019)](https://doi.org/10.1002/sim.8086) motivates known-truth evaluation with Monte Carlo error. These sources support the workflow, not a claim that this pilot is validated.

## Reproducibility checks

Frozen source hashes unchanged: **True**. All pilot municipality map codes match existing verified geography. Draw-by-draw municipal aggregation is checked during export. The Python tests and browser checks are recorded in the execution handoff.
