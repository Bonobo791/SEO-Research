# ADR 0001: Keyword-Cluster Observational Analysis

## Status

Accepted

## Context

Ranking research often starts from one seed keyword, but observed SERPs and page
content vary across related queries. We need a repeatable CLI workflow that
expands a seed into a keyword cluster and compares similarity features to
observed ranks without implying causation.

## Decision

1. Expand each seed into a capped keyword cluster (default cap: 25 keywords).
2. Treat ranking analysis as **observational**: similarity features may
   correlate with rank variation within the observed top 20; they do not prove
   ranking factors.
3. Use DataForSEO as the canonical provider for keyword expansion, SERP
   collection, and parsed page text in v1.
4. Capture TextRazor entities from parsed page text for future work, but exclude
   entity-derived features from the first ranking-variation model.

## Consequences

- The CLI must preserve raw provider payloads alongside normalized rows for
  audit and later live integration.
- Reports must state observational limits explicitly.
- Causal language and entity-based model features stay out of scope until a
  later ADR or goal revision.

## Current implementation note

Offline fixtures implement keyword expansion normalization and a single-keyword
SERP/page-text path for the first cluster keyword. Full per-keyword cluster
iteration is planned, not yet shipped.
