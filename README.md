# SEO-Research

Python CLI research scaffold for DataForSEO/TextRazor SEO ranking similarity
analysis.

## What works today

Offline `seo-rank run` expands a seed keyword from fixtures, normalizes SERP
rows, passages, page-level similarity features, and optional TextRazor
entities, then writes JSON and Markdown artifacts with **no network calls**.

```bash
python -m pytest
seo-rank run --seed "technical seo" --dry-run --output-dir artifacts
```

## Product direction (planned)

Per cluster keyword: top-20 organic SERP, similarity at passage / page / domain
URL scope, dual backends every run (`BGE-reranker-v2` + Gemini cosine),
`statsmodels` OLS with Benjamini-Hochberg after OLS pre-analysis diagnostics.
Not implemented in code yet.

## Repository layout

| Path | Purpose |
|------|---------|
| `src/seo_rank/` | CLI and offline provider boundaries |
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
