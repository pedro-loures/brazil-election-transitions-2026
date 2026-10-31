# Model-agreement extension: current execution

**Decision: insufficient evidence.** Independent calibration is not complete.

Completed fit attempts: 669. Statuses: {'ok': 397, 'diagnostic_warning': 251, 'too_few_sections_or_rank_deficient': 20, 'insufficient_bootstrap': 1}.
Completed known-flow municipal datasets with exported flows: 60. Repeated models and resamples are not independent datasets.
Frozen source hashes unchanged: True.

The four families share composition effects and DM moment overdispersion. Behavioural and combined models jointly infer two section regimes. The original WLS estimator is an additional, unmatched benchmark.
Whole-building resamples are paired across models. Groups are rebuilt; original fixed reporting supports and denominators are preserved. Sections omitted from mixture fitting use prior component membership, without reading their second-round outcomes for assignment.
Posterior intervals, empirical resampling ranges, model agreement and known-flow accuracy are distinct evidence. Mode-cluster Jaccard and posterior co-assignment stability are reported separately.
Inspect `results/2026/model_agreement/execution_state.json` for current progress and a measured runtime ETA. A completed pilot is not full five-bin validation.

Report: `results/2026/model_agreement/report.html`. Raw fit attempts, flows, calibration metrics, consensus failures, priors, cluster stability and resampling diagnostics are exported alongside it.
