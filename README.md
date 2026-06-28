# SEO-Research

Python CLI research scaffold for DataForSEO/TextRazor SEO ranking similarity
analysis.

## What works today

Offline `seo-rank run` expands a seed keyword from fixtures, loops over every
capped cluster keyword, normalizes SERP rows, passages, page-level similarity
features, and optional TextRazor entities, then writes JSON and Markdown
artifacts with **no network calls**. Provider request builders and credential
validators are available for offline verification. The CLI also has a
non-default `--live-providers` gate, standard-library HTTP clients, and an
env-gated live smoke test.

```bash
python -m pytest
seo-rank run --seed "technical seo" --dry-run --output-dir artifacts
```

For live provider smoke tests, copy `.env.example` to `.env`, replace the
placeholder values, and source it in your shell before running the integration
test. The CLI reads environment variables from the process environment; it does
not auto-load `.env`.

## Product direction (Phase 4)

Phase 3 shipped full cluster orchestration: offline and gated live runs process
every capped keyword, group per-keyword outputs under `keyword_results`, and
annotate flattened rows with `target_keyword`.

Phase 4 adds dual live similarity backends (BGE-reranker-v2 + Gemini cosine) for
**page-level** content scoring on each top-20 organic SERP row. Passage and domain
scopes are Phase 5.5. Later: `statsmodels` OLS with Benjamini-Hochberg (Phase 5)
and `runs/RUN_ID/` reporting (Phase 6).

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
