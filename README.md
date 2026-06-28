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

## Product direction (Phase 3)

Full cluster orchestration is in place for offline and explicitly gated live
provider runs. Each target keyword gets its own SERP, page text, passages,
fixture similarity features, TextRazor entities, and raw provider payloads under
`keyword_results`; flattened normalized rows also carry `target_keyword` for
downstream consumers. `--live-providers` requires
`SEO_RANK_ENABLE_LIVE_PROVIDERS=1` and valid provider credentials before
executing live provider calls.

Later phases remain planned after that: top-20 organic SERPs at passage / page /
domain scope, dual live similarity backends every run, and `statsmodels` OLS
with Benjamini-Hochberg after OLS pre-analysis diagnostics.

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
