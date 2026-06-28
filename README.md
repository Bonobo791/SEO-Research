# SEO-Research

Python CLI research scaffold for DataForSEO/TextRazor SEO ranking similarity
analysis.

The intended implementation expands a seed keyword into a keyword cluster,
collects top-20 organic SERP results per cluster keyword through DataForSEO,
retrieves provider parsed page text, and scores cosine similarity at passage,
page, and domain URL scope against the keyword that generated each SERP (domain
URLs as a content proxy; up to 1000 URLs per domain, skip larger domains).

**Every live run** must execute **both** similarity backends and **full**
statistical analysis:

- **Similarity (both required each run):** cross-encoder `BGE-reranker-v2` and
  bi-encoder Gemini embedding with cosine similarity alone.
- **Analysis (required each run):** `statsmodels` OLS residual/variance models
  plus Benjamini-Hochberg multiple-testing correction on keyword- and
  feature-level comparisons. Complete OLS pre-analysis diagnostics (linearity,
  multicollinearity, exogeneity review, homoscedasticity, normality, influence)
  **before** interpreting results; see `ARCHITECTURE.md` § OLS Pre-Analysis
  Preparation.

TextRazor entities are captured for future work. The offline CLI scaffold today
uses fixture embeddings only; dual-backend similarity and per-run stats analysis
are the documented contract for live runs.

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
