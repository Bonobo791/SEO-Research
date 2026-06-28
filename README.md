# SEO-Research

Python CLI research scaffold for DataForSEO/TextRazor SEO ranking similarity
analysis.

## What works today

Offline `seo-rank run` expands a seed keyword from fixtures, normalizes SERP
rows, passages, page-level similarity features, and optional TextRazor
entities, then writes JSON and Markdown artifacts with **no network calls**.
Phase 2 provider request builders and credential validators are available for
offline verification, but live calls are not executed by default.

```bash
python -m pytest
seo-rank run --seed "technical seo" --dry-run --output-dir artifacts
```

## Product direction (Phase 2)

Live provider boundaries are in progress: DataForSEO request construction,
parsed-page TextRazor request construction, and credential validation are
implemented. Explicit flags or integration checks for non-default live calls are
next. The offline scaffold stays in place while those boundaries are added.

Later phases remain planned after that: per-cluster keyword execution, top-20
organic SERPs at passage / page / domain scope, dual similarity backends every
run, and `statsmodels` OLS with Benjamini-Hochberg after OLS pre-analysis
diagnostics.

## Repository layout

| Path | Purpose |
|------|---------|
| `src/seo_rank/` | CLI and provider boundaries |
| `tests/unit/` | pytest unit tests |
| `ARCHITECTURE.md` | Product architecture, data flow, planned pipeline |
| `GOALS.md` | Active-scope contract |
| `ROADMAP.md` | Phased backlog and history |
| `TESTING.md` | Verification contract |

## Documentation

- Architecture and planned pipeline: `ARCHITECTURE.md`
- Active scope: `GOALS.md`
- Backlog: `ROADMAP.md`
- Testing: `TESTING.md`
- Process: `AGENTS.md`, `SDLC.md`

Verification: `python -m pytest`
