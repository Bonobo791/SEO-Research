# SEO-Research

Python CLI research scaffold for DataForSEO/TextRazor SEO ranking similarity
analysis.

The intended implementation expands a seed keyword into a keyword cluster,
collects top-20 organic SERP results through DataForSEO, retrieves provider
parsed page text, computes passage-to-keyword semantic similarity, captures
TextRazor entities for future work, and reports observational ranking variation
results.

Current repository state:

- `pyproject.toml` defines the `seo-rank` console script and pytest config.
- `src/seo_rank/` contains the package marker and an offline `run` CLI that
  writes JSON and Markdown artifacts from fixtures.
- `tests/unit/` contains the active pytest suite, including an offline CLI smoke
  test and SDLC doc guards.
- `python -m pytest` is the active verification command.

Start here:

- Root architecture summary: `ARCHITECTURE.md`
- Detailed architecture: `docs/architecture/ARCHITECTURE.md`
- First implementation plan:
  `docs/implementation/dataforseo-textrazor-ranking-similarity-plan.md`
- Testing contract: `TESTING.md`
- SDLC contract: `AGENTS.md`
