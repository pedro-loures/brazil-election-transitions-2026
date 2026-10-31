# Behavioural pooling, resampling and cross-model agreement

Extension requested on 30 October 2026. Implementation is in `elections/agreement*.py`, with execution status recorded separately in `MODEL_AGREEMENT_RESULTS.md`. Implemented stages and a completed pilot do not establish statistical validation. Preserve the original spatial manifest, implementation snapshot, simulations and decisions. Freeze a new manifest before new outcomes; use `results/2026/model_agreement/` for this extension. No previous result is reclassified by adding an agreement rule.

The initial execution fixes two behavioural regimes and a 10-section/5-km geographic comparator. These are prospective settings, not empirically established optimal choices. The pilot uses three first-round-selected development municipalities (bins 1–3), 20 paired building-bootstrap perturbations per municipality, two large-building deletion checks and two additional prior variants. Its known-flow screen has 30 independent datasets in each of the within-building and contextual scenarios in bin 1. Full development, five-bin profiling, all-municipality perturbations and independent validation are separate resumable stages; none is implied by pilot completion.

## Question and comparison

Does sharing information among sections with similar inferred transition patterns improve recovery, and do substantively different models agree on particular flows? Agreement is evidence of robustness to the model choices tested. It is not an independent replication, a probability of correctness or a substitute for known-truth calibration.

Compare municipal, geographic, behavioural and combined geographic–behavioural model families. Retain the original constrained estimator as an additional benchmark. Match likelihoods, priors and contextual/residual extensions where possible; record every unmatched assumption. Prior variants, random seeds and grouping settings are sensitivity variants, not extra independent model votes.

Learn behavioural groups and transitions jointly, retaining section observations and group-membership uncertainty. Similar changes in totals do not establish similar individual movements. Evaluate the model even when observed swings coincide but underlying transitions differ. Preserve first-round composition variation and assess rank/conditioning within inferred regimes. Tune complexity on development data only. Predictive checks on aggregate outcomes complement, but cannot establish, hidden-flow recovery.

## Compare estimates on the same target

All comparisons use the same eligible electorate, origin/destination definitions and expected-flow estimand. Compare municipality, original polling place and section where each method supplies estimates. Different new-group partitions must be aggregated to a common support before comparison. Unsupported levels remain unavailable.

For each flow export every model's count, origin rate, interval type/width, convergence, prior sensitivity and validation status. Export all pairwise count/rate differences and the across-model range. For whole matrices export allocation distance `sum(abs(F_a-F_b))/(2*N)`.

Initial candidate agreement tolerances reuse the existing investigation rules: pairwise matrix distance at most 0.05, supported-origin rate difference at most 10 percentage points (origin count at least 100), and a key-flow count difference at most 2% of the common electorate. Report the separate tests; a whole-matrix pass cannot conceal a disputed cell. These are study defaults requiring development evaluation, not academic confidence levels. Unsupported small origins receive separate assessments.

Report the largest mutually agreeing subset of model families, with explicit member names and all dissenting or unavailable models. Every pair in a subset must meet the relevant tolerance; agreement through an intermediate model is insufficient. “Three of four agree” is a descriptive count. It never becomes “75% probability of truth.” Do not average agreeing estimates or shrink their intervals automatically, and do not treat interval overlap as an agreement test.

Distinguish agreement alone from agreement supported by adequate computation, useful precision, prior robustness and independent known-flow validation. Stronger shared assumptions can generate shared bias. No consensus overrides an individual reliability failure or the existing scaling requirements.

## Resampling and validation

Use the same resampling indices across all models so differences are paired. Keep each section's two-round record intact. Prespecify balanced strata and resampling units; assess whole-building or spatial-block perturbations when dependence is plausible. Rerun grouping and fitting within each resample. Label resampling variation separately from posterior uncertainty unless a combined inferential procedure has been justified and calibrated.

At fixed original reporting supports, export per-flow variation, leave-building/group-out influence, cluster co-assignment/Jaccard stability, convergence/failure fractions, agreement frequency for each named subset, and dissenting-model identity. Count expected models and failed/unavailable fits explicitly. Repeated resamples are not new elections or independent confirmations of a movement.

On new known-flow datasets, test whether consensus actually predicts accuracy: report RMSE, interval coverage/width and the frequency with which agreeing models are all materially wrong. Include shared misspecification, weak composition variation, identical observed swings from different flows, and behaviour unrelated to proximity. Use datasets as Monte Carlo units and report uncertainty. Freeze the full consensus procedure before held-out evaluation; evaluating only selected agreeing cases without assessing that selection would be optimistic.

## Reporting

Add map layers for across-model rate/count range, matrix disagreement, number/names of agreeing families, paired-resample agreement frequency and resampling variation. Display model intervals alongside these layers. Label agreement, sensitivity and simulation-based accuracy separately; display unavailable evidence explicitly.

## Academic basis and limits

- [Puig & Ginebra (2014), A cluster analysis of vote transitions](https://doi.org/10.1016/j.csda.2013.10.006): precedent for joint clustering and transition estimation, not proof of identification in this application.
- [Hennig (2007), Cluster-wise assessment of cluster stability](https://doi.org/10.1016/j.csda.2006.11.025): resampling/Jaccard cluster assessment; stability alone is not validity.
- [Gnaldi, Tomaselli & Forcina](https://arxiv.org/html/1509.03055): common ecological bias can affect multiple estimators; their agreement does not identify truth.
- [Cawley & Talbot (2010)](https://www.jmlr.org/papers/v11/cawley10a.html): model/procedure selection and its evaluation must be separated.

The agreement tolerances, subset reporting rule and proposed map layers are this project's design choices. Their value must be established by the new experiment.
