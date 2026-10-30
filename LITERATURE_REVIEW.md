# Academic support and challenges for the voter-transition methodology

Reviewed: **30 October 2026**. Scope: the supplied Twitter thread and the methodological reconstruction implemented in this repository.

The literature supports using aggregate election results to calculate bounds and to estimate voter transitions **under explicit assumptions**. It also supplies substantial theoretical and empirical challenges to interpreting those estimates as identified individual movements or as proof of campaign effects. The most defensible parts of this project are the observed totals, accounting identities, and correctly qualified bounds. The flow estimates and uncertainty ranges require further validation.

Here, **supports** means support for a particular component or methodological family. **Challenges/contradicts** means that a paper challenges a necessary assumption or contradicts a stronger interpretation; it does not mean its authors examined this thread, this code, or Brazil's 2026 election. **Mixed** means that a source supports the research approach while identifying an important limitation. Counting papers on each side is not a measure of which conclusion is correct.

## 1. What is being evaluated

The thread combines observed section returns, accounting, an incompletely specified transition estimator, resampling, aggregate correlations, a proportional-allocation comparison, and substantive claims about mobilization. Its exact estimator cannot be reconstructed from the screenshots alone.

The repository implements a specific ecological regression in [elections/model.py](elections/model.py). Within each municipality, section `s` has:

```text
x_s = [A1, B1, other valid candidates1, blank/null1, abstention1]
y_s = [A2, B2, blank/null2, abstention2]
```

It estimates a common 5×4 transition-rate matrix `P` by minimizing:

```text
sum_s ||x_s P - y_s||² / N_s
```

Rates are nonnegative, each origin row sums to one, and municipal destination totals match exactly. A second fit prohibits A↔B switching. Section predictions need not match every observed section margin. The full model receives 150 section bootstrap resamples; reported intervals are percentile ranges. Sections must pass matching, electorate-size, location, and consistency checks. See [README.md](README.md) for the complete implementation description.

The source-to-code assessments below are this review's applications of the literature, not claims that the cited authors endorse this implementation.

## 2. Which components have support, and which face challenges?

| Component or claim | Supporting literature | Challenging or qualifying literature | Assessment for this project |
|---|---|---|---|
| Estimate transitions using many sections' election margins | S1, S3, S4, S5, S6 | C2, C3, C4 | Established research problem; estimates remain assumption-dependent. |
| Use nonnegative probabilities and consistent election totals | S4, S6, S7 | C3; M2 | Sensible constraints. Agreement with margins imposed during fitting is not independent validation. |
| Calculate bounds without selecting one transition table | S2 | C3 clarifies limits | Strong support. Bounds identify a feasible range, not necessarily a useful point estimate. |
| One common transition matrix per municipality | S1 provides a conditional foundation | C2, C3, C4 | A consequential simplifying assumption. Municipal boundaries do not establish behavioral homogeneity. |
| The exact weighted quadratic objective used here | S4 supports related moment/least-squares approaches | S3 uses a different probability model; M1 shows alternative formulations matter | Methodological precedent exists; no reviewed source validates this exact objective and constraints for these data. |
| High section correlation establishes individual voter origins | No source establishes this implication | C1, C3, C4 | Contradicted as a general inference. Aggregate associations can describe a pattern without identifying transitions. |
| The thread's 206-vote minimum is unconditional | S2 supports the method of bounds, not this unrestricted conclusion | C3; the counterexample in Section 5 | The claimed source-specific minimum requires excluding transfers from the other finalist. |
| Bootstrap provides information about estimator variability | S8; S5 motivates uncertainty assessment in transition research | C5, C6, M2 | Conditional support. Resampling is not a remedy for identification, heterogeneity, dependence, or boundary problems. |
| Exactly 150 resamples establish well-calibrated 95% intervals | None of the reviewed sources establishes this | C5, C6, M2 | Treat these as exploratory sensitivity ranges until coverage and numerical stability are evaluated. |
| Equal electorate sizes imply the same underlying people | S5, S7 support explicit treatment of population changes | S5, S7 also show why entries/exits matter | Equal counts are a screening rule, not proof of unchanged membership. |
| Mobilization is a plausible mechanism for turnout changes | M3 | M3 uses a causal design absent here | Plausible, but the proposed local campaign explanation is not causally identified. |
| Rejecting one allocation rule proves the preferred flow model | No supporting implication established | C3; M1, M2 motivate comparing alternatives | Rejects the tested joint assumptions only. |

## 3. Sources supporting components of the approach

### S1. Goodman (1953): ecological regression — conditional support

**Reference:** Goodman, L. A. (1953). *Ecological Regressions and Behavior of Individuals*. American Sociological Review, 18(6), 663–664. [DOI/publisher record](https://doi.org/10.2307/2088121).

**Why it supports the approach:** This is an early statistical foundation for estimating group-specific behavior from aggregate compositions. The relevant condition is that within-group behavior has a suitable relationship with area composition; literal equality of every area's realized transition fractions is stronger than needed for a regression of conditional means.

**Application and limit:** It supplies a lineage for `x_s P`, not validation of our weighting, calibration, constraints, or Brazilian estimates. Context-related variation in transitions can defeat the inference.

**Access:** Original bibliographic record verified through the publisher's issue listing; original full text was not retrieved. The methodological description was cross-checked against C3, Section 3.4, and S4's historical discussion. This is not a claim to have independently read the original article.

### S2. Duncan and Davis (1953): deterministic bounds — direct support for bounds

**Reference:** Duncan, O. D., and Davis, B. (1953). *An Alternative to Ecological Correlation*. American Sociological Review, 18(6), 665–666. [DOI/publisher record](https://doi.org/10.2307/2088122).

**Why it supports the approach:** Observed margins restrict the possible internal cells of contingency tables without requiring one fitted behavioral model.

**Application and limit:** This supports reporting unrestricted feasible ranges and showing how additional restrictions change them. It does not justify promoting a conditional minimum to an unconditional finding. Section 5 derives the relevant bound for this application.

**Access:** Original citation verified; original full text was not retrieved. The bounds were cross-checked in C3, Section 4.1, equations (13)–(14), which explicitly attributes the method to Duncan and Davis.

### S3. Brown and Payne (1986): voting transitions — support for the problem, a different model

**Reference:** Brown, P. J., and Payne, C. D. (1986). *Aggregate Data, Ecological Regression, and Voting Transitions*. Journal of the American Statistical Association, 81(394), 452–460. [Publisher abstract and DOI](https://www.tandfonline.com/doi/abs/10.1080/01621459.1986.10478290).

**Why it supports the approach:** The paper models transitions between successive elections from precinct margins using an aggregated compound multinomial model, with covariates and random effects.

**Application and limit:** It directly supports studying election-to-election transitions from aggregate data. Its treatment of heterogeneous behavior is also a reason to question an unqualified common-matrix model. Our weighted least squares is not the Brown–Payne likelihood.

**Access:** Publisher abstract and bibliographic metadata examined; full article not retrieved.

### S4. Rosen, Jiang, King, and Tanner (2001): R×C inference and least squares — conditional support

**Reference:** Rosen, O., Jiang, W., King, G., and Tanner, M. A. (2001). *Bayesian and Frequentist Inference for Ecological Inference: The R×C Case*. Statistica Neerlandica, 55(2), 134–156. [DOI](https://doi.org/10.1111/1467-9574.00162); [original article PDF reproduction](https://scispace.com/pdf/bayesian-and-frequentist-inference-for-ecological-inference-50lisejgk6.pdf).

**Why it supports the approach:** The paper develops larger-table ecological inference, including a faster moment-based nonlinear least-squares alternative to Bayesian estimation. It explicitly considers logically possible parameter regions.

**Application and limit:** This is useful precedent for computationally tractable estimation and probability constraints. Its model contains structure, covariates, and regularity conditions that cannot simply be assumed to hold for our different quadratic program.

**Access:** Original article PDF examined, especially Sections 4 and 6. The linked PDF is a reproduction, not a third-party summary.

### S5. Romero, Pavía, Martín, and Romero (2020): presidential rounds and uncertainty — close application-level support

**Reference:** Romero, R., Pavía, J. M., Martín, J., and Romero, G. (2020). *Assessing uncertainty of voter transitions estimated from aggregated data. Application to the 2017 French presidential election*. Journal of Applied Statistics, 47(13–15), 2711–2736. [DOI](https://doi.org/10.1080/02664763.2020.1804842); [university-repository manuscript](https://riunet.upv.es/bitstreams/a3ae169a-d7ea-45da-974f-5c16b0ab0881/download).

**Why it supports the approach:** It estimates transfers between presidential rounds using mathematical programming, explicitly handles electorate entries/exits, and develops uncertainty assessment using model residual information.

**Application and limit:** This is especially relevant to the election structure here. Its uncertainty procedure is not our ordinary section bootstrap. Its population-change treatment also argues for extending our coverage screening rather than equating equal electorate sizes with identical people.

**Access:** University-hosted original manuscript examined; the repository supplies the final journal citation.

### S6. Pavía and Romero (2024; online 2022): constrained optimization — support with an algorithm distinction

**Reference:** Pavía, J. M., and Romero, R. (2024). *Improving Estimates Accuracy of Voter Transitions. Two New Algorithms for Ecological Inference Based on Linear Programming*. Sociological Methods & Research, 53(3), 1491–1533. First published online in 2022. [Publisher article and DOI](https://doi.org/10.1177/00491241221092725).

**Why it supports the approach:** The paper develops optimization-based R×C estimates under a homogeneity hypothesis and evaluates them using known transition tables and simulations. It also addresses extreme estimated transfer probabilities.

**Application and limit:** It supports constrained optimization as a serious methodological family. Its linear-programming algorithms and empirical validation do not transfer automatically to our quadratic loss. A fitted probability of zero should not be interpreted as proof that a transition never occurred.

**Access:** Publisher abstract and publication details examined; indexed manuscript excerpts also inspected. The article's online year and issue year are distinguished above.

### S7. Pavía (2023): consistency and completeness — support for calibration

**Reference:** Pavía, J. M. (2023). *Adjustment of initial estimates of voter transition probabilities to guarantee consistency and completeness*. SN Social Sciences, 3, article 75. [Open-access article and DOI](https://link.springer.com/article/10.1007/s43545-023-00658-y).

**Why it supports the approach:** The paper develops methods to make transition estimates consistent with election margins while accommodating incomplete information and population-change scenarios.

**Application and limit:** It supports our concern with row-standardized matrices and consistent municipal totals. Consistency is a property an estimator can impose; it is not independent evidence that its internal cells are correct. The paper adjusts initial information, so it is not our estimator.

**Access:** Publisher full text examined, particularly the introduction, data specification, and scenarios.

### S8. Efron (1979): bootstrap — support subject to a sampling model

**Reference:** Efron, B. (1979). *Bootstrap Methods: Another Look at the Jackknife*. The Annals of Statistics, 7(1), 1–26. [DOI](https://doi.org/10.1214/aos/1176344552); [original article, university-hosted PDF](https://blogs.helsinki.fi/bk-club/files/2012/05/Efron_Bootstrap_AS1979.pdf).

**Why it supports the approach:** The bootstrap approximates sampling distributions by resampling from an empirical distribution.

**Application and limit:** This supports resampling as a tool, not every bootstrap implementation. The stochastic target and resampling unit must be justified. Resampling a complete set of election sections does not estimate uncertainty in the already observed vote totals, and cannot recover information absent from the margins.

**Access:** Publisher identity verified and indexed original-article passages examined; direct PDF retrieval timed out. No claim of a complete full-text reading.

## 4. Sources challenging assumptions or contradicting stronger interpretations

### C1. Robinson (1950): aggregate correlation is not individual association

**Reference:** Robinson, W. S. (1950). *Ecological Correlations and the Behavior of Individuals*. American Sociological Review, 15(3), 351–357. [Original DOI](https://doi.org/10.2307/2087176); [original article, university-hosted scan](https://fisher.stats.uwo.ca/faculty/aim/2015/9938/articles/Robinson1950AmericanSociologicalReview.pdf). A later reprint has a [different DOI](https://doi.org/10.1093/ije/dyn357).

**What it challenges:** Substituting correlations across areas for associations among individuals can produce misleading magnitudes and even different signs.

**Application:** A strong correlation between section-level gains and valid-vote growth does not identify which individuals moved from abstention or blank/null voting to a candidate. It can still be a legitimate description of sections. The paper does not prohibit all model-based ecological inference.

**Access:** Original scanned article excerpts, including the conclusion, and publisher reprint information examined.

### C2. Freedman and colleagues (1991): plausible alternative behavior models

**Reference:** Freedman, D. A., Klein, S. P., Sacks, J., Smyth, C. A., and Everett, C. G. (1991). *Ecological Regression and Voting Rights*. Evaluation Review, 15(6), 673–711. [DOI](https://doi.org/10.1177/0193841X9101500602); [Berkeley technical-report manuscript](https://digicoll.lib.berkeley.edu/record/85734/files/248.pdf).

**What it challenges:** In its application, ecological regression relies on political-behavior assumptions not supported by the data; a neighborhood model gives different behavioral conclusions.

**Application:** Our same-origin voters may behave differently across neighborhoods, even within a municipality. Fit and numerical uniqueness under one specification do not establish that its behavioral assumptions are right.

**Limit:** This is an application-specific critique, not proof that every ecological estimator is biased or that our particular estimates are wrong.

**Access:** University-hosted original technical report examined; final article metadata cross-checked.

### C3. Wakefield (2004): missing identification and assumption dependence

**Reference:** Wakefield, J. (2004). *Ecological inference for 2×2 tables*. Journal of the Royal Statistical Society: Series A, 167(3), 385–445, including discussion. [DOI](https://doi.org/10.1111/j.1467-985X.2004.02046_1.x); [original article PDF](https://www.stat.purdue.edu/~chuanhai/teaching/Stat598A/Wakefield_Ecology.pdf).

**What it challenges:** Margins do not determine internal cells; contextual effects and additional information materially affect inference.

**Application:** Bounds, model assumptions, and external evidence must be distinguished. Full rank in our common-matrix regression addresses that restricted parameterization, not identification under arbitrary section-specific behavior. The paper also supports using individual information alongside aggregates.

**Access:** Full article examined, especially Sections 3.4 and 4.1 and its summary. This review's assessment distinguishes the author's analysis from the appended discussion.

### C4. Gnaldi, Tomaselli, and Forcina (2018): contextual bias in voter transitions

**Reference:** Gnaldi, M., Tomaselli, V., and Forcina, A. (2018). *Ecological Fallacy and Covariates: New Insights based on Multilevel Modelling of Individual Data*. International Statistical Review, 86(1), 119–135. [Publisher and DOI](https://onlinelibrary.wiley.com/doi/abs/10.1111/insr.12244); [author preprint](https://arxiv.org/abs/1509.03055).

**What it challenges:** The authors formalize conditions for unbiased ecological regression and use individual voting data to show substantial bias in ecological estimates when conditions fail. Covariate adjustment is not a universal remedy.

**Application:** This directly challenges assuming that a common transition matrix adequately describes all sections. A stable bootstrap distribution around that fit need not reveal contextual bias.

**Access:** Published summary and indexed original-article passages examined; the accessible author-preprint abstract was cross-checked. Preprint claims are not silently substituted for the final version.

### C5. Andrews (2000): bootstrap failure at parameter boundaries

**Reference:** Andrews, D. W. K. (2000). *Inconsistency of the Bootstrap when a Parameter Is on the Boundary of the Parameter Space*. Econometrica, 68(2), 399–405. [Publisher record and DOI](https://onlinelibrary.wiley.com/doi/pdf/10.1111/1468-0262.00114).

**What it challenges:** Ordinary bootstrap approximations can fail for boundary-constrained estimation problems.

**Application:** Our probabilities are constrained to [0,1], and zero/one estimates can occur. Standard percentile intervals therefore need empirical coverage checks and an appropriate theoretical justification.

**Limit:** Applying this warning to our estimator identifies a risk, not a proof that all its bootstrap intervals are inconsistent. Establishing that result would require analysis of this estimator and its data-generating assumptions.

**Access:** Publisher bibliographic information and indexed original-paper excerpts examined; full PDF access was blocked. Page range follows the publisher, rather than conflicting secondary metadata.

### C6. Cameron and Miller (2015): dependence and resampling units

**Reference:** Cameron, A. C., and Miller, D. L. (2015). *A Practitioner's Guide to Cluster-Robust Inference*. Journal of Human Resources, 50(2), 317–372. [DOI](https://doi.org/10.3368/jhr.50.2.317); [author-hosted article](https://faculty.econ.ucdavis.edu/faculty/cameron/research/Cameron_Miller_JHR_2015_February.pdf).

**What it challenges:** Inference that ignores within-cluster dependence can overstate precision; bootstrap design and the number of independent clusters matter.

**Application:** Sections sharing polling places or neighborhoods may have related errors. Independently resampling sections needs justification. Assess polling-place or geographic clustering, then evaluate an appropriate uncertainty procedure for this constrained estimator.

**Limit:** The paper does not establish that these Brazilian section errors are correlated, or that a particular cluster bootstrap automatically fixes this model.

**Access:** Author-hosted full article examined, including its bootstrap cautions.

## 5. Sources with mixed implications and direct checks on the reasoning

### M1. Pavía and Romero (2024): formulation sensitivity

**Reference:** Pavía, J. M., and Romero, R. (2024). *Symmetry estimating R×C vote transfer matrices from aggregate data*. Journal of the Royal Statistical Society: Series A, 187(4), 919–943. [Publisher full text and DOI](https://academic.oup.com/jrsssa/article/187/4/919/7616654).

**Support:** The paper develops and evaluates constrained ecological-inference algorithms.

**Challenge:** It shows that formulation choices, including asymmetry in assigning rows and columns, can affect estimates and accuracy. Its evidence favors symmetric procedures in its benchmark setting.

**Application and limit:** Benchmark our forward quadratic estimator against published alternatives. The paper evaluates simultaneous elections with known cross-classifications; its performance ranking does not automatically apply to sequential Brazilian presidential rounds.

**Access:** Publisher full text examined, including its abstract and introduction.

### M2. Plescia and De Sio (2018; online 2017): validation using known transitions

**Reference:** Plescia, C., and De Sio, L. (2018). *An evaluation of the performance and suitability of R×C methods for ecological inference with known true values*. Quality & Quantity, 52, 669–683. [Open-access article and DOI](https://link.springer.com/article/10.1007/s11135-017-0481-z).

**Support:** Ecological methods can be compared empirically against known internal cells rather than dismissed or accepted in principle.

**Challenge:** Confidence intervals and point estimates require evaluation against truth; small residuals and plausible probabilities are insufficient validation criteria.

**Application and limit:** Our synthetic recovery test establishes correct behavior under its constructed assumptions. It does not establish real-election interval coverage. Their split-ticket benchmark is informative but differs from successive-round voter transitions.

**Access:** Publisher full text examined, particularly its stated research design and coverage-evaluation criterion.

### M3. Gerber, Green, and Larimer (2008): mobilization is plausible, causal attribution requires a design

**Reference:** Gerber, A. S., Green, D. P., and Larimer, C. W. (2008). *Social Pressure and Voter Turnout: Evidence from a Large-Scale Field Experiment*. American Political Science Review, 102(1), 33–48. [Publisher abstract and DOI](https://doi.org/10.1017/S000305540808009X).

**Support:** A field experiment demonstrates that an intervention can increase turnout. Mobilization is a plausible behavioral mechanism.

**Challenge to interpretation:** This does not show that a particular Brazilian campaign produced the observed changes. Our pipeline does not observe or assign campaign contact, and inferred return-to-voting is not itself an estimated treatment effect.

**Access:** Publisher abstract and article metadata examined. No numerical treatment effect is transferred to Brazil.

### The 206-vote claim: what follows without a behavioral model?

The following is a derivation for this project, using the method-of-bounds logic associated with S2; it is not a quotation from a paper or a new empirical finding.

For one section, let `M1` combine first-round abstention and blank/null voting. Let `V1 = A1+B1+O1`, where `O1` is votes for other valid candidates, and `N = M1+V1` is the unchanged underlying electorate. If `z` people from `M1` choose A in round two:

```text
max(0, A2 - V1) <= z <= min(A2, M1)
```

Reason: at most `V1` of A's second-round votes can originate outside `M1`; at most all of `M1`, or all of `A2`, can lie in the intersection. The matching assumption concerns people, not just equal electorate counts.

If **B1→A2 is forbidden**, the outside supply falls to `A1+O1`, yielding:

```text
z >= max(0, A2 - A1 - O1) = max(0, delta_A - O1)
```

The latter is the type of calculation behind the thread's 206-vote minimum. Without excluding finalist switching, an excess gain over `O1` need not have come from `M1`. A concrete feasible counterexample is:

| Category | First round | Second round |
|---|---:|---:|
| A | 100 | 130 |
| B | 100 | 110 |
| Other valid candidates | 10 | 0 |
| Abstention plus blank/null | 90 | 60 |
| Total electorate | 300 | 300 |

Let all 100 original A voters stay, 20 B voters switch to A, all 10 other-candidate voters switch to A, and 30 people from `M1` choose B. The remaining 80 B voters and 60 people in `M1` stay in their categories. Both finalists gain, yet **no one from `M1` votes for A**. Its unrestricted lower bound is zero; imposing no B→A switching instead gives a conditional lower bound of 20. This is a mathematical counterexample, not a claim about any actual section. A proposed alternative for a real section must satisfy that section's full margins.

Our exported `a_lower_if_no_cross` and `b_lower_if_no_cross` are therefore appropriately conditional. The unrestricted bounds are the relevant comparison when finalist switching is allowed. This qualification challenges the thread's stronger interpretation while supporting the repository's separation of bounds and assumptions.

### Correlations share an accounting component

Define `D_s = delta_turnout_s - delta_invalid_s`. The section identity gives:

```text
delta_A_s + delta_B_s = O1_s + D_s
delta_A_s = D_s + O1_s - delta_B_s
```

Consequently, the correlation of `delta_A_s` with `D_s` is not independent evidence in addition to this identity: its value depends on the variances and covariances of the other terms. The identity does not force a high positive correlation in every dataset, but it makes a high value insufficient to identify the individual mechanism. C1's cross-level warning is an additional, separate objection.

### What the bootstrap ranges currently measure

The complete section counts are observed. The current resampling experiment varies which sections inform a model, so its immediate interpretation is **model-based sensitivity to section composition**, not uncertainty about the official total count.

Two extra issues follow from the implementation itself:

1. With 150 successful replicates, a 2.5% tail contains only about `150 × 0.025 = 3.75` replicates. This is our arithmetic observation about tail resolution, not a universal literature rule declaring 150 invalid. More replicates and repeated seeds can assess numerical stability; they do not repair model bias.
2. Failed or rank-deficient draws are discarded. Their frequency and causes matter; retaining 80% is an operational flag, not a demonstrated coverage theorem. The bootstrap samples also recalibrate their own destination totals, so their rates applied to the original electorate need not preserve the original destination margins. Individual reported quantiles are not jointly feasible transition tables.

The general motivation comes from S8; risks concerning boundaries, dependence, and empirical coverage are addressed by C5, C6, and M2, respectively.

## 6. What the literature implies we should keep or improve

| Action | Reason and supporting references | Current status |
|---|---|---|
| Keep observed totals, accounting residuals, coverage, and unrestricted bounds separate from model outputs | They answer different questions; S2, C3 | Implemented. |
| Keep the no-switch fit as a sensitivity scenario | Zero switching is an imposed restriction, not identified behavior; C2–C4 | Implemented; must remain labeled conditional. |
| Validate against heterogeneous simulations and compare published estimators | A test generated under the fitted assumptions is insufficient; S3–S6, M1, M2 | Existing tests are a starting point, not this broader validation. |
| Examine contextual variation and compare common-rate, covariate, and hierarchical models | Composition-related heterogeneity can bias ecological inference; C2–C4 | Not yet implemented. Adding covariates is not guaranteed to eliminate bias. |
| Evaluate dependence and resampling at defensible geographic units | Independent section resampling may miss shared errors; C6 | Not yet implemented; small numbers of clusters also need attention. |
| Test uncertainty coverage at zero/one rates and under misspecification | Boundary estimates and contextual bias can undermine intervals; C4, C5, M2 | Not yet implemented. |
| Increase bootstrap replicates for stability studies and inspect failed draws | Tail resolution and resampling diagnostics matter; S8, C6; calculations above | Current run uses 150, with failure counts reported. |
| Model electorate entries/exits or report sensitivity to their exclusion | Matching counts is not matching membership; S5, S7 | Current implementation filters changed counts and reports coverage. |
| Seek independent transition information, with survey/recall error considered | External information can help evaluate ecological estimates; C3, S5 | No individual transition data used. |
| Use a causal design before attributing changes to campaign activity | An estimated flow and an intervention effect are different quantities; M3 | No causal campaign-effect design implemented. |

The literature does **not** turn accounting agreement into a general fraud test, identify individual ballots, or validate machine-log timestamps. The timing audit is a separate data-processing task, and none of these references verifies the currently unprocessed nationwide logs.

## 7. Retrieval and interpretation notes

This is a focused literature review, not a systematic review or meta-analysis. Searches combined ecological inference, voter transitions, homogeneity, R×C tables, uncertainty, bootstrap boundaries, clustering, and turnout experiments. Publisher records, original papers, and author/university manuscripts were preferred. Search results and secondary bibliographic services were used to locate works, not as substitutes for the original research claims.

Access differed across works, as disclosed above. Some originals were accessible only as indexed passages or abstracts; S1 and S2 were checked bibliographically and interpreted through accessible original research that explains them. Publication years follow journal issue years, with differing online years noted. Assertions applying these works to the repository, proposed improvements, and the algebra in Section 5 are this review's reasoned assessments.

No reviewed source directly evaluates this implementation or establishes that the thread's estimated individual movements occurred in the 2026 Brazilian election. The credible reading of the current output is a descriptive audit plus explicitly conditional ecological estimates, with uncertainty calibration and causal interpretation still requiring additional work.
