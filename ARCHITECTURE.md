# Architecture

## Stack

- Language: Python
- Runtime: CLI
- Source directory: `src/seo_rank/`
- Test directory: `tests/`
- Package manifest: `pyproject.toml`
- Analysis library: `statsmodels` for observational ranking models (planned;
  not yet a runtime dependency); `numpy`, `scipy`, `patsy`, and `linearmodels`
  for OLS diagnostics, IV/panel extensions, and supporting tests (planned)
- Similarity backends: deterministic fixture embeddings for offline tests today;
  cross-encoder `BGE-reranker-v2` and bi-encoder Gemini embedding plus cosine
  similarity alone when live similarity evaluation begins (planned; not yet
  runtime dependencies)
- Deployment: none
- Databases: none
- Cache layer: none
- CI: none configured

## Overview

SEO-Research is a Python CLI application scaffold for research-grade SEO
ranking analysis. The first version will expand a seed keyword into a keyword
cluster, collect top-20 organic SERP results through DataForSEO, retrieve
provider-parsed page text, compute passage-to-keyword semantic similarity, and
report whether similarity features explain variation in observed rankings.

TextRazor entities will be captured and normalized from the same DataForSEO page
text, but entity-derived model features are out of scope for the first model.

The detailed product architecture lives in
`docs/architecture/ARCHITECTURE.md`. The first implementation plan lives in
`docs/implementation/dataforseo-textrazor-ranking-similarity-plan.md`.

## Current Components

- `AGENTS.md`: repo process contract. It requires strict TDD for code-shaped
  changes and all configured tests passing before commit.
- `SDLC-LOOP.md`: operating loop for planning, red/green proof, review, and
  escalation.
- `START-SDLC.md`: session-start prompt for working in SDLC mode.
- `PROVE-IT.md`: pre-commit proof checklist and proof-stamp instructions.
- `.agents/skills/sdlc/SKILL.md`: repo-local SDLC skill entrypoint. Use `$sdlc`
  for implementation work.
- `.codex/config.toml`: repo-local Codex model and hook settings.
- `.codex/hooks.json`: portable hook wiring using Node entrypoints.
- `.codex/hooks/*.cjs`: active hook implementations for session, git, and
  compaction guards.
- `.codex-sdlc/manifest.json`: setup scan results and confirmed preferences.
- `docs/architecture/`: product architecture and ADRs.
- `docs/implementation/`: first implementation plan.

## Application Surface

The repository now contains the first project scaffold:

- Source directory: present at `src/seo_rank/`
- Test directory: present at `tests/`
- Package manager or dependency manifest: present at `pyproject.toml`
- Current package contents: `__init__.py` and `cli.py` with an offline `run`
  command that writes JSON and Markdown artifacts from fixtures
- Current test status: pytest collects unit tests under `tests/unit/`
- Database: not present
- Cache layer: not present
- Deployment target: not present
- CI workflow: not present

Implementation has started. The runnable product surface is still minimal, but
`python -m pytest` now verifies the offline CLI smoke path and SDLC doc guards.
Provider boundaries, normalization, and similarity features remain planned work.

## Key Product Components

- CLI: accepts seed keyword, location, language, device, cluster size, SERP
  depth, output directory, model name, JavaScript parsing option, `--dry-run`,
  and `--skip-textrazor`.
- Provider clients: DataForSEO for keyword expansion, SERP collection, and page
  text parsing; TextRazor for entity extraction from parsed page text.
- Normalizers: preserve raw provider responses and normalize them into stable
  internal schemas.
- Text pipeline: split page text into paragraph/headings passages, embed keyword
  and passages, compute cosine similarity, and aggregate page-level features.
  Offline runs use deterministic fixture vectors. Live runs follow the planned
  cosine-similarity procedure in [Planned Cosine Similarity Run](#planned-cosine-similarity-run).
- Analysis engine: on every run, complete OLS pre-analysis preparation, then
  compare baseline and similarity-feature models over observed top-20 rankings
  with mandatory `statsmodels` OLS residual/variance modeling and
  Benjamini-Hochberg multiple-testing correction. See [Planned Per-Run Statistical
  Analysis](#planned-per-run-statistical-analysis) and [OLS Pre-Analysis
  Preparation](#ols-pre-analysis-preparation).
- Reporters: emit machine-readable JSON artifacts and a Markdown report.

## Data Flow

Seed keyword input flows through keyword expansion, SERP collection, page text
parsing, TextRazor entity capture, passage extraction, dual-backend similarity
feature generation (cross-encoder and bi-encoder on every live run), rank-feature
joining, mandatory `statsmodels` OLS analysis with Benjamini-Hochberg correction,
and report generation.

Raw provider responses and generated run artifacts should stay out of source
control.

## Planned Cosine Similarity Run

Live similarity evaluation runs once per keyword in the expanded keyword
cluster. For each cluster keyword:

1. Collect the organic **top-20 SERP** for that keyword. That keyword is the
   **target keyword** for every similarity score derived from that SERP. Passage,
   page, and domain scores always use the keyword that generated the SERP, not
   other keywords in the cluster.
2. For **each organic result** in that top 20:
   - **Passage scope:** extract passages from the result's parsed page text and
     score each passage against the target keyword.
   - **Page scope:** score the full parsed page content of the result against
     the target keyword.
   - **Domain scope:** score the URLs on the result's domain against the target
     keyword. Use the URL list as a proxy for site-wide content; do not require
     a full body fetch for every URL. Keep at most **1000 URLs** per domain and
     **skip domains whose URL inventory exceeds 1000**.

Compare **both** backends on **every** live similarity run (not a one-off
experiment):

- Cross-encoder: `BGE-reranker-v2`
- Bi-encoder: Gemini embedding with cosine similarity alone

Each backend produces passage-, page-, and domain-level scores for the same
top-20 SERP rows so results stay comparable run to run.

## Planned Per-Run Statistical Analysis

Every completed run must include observational ranking analysis, not only
similarity feature generation. **Before interpreting results or applying
Benjamini-Hochberg correction**, complete [OLS Pre-Analysis
Preparation](#ols-pre-analysis-preparation) on the run dataset.

1. Fit baseline and similarity-feature models with **`statsmodels` OLS**
   residual/variance modeling over the observed top-20 rankings, following the
   diagnostic workflow below.
2. Apply **Benjamini-Hochberg** multiple-testing correction across keyword- and
   feature-level comparisons produced by that run.
3. Emit similarity-backend outputs, diagnostic artifacts, and statistical
   analysis into the run outputs (JSON plus Markdown report sections).

Do not skip either similarity backend or the statistical analysis step on
individual runs unless the run is an explicit offline fixture or dry-run test
mode documented in the CLI contract.

## OLS Pre-Analysis Preparation

Before running ranking-variation analysis on a prepared run dataset, fit and
validate the OLS specification. Detect problems first; **fix only when a check
flags an issue or theory supports a revision**. After every correction, refit
the model and rerun all diagnostics on the revised specification.

### Fit a preliminary OLS model first

Use `statsmodels.OLS` or `statsmodels.formula.api.ols`. Retain fitted values,
residuals, and the design matrix for all downstream diagnostics.

### Linearity — detect

- Plot residuals versus fitted values with a LOWESS smoother using
  `statsmodels.nonparametric.smoothers_lowess.lowess`.
- Run `statsmodels.stats.diagnostic.linear_reset`.
- Inspect component-plus-residual plots with
  `statsmodels.graphics.regressionplots.plot_ccpr_grid`.

**Fix only if curved patterns or RESET indicate misspecification:** add
theory-supported polynomial terms, interactions, `np.log(x)` for positive
predictors, or spline terms with `patsy.bs`; refit and repeat the checks.

### Multicollinearity — detect only when there is more than one predictor

- Calculate VIF for each non-intercept predictor with
  `statsmodels.stats.outliers_influence.variance_inflation_factor`.
- Calculate a condition number with `numpy.linalg.cond`.

**Flag for review:** VIF above about 5, condition number above about 30, exact
duplicate columns, or near-perfect correlations.

**Fix only if flagged:** drop one redundant predictor, combine conceptually
overlapping predictors into an index, or mean-center continuous predictors
before creating polynomial and interaction terms. Use PCA or ridge only when
prediction—not standard OLS coefficient interpretation—is the goal.

### Exogeneity — assess

Do not use residual plots or a generic Python test to claim exogeneity. Require a
causal DAG, variable timing, and domain review to identify omitted confounders,
reverse causality, colliders, and measurement problems.

**Test only in a valid identification setup:** where a credible instrument
exists, fit `linearmodels.iv.IV2SLS` and run `wu_hausman()`; assess instrument
relevance through first-stage diagnostics.

**Fix only if an issue is plausible:** add justified **pre-treatment**
confounders, use panel fixed effects with `linearmodels.panel.PanelOLS` when
appropriate, or use IV/2SLS with a defensible instrument. Do not treat
transformations as an exogeneity fix.

### Homoscedasticity — detect

- Plot residuals versus fitted values.
- Run `statsmodels.stats.diagnostic.het_breuschpagan` and optionally `het_white`.

**Fix only if variance is nonconstant:** refit inference using HC3 robust
standard errors (`cov_type="HC3"`). Use `statsmodels.WLS` only when justified
inverse-variance weights are available. Consider a substantively justified
outcome transformation, then recheck residuals.

### Normality of errors — detect

- Create a Q-Q plot with `statsmodels.graphics.gofplots.qqplot`.
- Use `scipy.stats.shapiro` for small samples or `scipy.stats.normaltest` for
  larger samples. Treat large-sample test rejections cautiously.

**Fix only if non-normality materially affects small-sample inference:** first
address outliers, nonlinearity, and heteroscedasticity. Then use bootstrap
confidence intervals, a justified outcome transformation, or a more suitable
model family such as `statsmodels.GLM` for binary, count, or strongly skewed
outcomes.

### Influential observations — detect

Use `results.get_influence()` and extract leverage (`hat_matrix_diag`),
externally studentized residuals (`resid_studentized_external`), Cook's distance
(`cooks_distance`), DFFITS, and DFBETAs.

**Flag for review** (where `p` includes the intercept, `n` is sample size):

- Leverage > `2p/n`
- Absolute studentized residual > 3
- Cook's distance > `4/n`
- DFFITS > `2 * sqrt(p/n)`
- Absolute DFBETA > `2/sqrt(n)`

**Fix only if necessary:** correct verified data errors. Do not automatically
delete valid observations. Refit the model with and without flagged valid cases
as a sensitivity analysis; use `statsmodels.RLM` as an additional robustness
check when conclusions are highly sensitive.

### After every correction

Refit the model and rerun **all** diagnostics on the revised specification
before proceeding to Benjamini-Hochberg correction and run reporting.

## Decisions

- Build as a CLI-first Python application.
- Use DataForSEO as the canonical SERP and page-text source.
- Send DataForSEO parsed page text to TextRazor; do not send original URLs for
  entity extraction.
- Keep direct page fetching out of v1.
- Treat analysis as observational and censored to observed top-20 rankings.
- Use `statsmodels` for OLS residual/variance models and Benjamini-Hochberg FDR
  correction on every run; complete [OLS Pre-Analysis
  Preparation](#ols-pre-analysis-preparation) before interpreting results; do not
  introduce a parallel stats stack for the same work.
- Keep deterministic fixture embeddings for offline cosine-similarity tests.
  Live runs follow [Planned Cosine Similarity Run](#planned-cosine-similarity-run):
  per cluster keyword, top-20 SERP, then passage, page, and domain URL scoring
  against that keyword's target keyword only.
- Capture TextRazor entities for future work but exclude entity-derived features
  from the first ranking-variation model.
- Continue filling in the real package under `src/seo_rank/` and add
  discoverable tests under `tests/`.
- Keep significant architecture decisions in `docs/architecture/adr/`.

## Codex And SDLC Flow

The canonical implementation entrypoint is `$sdlc`. Codex does not have a
native `/sdlc` command in this repo, and repo docs should not imply one exists.

Execution lane guidance:

- Use CLI for repository edits, tests, docs, hooks, commits, and ordinary
  verification.
- Use Desktop/computer-use first for browser sign-in, Microsoft tenant flows,
  MFA, Office UI, admin portals, screenshots, or desktop-only state. Start it
  from the repo root with `codex app .` on macOS or Windows.
- Keep credentials, MFA, tenant consent, sends, deletes, license/admin changes,
  and policy publishing as explicit human actions.
