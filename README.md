# Brazilian presidential runoff analysis

This project applies the separable parts of the supplied Twitter thread to every
domestic municipality unit present in the TSE presidential files. The default
year is **2026**, matching the screenshots. It produces observed totals, section
coverage and reconciliation checks, arithmetic bounds, correlations,
conditional allocation checks, explicit ecological flow estimates, and an
offline searchable HTML report.

**This is a methodological reproduction, not the original author's code.** The
screenshots do not specify the original ecological estimator, its objective,
constraints, or weighting. Estimates here can differ. Individual transitions
are not directly observed and campaign effects are not causally identified.

See [the academic literature review](LITERATURE_REVIEW.md) for sources supporting
and challenging each component, their relevance to this implementation, and
priorities for methodological validation.

## Hosted visualization and published data

**[Open the interactive map and flowcharts](https://pedro-loures.github.io/brazil-election-transitions-2026/)**

**[GitHub repository and downloadable data](https://github.com/pedro-loures/brazil-election-transitions-2026)**

The static map and flowcharts are published from `docs/` using GitHub Pages.
The site has no backend, external map tiles, or third-party runtime libraries.
The same files work at a GitHub project-site path or any other HTTP prefix.

The checked-in [data snapshot](datasets/README.md) includes processed inputs,
computed results, model estimates, and provenance. Large raw TSE/IBGE archives
remain outside Git. Restore the verified working snapshot after cloning:

```bash
python scripts/restore_snapshot.py
python -m http.server 8765 --bind 127.0.0.1 --directory docs
```

Open `http://localhost:8765/`. Python dependencies are needed for analysis and
tests, but not to browse the hosted visualization. After recomputing results
and rebuilding the flow explorer/map, update the published files with
`python scripts/prepare_publication.py`. GitHub Pages uses the `main` branch's
`/docs` directory; pushes updating that directory republish the site.

## Run

Python 3.10+ with packages listed in `requirements.txt` is required. From the
project directory:

```bash
python -m pip install -r requirements.txt
python -m elections download --year 2026 --output data/raw/2026
python -m elections prepare --year 2026 --raw data/raw/2026 --output data/processed/2026
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLCONFIGDIR=/tmp/elections-twitter-matplotlib python -m elections analyze --bootstrap 150 --workers 8
python -m pytest -q
```

Open `results/2026/report.html` directly in a browser. The municipality search,
tables, and embedded figure work offline. CSV and PDF downloads sit alongside
the HTML. A focused run can use `--municipality 81914 --output results/lebon`.
These are **TSE municipality codes**, not IBGE codes. Candidate A is the runoff
finalist with the smaller ballot number, and B the other finalist; the names
and numbers are saved in metadata and displayed in the report.

## Port-forwarded flowcharts

The standalone flow explorer recreates the thread's labeled arrows and
proportional Sankey diagram, and offers both fitted models for every modeled
municipality. Its **Thread reference** reproduces the screenshot matrix exactly;
**Explore geography** uses our estimates and clearly identifies their
analyzed-section coverage. Select a flow to inspect its estimate, category
shares, and available bootstrap range. Retained-vote and minimum-flow controls
hide links without changing the electorate totals. SVG export preserves the
current diagram. All assets and data are served locally, without CDN libraries.

Build once after the computed analysis changes:

```bash
python scripts/build_flowcharts.py
```

Start on the remote machine containing this checkout:

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory results/2026/flowcharts
```

From a terminal on your own computer, forward the port:

```bash
ssh -N -L 8765:127.0.0.1:8765 YOUR_SSH_HOST
```

Use the SSH host/alias that reaches the machine running the server. If your SSH
setup needs a jump host, keep the same configured jump-host settings.
Open `http://localhost:8765/` in your local
browser and keep the SSH connection open. The standalone page needs HTTP
serving because municipality data loads on selection.

Checks for the graph geometry and source separation:

```bash
node tests/test_flow_layout.mjs results/2026/flowcharts/data
```

Optional browser QA uses Playwright and `scripts/check_flowcharts_browser.py`;
Playwright is not required to run or view the report.

Under **Explore geography**, choose Municipality, State / UF, Region, or Brazil.
State/region/Brazil diagrams sum the available municipal model matrices; they
do not refit a single model at the larger geographic level. Municipalities
without a fitted matrix are absent from estimated flows but remain included in
full observed totals. Coverage is computed separately for each selected model
and reports both modeled municipalities and the electorate represented by the
diagram. Brazil covers the domestic electorate and excludes overseas voting.
Aggregate bootstrap intervals are not reported: adding municipal percentile
endpoints would not produce a valid aggregate interval.

Refresh aggregate data and page assets without rewriting municipal files:

```bash
python scripts/build_flowcharts.py --aggregates-only
```

The map above the diagrams selects municipalities, UFs, and regions by clicking
their polygons. **Map level** changes the units; municipality view can focus on
one UF. Drag to pan, use + / − to zoom, or select **Zoom to selection**. The
flowchart follows the selected area; the model selector does not change colors.

The diverging color metric is `(Lula₂ − Lula₁) − (Flávio₂ − Flávio₁)`, in **raw
votes**, using full observed results. The interface names the candidate with
the greater gain and shows a positive advantage: **Lula +368** means Lula gained
368 more votes than Flávio; **Flávio +368** means the reverse. This is the gap
between their gains, not that candidate's own gain or the runoff winning margin.
Both individual vote changes remain visible. Ties read **Equal gains**.
Red identifies a greater Lula gain; blue identifies a greater Flávio gain.
Color intensity defaults to a **soft logarithmic scale**. Its magnitude is
`(log(1 + abs(x)) / log(1 + max_abs)) ** 1.55`, with muted endpoints applied
equally to both candidates. This tempers the previous strong logarithmic colors
while keeping smaller municipalities visible beside São Paulo.
**Color intensity** also offers the original linear scale. Both are symmetric
about equal gains, and the legend inverts the selected transformation to show
positive gain advantages on each candidate's side. Focusing on a UF recalculates
the legend. It does not measure individual
voter switching or percentage-point changes. State and region colors include
all municipalities, even those without fitted flow matrices.
Delicate state outlines remain visible at every map level; slightly heavier lines mark
region borders. The background is tinted and the map uses a taller aspect ratio
to keep the country prominent. Borders do not intercept polygon selection.

Map boundaries use the [official IBGE 2025 municipal mesh](https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html).
The [official TSE municipality configuration](https://resultados.tse.jus.br/oficial/ele2026/6258/config/mun-e006258-cm.json)
provides the direct `cd` → `cdi` join to IBGE codes. All 5,571 domestic election
units join exactly, including Boa Esperança do Norte. The two IBGE operational
water-body units have no election counts; they contribute only to aggregate
outlines. Geometry is simplified with shared boundaries and then dissolved for
27 UFs and five regions. The display uses Mercator projection. Browser assets
remain entirely local; there is no tile server or third-party runtime request.

To rebuild the boundaries, install the optional build dependencies:

```bash
python -m pip install -r requirements-map.txt
python scripts/build_map.py
```

The builder reads cached `data/raw/geography/BR_Municipios_2025.zip` and
`data/raw/geography/tse.json`. Official source URLs and file hashes are recorded
in the served `data/maps/manifest.json`; cached download URLs are also stored in
`data/raw/geography/urls.json`. Rebuild the map after observed results change.
Use `--output` to build map data into a different flowchart output directory.
`scripts/check_map_browser.py` verifies real polygon clicks, keyboard selection,
the delta calculation, newest-municipality coverage, zooming, and phone layout.

The downloader records source metadata, retrieval time, file sizes, and SHA-256
hashes in `data/raw/2026/manifest.json`. It reuses existing ZIP files; move a
cached file aside to request a fresh download. For a later year, supply all raw,
processed, and output paths explicitly. Do not mix source snapshots silently.

## Official inputs

The [TSE results dataset](https://dadosabertos.tse.jus.br/dataset/resultados-2026)
provides the following archives:

1. `votacao_secao_2026_BR.zip`: presidential votes by section and ballot number.
2. `detalhe_votacao_secao_2026.zip`: electorate, turnout, abstention, and section
   status. Only its `*_BR.csv` presidential member is loaded.
3. `detalhe_votacao_munzona_2026.zip`: independent municipal/zone summaries for
   reconciliation. Only `*_BR.csv` is loaded.
4. `votacao_candidato_munzona_2026.zip`: official candidate vote destinations,
   used to distinguish valid candidate votes from technically null ballots.

`BRASIL` consolidated files and state members are never added to the `BR`
member, which would double count presidential records. Only ordinary
presidential elections in the requested year are used. Both rounds must exist
with exactly one election ID per round and exactly two runoff finalists.
Overseas voting (`ZZ`) is retained in normalized inputs but excluded from the
domestic municipality analysis; Brasília and other TSE municipality units are
retained as represented in the source.

The TSE dataset notes mention 39 duplicate electorate records related to
temporary transfers. Raw official counts are preserved, and the note is stored
in the manifest. The project does not arbitrarily subtract them from sections.

## Methods and their interpretation

### Observations, validation, and matching

Section keys are **UF + TSE municipality + electoral zone + section**. Duplicate
detail records fail ingestion. Vote counts are reconciled to section turnout;
turnout plus abstention must equal the electorate. Installed, non-annulled
sections with nonnegative, internally consistent counts are usable.

Full municipality counts include all available section records. Transition
analysis and the section statistics additionally require both rounds, equal
eligible-voter counts, the same polling-place code, and no third candidate in
round two. Unmatched, changed, and unusable sections are retained with flags,
not replaced by zeros. Equal electorate counts are a screening rule; they do
not prove that registry membership is identical. Flow analysis assumes a common
underlying electorate in the retained sections.

Reference summaries are reconciled independently and all differences are
exported. A mismatch remains visible instead of silently adjusting a source.
The `analyzed_*` columns describe only retained sections. Unprefixed municipality
totals describe the full available electorate. Read coverage before comparing
them or generalizing a fitted result to an entire municipality.

### Accounting identity

For A and B as the finalists and O as first-round votes for other valid
candidates:

```text
ΔA + ΔB = O₁ + Δturnout − Δ(blank/null)
```

This is a conservation identity, not evidence identifying who changed their
vote. Net turnout and net blank/null changes do not measure gross individual
flows. Every retained section receives an accounting residual check.

### Bounds on gross mobilization flows

For each retained section, let `M₁ = blank/null₁ + abstention₁` and
`V₁ = A₁ + B₁ + O₁`. The number of people from M voting for A in round two has
the unrestricted sharp bounds:

```text
max(0, A₂ − V₁) ≤ M→A ≤ min(A₂, M₁)
```

Bounds are computed per section and then summed, which is at least as
informative as first pooling all sections. They permit arbitrary switching,
abstention, and changes to blank/null votes.

If **B→A switching is prohibited**, a conditional lower bound is:

```text
M→A ≥ max(0, ΔA − O₁)
```

This is the counterpart of the thread's 206-vote argument. It is explicitly
conditional, not an unconditional proof of origins. The corresponding quantities
are reported symmetrically for B. `no_cross_section_infeasible` counts sections
where prohibiting both A→B and B→A already contradicts the margins. A global
no-switch interpretation is unavailable if even one retained section is
incompatible with that assumption.

### Correlations and geographic descriptions

Pearson correlations compare section gains with `Δturnout − Δ(blank/null)`.
Fewer than three sections or constant variables produce a missing correlation,
not zero. These variables are connected by the accounting identity; the
correlation is not independent causal evidence of mobilization. Counts can
also reflect section size. Polling-place aggregates are exported separately;
their scope is the retained sections, not every section at that place.

### Proportional-allocation check

The comparison allocates the **net** increase in valid votes in the section
according to the first-round A/B shares, assumes the original finalist votes
are retained, and checks whether the required allocation from O is in `[0,O₁]`.
Sections with no first-round finalist votes or a negative net increase are
marked untestable for this "additional voter" interpretation.

Infeasibility rejects this combined allocation/retention scenario. It does not
uniquely identify the flow model below or prove a campaign mechanism. This
explicit test need not match the original thread's undocumented treatment of
turnover or negative net changes.

### Explicit ecological transition model

For section s:

```text
xₛ = [A₁, B₁, O₁, blank/null₁, abstention₁]
yₛ = [A₂, B₂, blank/null₂, abstention₂]
```

Fit one common 5×4 rate matrix P per municipality by minimizing
`Σₛ ||xₛP − yₛ||² / Nₛ`, subject to nonnegative rates, each origin row summing
to one, and exact municipality destination margins. SLSQP solves this convex
quadratic problem using analytical gradients. Fractional expected voter counts
are exported; they are not identified people. Municipal margins reconcile by
construction, whereas section predictions generally have residuals. Section
RMSE, maximum residual, aggregate margin error, design rank, and condition
number are exported so fit and weak designs remain visible.

The **full** model allows every transition. A **no_cross** sensitivity model
prohibits A↔B switches and retains all other transitions. Its restrictions are
assumptions, not observations. Cities with fewer than ten retained sections or
design rank below five are not assigned a fitted matrix. Passing those checks
does not establish that transition rates are actually constant across sections
or guarantee strong identification; examine the condition number and fit.

The full model is refitted on 150 independent section bootstrap resamples with
replacement, using a reproducible municipality-specific random seed. Resampled
rates are applied to the original municipality origin totals before computing
2.5%, median, and 97.5% flow quantiles. Failed/rank-deficient draws are counted;
fewer than 80% successful draws are flagged. Quantiles with low success remain
visible but must be interpreted with that flag. These ranges measure
resampling sensitivity **under the model**, not uncertainty in the complete
election count, arbitrary alternative models, or spatial dependence.
No-cross estimates are a sensitivity comparison without bootstrap intervals.

## Timing audit: separate data requirement

The nationwide vote analysis does **not** include the raw voting-machine event
logs. Consequently, it makes no claim about the national number of votes after
17:00 or before 11:00. The TSE provides raw logs through its
[transmitted-files dataset](https://dadosabertos.tse.jus.br/dataset/resultados-2026-arquivos-transmitidos-para-totalizacao)
and [technical download documentation](https://www.tse.jus.br/eleicoes/informacoes-tecnicas-sobre-a-divulgacao-de-resultados).
Raw extraction is version-specific and must account for replacement machines,
retransmissions, archived events, and machine clock/timezone conventions.
BU receipt times in the results files are **not** voting times.

A streaming audit command is implemented for normalized event CSVs, sorted by
`uf,municipality_code,zone,section,round` (numeric sorting for numeric fields):

```text
uf,municipality_code,zone,section,round,machine_id,event_id,event_type,timestamp
SC,81914,77,39,2,example-machine,example-event,vote_computed,2026-10-25T16:58:00-03:00
```

The line above illustrates the format; it is not a downloaded vote record.
`event_id` identifies a log event, never a voter. Timestamps must include an
explicit UTC offset. Only `vote_computed` events are counted. Exact duplicate
machine events are deduplicated; conflicting duplicates fail. The counts must
reconcile to section turnout before their timing contributes to the audited
municipal totals. Missing and mismatched logs remain explicit coverage failures.
The audit does not prove an upstream raw-log extractor has selected the right
events, or validate machine clock accuracy.

```bash
python -m elections timing --events data/events_sorted.csv --round-one-date 2026-10-04 --round-two-date 2026-10-25
```

The cutoff is explicitly `timestamp >= 17:00:00` in Brasília time and the
morning measure is `timestamp < 11:00:00`. Offset conversion matters for
municipalities outside the Brasília timezone. These are separate timing
exports; the primary report keeps its `logs_status=not_loaded` label.

## Outputs

| File | Contents |
|---|---|
| `report.html` | Offline searchable municipality report with observed counts, bounds, flow estimates, and diagnostics |
| `municipalities.csv` | Full totals, analyzed-subset statistics, coverage, model diagnostics |
| `sections.csv.gz` | Both-round section records, eligibility flags, deltas, bounds, allocation checks |
| `reference_audit.csv` | Section aggregates compared with independent official municipal/zone summaries |
| `estimated_flows.csv.gz` | Full and no-cross estimates; bootstrap ranges for the full model |
| `polling_places.csv.gz` | Retained-section counts grouped by polling place |
| `national_overview.png/.pdf` | Exportable correlation and coverage histograms |
| `summary.json`, `run.json` | National coverage, candidate identities, settings, and run metadata |

The tests cover a switching counterexample to the unconditional 206-vote
interpretation, sharp bounds checked against linear programming, recovery of
known synthetic transition rates, exact model margins, sensitivity restrictions,
small/rank-deficient cities, matching failures, reproducible resampling, and
timing timezone/coverage rules. Synthetic test cases are not election evidence.
