# ADR 0002: Treat Top-20 Ranking Data as Censored and Require Validation Guardrails

## Status

Accepted

## Context

V1 analyzes URLs observed in the top 20 organic results for each keyword in a
cluster. This is not a complete sample of all pages that could rank for a query.
It is a censored sample limited to pages already visible in the collected SERP
window.

The first model uses user-selected similarity features that may be correlated
with domain identity, keyword intent, or collection timing. Without explicit
guardrails, reports could overstate explained variation or confuse descriptive
associations with predictive or causal findings.

## Decision

V1 reports will treat top-20 organic ranking data as censored observational
data.

The analysis engine must include:

- Intercept-only baseline.
- Keyword-controls-only baseline.
- Similarity-feature regression model.
- Secondary predictive importance check over the same feature table.
- Residual and missingness warnings by keyword, domain, and rank bucket when
  data is sufficient.
- Leakage checks based on timestamps, feature provenance, and rank-derived
  predictors.

Reports must state that explained variation applies to observed top-20 ranking
position within the collected keyword cluster, not total ranking probability
across all candidate pages.

## Consequences

Positive consequences:

- Reduces the risk of inflated or misleading model results.
- Separates descriptive, predictive, and causal language.
- Makes validation behavior explicit before implementation.

Negative consequences:

- Reports are more complex.
- Some analyses will produce warnings instead of clean conclusions.
- Validation may be noisy for small clusters.

## Alternatives Considered

### Treat top-20 observations as an ordinary complete ranking dataset

Rejected. This would make implementation simpler but would misrepresent the
sampling frame and encourage overbroad conclusions.

### Use only predictive machine-learning models

Rejected for v1. Predictive models can be useful later, but the first version
needs interpretable baselines, diagnostics, and uncertainty language.

### Wait for causal experimentation before reporting findings

Rejected. Observational analysis is still useful when it is clearly labeled and
disciplined. Causal modules can be added after measurement quality is
established.

## Follow-Up Decisions

- Define exact thresholds for high domain repetition.
- Define minimum keyword count and observation count for grouped validation.
- Define report severity levels for leakage, censoring, missingness, and
  instability warnings.
