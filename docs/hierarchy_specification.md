# Polling-place pilot: statistical specification and execution

Date: 30 October 2026. The frozen experiment is `results/2026/hierarchy_pilot/manifest.json`.

## What the model estimates

Sections are observations; administrative groups are **UF + TSE municipality + electoral zone + polling-place code**. This prevents collisions across zones. It does not establish that a group is one physical building, and no polling-place catchment polygons or verified coordinates are available. Maps therefore use the existing officially joined municipality polygons. Local results are available in a table.

The five origins are Lula, Flávio, other valid candidates, blank/null, and abstention in round one. The four destinations omit other candidates in round two. The closed electorate comprises exactly the sections retained by the original national run, including its technical-null classification. Equal electorate counts remain a population-closure assumption, not evidence that the same individuals stayed registered.

Let `x[s,g]` be first-round origin counts. Conditional on local probabilities, unobserved row counts follow independent multinomials:

```
T[s,g,:] ~ Multinomial(x[s,g], P[place(s),g,:])
y[s,:] = sum_g T[s,g,:]
log(P[p,g,k]/P[p,g,abstention]) = mu[g,k] + tau*z[p,g,k]
mu[g,k] ~ Normal(0, mu_sd)
z[p,g,k] ~ Normal(0, 1)
tau ~ HalfNormal(tau_scale)
```

There are 15 municipal reference logits and 15 deviations per place, with one regularized heterogeneity scale per municipality. Municipalities are fitted separately; within each, municipal logits, deviations, and scale are inferred **jointly**. There is no fixed empirical prior fitted to the same outcomes first. With few places, the scale will depend on its prior. The reference destination is abstention; priors on reference logits are not exchangeable across destinations. The sensitivity analysis changes both their spread and the deviation scale.

Primary priors: `mu_sd=2`, `tau_scale=0.5`. Tighter pooling uses `2, 0.25`; wider priors use `3, 1`. These are transparent modeling choices, not priors established by Brazilian individual-level evidence. Neutral logits impose no retention preference. `prior_predictive.json` records boundary probabilities and scale ranges before conditioning on outcomes.

Primary fits allow all finalist switching. The existing national no-switch fit remains a separate assumption sensitivity. It is not an observed flow restriction.

## Likelihood and computation

The exact margin likelihood sums probabilities of every latent table with the observed column totals. Enumerating 5×4 tables for hundreds of people in every section is impractical for this pilot. The implementation uses a multivariate normal approximation for the **first three column counts**, with the fourth implied by the electorate:

```
E[y[s,k]] = sum_g x[s,g] * P[p,g,k]
Cov(y[s,k], y[s,l]) = sum_g x[s,g] *
    (1[k=l]*P[p,g,k] - P[p,g,k]*P[p,g,l])
```

Only `1e-6` diagonal jitter is added for numerical stability. There is no fitted residual overdispersion. The likelihood is a density approximation on integer observations, not a multinomial likelihood applied to fictitious observed flows. It can be poor near support boundaries or when expected category counts are small.

`likelihood_audit.json` compares its moments to exact four-destination convolution at N=8 and N=20. It also compares continuity-corrected binary projections with exact convolutions at N=20,100,300,600. The normalized small-grid comparison and binary projection check **do not prove accurate full posterior inference at Brazilian section sizes**. In particular, the fitted density does not itself apply binary continuity correction. Tiny-count errors remain reasons for caution, not implementation tests to suppress.

NumPyro NUTS samples the joint posterior in float64, with noncentered place effects. The pilot uses four chains, 700 warmup and 700 retained draws per chain, acceptance target 0.95. ArviZ reports rank-normalized R-hat and bulk/tail effective sample sizes. The declared final diagnostic targets are R-hat ≤1.01, both ESS ≥400, no divergences, and no maximum-tree-depth saturation. Failure is exposed rather than converted to a reliable-looking point estimate. Sampling diagnostics assess computation under the chosen approximate model; they do not verify individual-flow accuracy.

The initial simulations use two chains, 300 warmup and 400 retained draws per chain to screen for failures. Their smaller sampling budget is explicitly recorded. They are not a substitute for the four-chain real-data diagnostics.

## Expected flows, intervals, and comparison

Each posterior draw gives expected local counts `sum_s_in_p x[s,g]*P[p,g,k]`. Municipal draws are **sums of local expected count draws**; municipal rates divide those sums by municipal origin counts. Quantiles are computed after aggregation. Averaging place probabilities or summing marginal interval endpoints gives a different and incorrect municipal summary.

We do not reconstruct the realized latent ballots. Expected flow draws need not reproduce every observed destination total or satisfy bounds that condition on realized margins. Such differences are exported separately. Original observed totals must match across methods exactly; baseline expected destination totals match by constraint, while new expected totals are stochastic-model predictions. No post-fit calibration is applied.

Intervals are pointwise 95% posterior credible intervals **conditional on the approximate likelihood, priors, grouping, and population closure**. The old method's 150-section-bootstrap percentile ranges remain labeled as sensitivity ranges with unvalidated coverage. Interval overlap is not a test of agreement. No confidence interval for a between-method difference is invented by treating fits to the same data as independent.

The frozen municipal warnings are: matrix allocation distance >0.05, origin-rate difference >10 percentage points for an origin with ≥100 people, or an abstention/invalid-to-finalist cell shift >2% of the electorate. Prior sensitivity above 2% of the electorate is a separate warning. These are substantive investigation thresholds, not statistical significance levels. Simulations evaluate their behavior; thresholds were not fitted to which real cities disagree.

For expected flow matrices, `D=sum(abs(F_new-F_old))/(2*N)` measures total-variation disagreement between two allocations of the common electorate. It does not measure a fraction of individually misclassified people. A large D can accompany improvement over a biased baseline or failure of the new method.

## Known-flow validation and the expansion gate

The design follows ADEMP: compare methods on identical generated data, record expected and realized truth separately, preserve first-round sizes/compositions, evaluate bias, error, interval coverage, width, failures, and runtime. The main generator uses Lebon Régis's retained section compositions and administrative nesting. This is a realistic **single design template**, not a national simulation sample.

The eight frozen scenarios cover homogeneous, moderate/strong local heterogeneity, composition-correlated transitions, residual section heterogeneity within places, weak/tiny-origin design, singleton/sparse places, and structural zero switching. The sparse scenario also changes nesting. An addendum, saved before generating its outcomes, adds a ninth explicit **two-place** scenario; both places can then support independent fits under the operational screen. It changes no existing pilot selection, priors, thresholds, or simulated outcomes. The experiment still cannot certify every configuration nationally. Unequal electorate totals are explicitly rejected; unobserved equal-size turnover is not identifiable and remains outside closed-electorate recovery claims.

The municipal baseline uses its original estimator and 150-resample bootstrap. Independent place fits use the original ten-section/full-rank screen; unavailable fits remain in failure denominators. Hierarchical intervals are assessed against **expected flows**, not against a realized table as if it were the parameter. Individual flow errors, particularly previous-abstention-to-Lula bias, complement matrix-average errors whose signed biases can cancel.

`simulation_flow_summary.csv` reports signed bias, MAE and RMSE for each origin/destination pair. `allocation_conservation_residual_electorate_pp` averages signed errors across all cells and therefore cancels when both matrices preserve population; it is a bookkeeping check, **not a useful bias measure**. Early cached replicate JSON calls that same residual `bias_electorate_pp`; the consolidated CSV renames it to avoid that misleading interpretation.

The first stage has 30 independent repetitions per scenario. Monte Carlo errors use repetition-level summaries; correlated cells/places are not counted as independent replicates. An unqualified expansion requires at least 100 repetitions per relevant scenario, empirical interval coverage ≥0.90, RMSE no more than 1.10 times the baseline, ≤5% unavailable fits, acceptable sampling/sensitivity checks, and no unresolved material municipal disagreements. The initial screen can reject expansion but cannot by itself certify 95% coverage. If a substantial screen failure or unresolved pilot disagreement occurs, record the failed gate and stop national expansion; otherwise extend the simulation before deciding.

After screening exposed model failures, `scripts/confirm_hierarchy_diagnostics.py` refits the first three contextual, within-place and boundary datasets using four chains, 1,000 warmup and 1,500 retained draws per chain with new MCMC seeds. This is a documented **post-screen computational confirmation**, not an independent calibration experiment. Its nine datasets do not increase the independent simulation count, and its results do not replace the original screen.

## Sources and what they support

- [Rosen et al. (2001)](https://doi.org/10.1111/1467-9574.00162): R×C ecological models and constrained/moment-based alternatives. Methodological lineage, not validation of these priors or likelihood.
- [Wakefield et al. (2011)](https://sites.stat.washington.edu/adobra/Files/Papers/wakefield-dobra-et.pdf), Sections 2–3.1.2: convolution likelihood and hierarchical logits; normal approximation is computationally attractive but can fail. Their detailed examples are 2×2, so our 5×4/place extension still requires validation.
- [Gelman (2006), multilevel models](https://sites.stat.columbia.edu/gelman/research/published/multi2.pdf): partial pooling and its limits. Regularization does not create individual-level evidence.
- [Gelman (2006), variance priors](https://sites.stat.columbia.edu/gelman/bayescomputation/Gelman2006.pdf): inspect scale priors and sensitivity when group-level variance has weak information. The half-normal is our parsimonious choice, not a paper-specific recommendation for this dataset.
- [Morris, White and Crowther (2019)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6492164/): ADEMP, comparisons with known truth, reporting failures and Monte Carlo uncertainty.
- [Stan diagnostic guidance](https://mc-stan.org/learn-stan/diagnostics-warnings.html): chain/ESS/divergence diagnostics. [Posterior predictive checks](https://mc-stan.org/docs/stan-users-guide/ppcs.html): replicate observables; do not equate aggregate prediction with transition recovery.
- [Wakefield (2004)](https://www.stat.purdue.edu/~chuanhai/teaching/Stat598A/Wakefield_Ecology.pdf): nonidentification, contextual bias, and external information. These objections apply to both models even if their estimates agree.

See the broader [literature review](../LITERATURE_REVIEW.md) for source-access qualifications, challenges to bootstrap assumptions, and the distinction between accounting, bounds, estimation, and causal claims.

## Reproduce

```
python -m venv --system-site-packages .venv-hierarchy
.venv-hierarchy/bin/python -m pip install -r requirements-hierarchy.txt
MPLCONFIGDIR=/tmp/elections-matplotlib OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv-hierarchy/bin/python -m elections.hierarchy_pilot
MPLCONFIGDIR=/tmp/elections-matplotlib OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv-hierarchy/bin/python -m elections.hierarchy_simulation
.venv-hierarchy/bin/python scripts/build_hierarchy_report.py
```

The pilot and simulation commands resume completed fit/replicate files. They verify the frozen input hashes before proceeding. Existing national data and results are read-only inputs; experimental artifacts go to `results/2026/hierarchy_pilot/`.

Optional browser validation uses Playwright with its Chromium installation (`python scripts/check_hierarchy_browser.py`). This execution reused the cached Playwright installation at `/tmp/elections-flow-browser` and required browser process startup outside the restricted sandbox. It opened the local report only. No website deployment was performed.
