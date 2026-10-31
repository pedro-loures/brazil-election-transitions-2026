# Spatial pooling: execution results

## Current decision

The spatial experiment is isolated from the original national results. Statistical validation and computation are reported separately.

| Population bin | Decision |
|---|---|
| 1 | insufficient evidence |
| 2 | insufficient evidence |
| 3 | insufficient evidence |
| 4 | insufficient evidence |
| 5 | insufficient evidence |

## Completed data and software work

- Frozen outcome-blind sample: 48 municipalities; independent development/validation splits.
- Detailed IBGE boundary/register consistency: {'verified_register_boundary': 438142, 'unresolved': 2423, 'missing': 1543}; 1724 simplified-map exceptions resolved.
- All 24 target/diameter combinations inventoried per sample municipality, including infeasible/undersized groups.
- Matched municipal, administrative, geographic, contextual/overdispersion and literal-aggregation model arms implemented.
- Section-level known-flow generators, fixed-support scoring, independent-stream validation, MC precision and fail-closed gates implemented.
- Offline interactive map/report includes estimates, widths, coordinate coverage, sensitivity, computation and municipal disagreement.
- Frozen original source hashes unchanged: **True**.

## Executed fits and remaining evidence

Raw fit-attempt statuses: `{'diagnostic_warning': 369, 'ok': 127, 'too_few_sections_or_rank_deficient': 38, 'resource_timeout': 21}`. See `raw_fit_status.csv` for original attempts and `fit_status.csv` for effective computation after same-data upgrades.

| Phase | Bin | Scenario | Method fits | Generated datasets | Municipal designs |
|---|---:|---|---:|---:|---:|
| confirmation | 1 | within_building | 12 | 3 | 3 |
| development | 1 | within_building | 450 | 30 | 6 |
| profile | 1 | observed | 9 | observed | 3 |
| profile | 2 | observed | 9 | observed | 3 |
| profile | 3 | observed | 9 | observed | 3 |
| profile | 4 | observed | 9 | observed | 3 |
| profile | 5 | observed | 9 | observed | 3 |
| real | 1 | observed | 10 | observed | 10 |
| real | 2 | observed | 10 | observed | 10 |
| real | 3 | observed | 10 | observed | 10 |
| real | 4 | observed | 10 | observed | 10 |
| real | 5 | observed | 8 | observed | 8 |

Confirmation datasets repeat the corresponding development data and are not extra independent validation replications.
See `simulation_metrics.csv.gz` and `simulation_summary.json` for actual executed datasets. Missing jobs/scenarios are not treated as successful replications. A geographic shortlist is not a validated reliability threshold.
Development outcomes do not certify interval coverage. Held-out validation requires a frozen selection lock; no supported selection means expansion is withheld.
Full certification remains incomplete. Inspect phase counts and gates for missing development scenarios, selection, held-out validation, prior variants or unresolved failures; implemented stages are not automatically completed evidence.

## Interpretation and reproducibility

Coordinates identify polling sites, not voters’ residences. Verified means source and detailed-boundary consistency, not field confirmation. Equal electorate sizes do not establish identical voters.
The extension uses composition covariates and Dirichlet-multinomial origin-row overdispersion with an approximate normal margin likelihood; these are additional assumptions, not a cure for ecological nonidentification.
Overdispersion changes margin uncertainty; it does not reconstruct distinct latent section matrices. Reported flows use fitted mean probabilities. Section-level hidden-rate recovery remains an explicit robustness test.
Local and municipal expected flows are summed draw by draw before intervals. A municipal pass cannot certify local flows. Exact zero flows receive separate boundary summaries.
Run `.venv-hierarchy/bin/python -m elections.spatial_runner --help` for resumable stages and `python scripts/build_spatial_report.py` to rebuild this report.
The accepted specification is `SPATIAL_POOLING_PLAN.md`; the feasibility/literature qualifications remain in `SPATIAL_POOLING_FEASIBILITY.md`.
