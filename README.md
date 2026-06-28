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
| `tests/unit/` | 10 pytest unit tests |
| `docs/architecture/` | Detailed product architecture and ADRs |
| `docs/implementation/` | Phased implementation plan |
| `GOALS.md` | Active-scope contract |
| `ROADMAP.md` | Backlog and history |

## Documentation

- Root summary: `ARCHITECTURE.md`
- Product detail: `docs/architecture/ARCHITECTURE.md`
- Implementation phases: `docs/implementation/dataforseo-textrazor-ranking-similarity-plan.md`
- Testing: `TESTING.md`
- Process: `AGENTS.md`, `SDLC.md`

Verification: `python -m pytest`
