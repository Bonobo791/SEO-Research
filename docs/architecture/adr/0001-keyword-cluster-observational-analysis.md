# ADR 0001: Use Keyword-Cluster Observational Analysis for V1

## Status

Accepted

## Context

The system needs to analyze SEO ranking factors and report explanation of
variation for top-20 organic rankings. A single SERP provides only 20
observations, which is too small for reliable variation explanation.

The requested direction is CLI-only, with DataForSEO as the SERP/page-text
provider and TextRazor as the entity provider. The first version should focus on
measurement quality, provenance, and disciplined statistical reporting rather
than a web application or causal experimentation platform.

## Decision

V1 will use keyword clusters as the primary unit of analysis.

Each cluster contains related keywords with shared search context such as
country, language, device, and search engine. For each keyword, the system
collects the top 20 organic ranking results from DataForSEO. The analysis
dataset is built from all ranked observations across the cluster.

Default target:

```text
log_rank = log(rank_position)
```

The system will also store raw `rank_position` and can later add
`inverse_rank_score`, `top_3`, and `top_10` for alternate analyses.

## Consequences

Positive consequences:

- More observations than single-SERP analysis.
- Better statistical power for explained-variation reporting.
- Ability to include keyword-level controls.
- Better visibility into whether signals are stable across related queries.
- Natural path toward batch analysis.

Negative consequences:

- Collection costs are higher than single-keyword analysis.
- Reports need to explain cluster scope carefully.
- Confounding by keyword intent, SERP features, and domain repetition must be
  handled explicitly.

## Alternatives Considered

### Single keyword SERP analysis

Rejected for v1. It is operationally simple but statistically weak. Twenty
observations cannot support meaningful explained-variation claims.

### Domain watchlist analysis

Deferred. It is useful for competitive monitoring but would bias v1 around
target domains rather than general measurement.

### Full causal experimentation platform

Deferred. Split tests and quasi-experimental designs require trustworthy
measurement infrastructure first.

## Follow-Up Decisions

- Define minimum keyword and observation counts for analysis warnings.
- Decide whether local storage remains file-based or moves to SQLite after the
  first prototype.
- Define any future TextRazor entity-derived feature set.
