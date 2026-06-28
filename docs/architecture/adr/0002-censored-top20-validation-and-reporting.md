# ADR 0002: Censored Top-20 Validation And Reporting

## Status

Accepted

## Context

Organic rank data is only observed for results that appear in the collected SERP
window. For this product, the window is the organic **top 20**. Results below
rank 20 are unobserved for modeling purposes.

## Decision

1. Normalize and analyze only organic results with rank 1–20 (configurable via
   `--depth`, default 20).
2. Treat ranks outside the collection window as **censored**, not missing at
   random.
3. Require reports and statistical outputs to describe this censoring constraint
   and avoid extrapolation below the observed window.
4. Filter non-organic SERP item types (e.g. paid) before normalization.

## Consequences

- Similarity and ranking models describe variation **within** the observed
  top 20, not the full SERP or full index.
- Domain- and page-level similarity features join to censored rank rows only.
- Future analysis code must document the censoring assumption in run artifacts.

## Current implementation note

`normalize_serp_results()` in `dataforseo.py` keeps organic rows only and caps
count by `depth`. Statistical modeling and censored-data reporting are not
implemented yet.
