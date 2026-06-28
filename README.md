# SEO-Research

Python CLI research scaffold for DataForSEO/TextRazor SEO ranking similarity
analysis.

The intended implementation expands a seed keyword into a keyword cluster,
collects top-20 organic SERP results through DataForSEO, retrieves provider
parsed page text, computes passage-to-keyword semantic similarity, captures
TextRazor entities for future work, and reports observational ranking variation
results.

Current repository state:

- `pyproject.toml` exists with a setuptools package definition and `seo-rank`
  console script.
- `src/seo_rank/` exists but currently contains only the package marker and a
  stub CLI entrypoint.
- `tests/` is configured as the pytest discovery root, but there are currently
  no discoverable test source files in the working tree.
- `python -m pytest` is the active verification command and currently exits
  with `0` collected tests.

Start here:

- Root architecture summary: `ARCHITECTURE.md`
- Detailed architecture: `docs/architecture/ARCHITECTURE.md`
- First implementation plan:
  `docs/implementation/dataforseo-textrazor-ranking-similarity-plan.md`
- Testing contract: `TESTING.md`
- SDLC contract: `AGENTS.md`
