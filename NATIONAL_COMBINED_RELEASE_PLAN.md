# Nationwide combined model: run and GitHub Pages release

User-authorized release, 30 October 2026: replace the primary website after a nationwide run. Keep the current site live until that run, publication build and verification finish. Publication is an experimental release, not a declaration that the model has passed independent statistical validation.

## What changes

The primary estimates will come from the combined geographic–behavioural Bayesian model. Sections remain observations. Nearby polling buildings are grouped toward 10 sections with a maximum 5-km group diameter; co-located sections remain together. Two behavioural regimes and their transition matrices are inferred jointly. Composition covariates and Dirichlet–multinomial moment overdispersion are shared with the tested model family. Regime membership uncertainty enters posterior predictions. The margin likelihood is a multivariate normal approximation, and all priors/settings remain those of the completed pilot.

The original constrained municipal estimator remains available as a historical baseline. The replacement site defaults to the new model and never fills missing new estimates with old ones. A same-electorate baseline refit supplies a descriptive disagreement metric. Similar estimates do not establish accuracy.

## National preparation

1. Reuse the audited official population/coordinate data and the existing matched two-round electorate. Freeze input hashes, code hashes, seeds, versions, per-city ordering and sampler budgets in a separate national manifest.
2. Enumerate every domestic TSE municipal unit, including units without usable coordinates. Exclude unresolved/missing locations from geographic fitting and export counts, electorate coverage and reasons. Coordinates identify polling buildings, not voter residences.
3. Store compact immutable municipal input shards. Retain first-round composition information, design rank/conditioning and population bins. Population bins describe coverage/performance; they do not change the fixed model or supply validated thresholds.

## Run strategy

4. Fit the combined model separately in every municipality, initially using four chains, 700 warmup and 700 retained draws per chain, acceptance 0.97 and depth 11. Use up to eight isolated workers with disjoint CPU affinities. Include representative small/large cities early to improve resource estimates.
5. Give sampling-warning or timeout cases one longer attempt: four chains, 1,000 warmup, 1,500 retained draws, acceptance 0.99 and depth 12. Preserve both attempts. Primary and longer runs use identical observed data; they are not extra independent datasets. Use the longer numerically valid fit if available; otherwise retain an available primary fit as explicitly provisional, or record unavailable.
6. Enforce per-attempt resource limits, storage reserves and resumable atomic outputs. Resource failure is not evidence of statistical bias. Terminal records are required for every municipal unit before publication; unavailable cases stay unavailable.
7. Sum section expected-flow draws before calculating municipal intervals. Save municipal draws for audit and legitimate later aggregation. Do not force posterior expected destination totals to equal observed totals. Export their differences and keep observed totals visibly distinct.

## Reliability and presentation

8. Show estimates, pointwise conditional posterior intervals, origin denominators, coordinate/electorate coverage, sampling diagnostics, prior-related assumptions and baseline disagreement. Warning fits have explicit provisional labels; unavailable intervals remain absent. Passing computation is not validation of hidden flows.
9. The primary nationwide map can be coloured by estimated transition rate, interval width, data coverage, computation or baseline disagreement. Provide municipality search and a selected-flow inspector. Preserve the former explorer at `baseline.html` and link to a readable changes/methods/results page.
10. Publish the completed pilot evidence alongside the national outputs: 60 known-flow development datasets, low convergence rates for the combined model, broad intervals and examples of shared error despite model consensus. National bootstrap and prior-variant sensitivity are not invented where they have not been run. Full five-bin held-out validation remains outstanding.

## Commit, release and rollback

11. Push the implementation, this plan, strategies, dependencies, tests and release tooling to `main` after local checks. This code commit does not replace the live primary map. Preserve the existing national result snapshots and original model assets.
12. After the nationwide fit finishes, build a candidate site in an isolated checkout. Require complete municipal accounting, input/code hashes, flow conservation, finite nonnegative matrices, sensible interval bounds and draw-before-quantile checks. Check every link and test the site at a GitHub project-site prefix, including provisional/unavailable cases and reliability selectors.
13. Commit the national data, provenance, documentation and replacement page to `main` using an ordinary fast-forward push. Do not force-push or overwrite unrelated remote changes. Verify GitHub Pages serves the new release identifier and that the baseline archive still opens. A failed build or push leaves the current primary site intact and records a release failure for investigation.
14. Roll back publication by reverting the release commit; retain the research artifacts and code. No additional user approval is required: the user explicitly authorized the main-branch push and Pages replacement after the nationwide run.

## Reproduction and progress

Run `python -m elections.national_combined prepare`, then `python -m elections.national_combined run --workers 8`. Inspect `results/2026/national_combined/execution_state.json`, `manifest.json` and the per-city attempts. The authorized background release driver resumes completed work and publishes only after the checks above. Runtime estimates are updated from completed attempts; a full run can take days and is not represented as already complete.
