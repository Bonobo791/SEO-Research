# DataForSEO + TextRazor Ranking Similarity Implementation Plan

## Summary

Build a Python CLI scaffold for a first research run:

1. Expand a seed keyword into a keyword cluster.
2. Collect the top 20 organic results for each keyword.
3. Retrieve canonical page text through DataForSEO.
4. Split each page into paragraph passages.
5. Compute cosine similarity between each passage and the ranking keyword.
6. Aggregate similarity at the page level.
7. Test whether similarity features explain variation in observed top-20
   rankings.

TextRazor entities should be captured and normalized from the same DataForSEO
page text, but entity-derived features are out of scope for the first model.

## Defaults And Scope

- Runtime: Python CLI.
- Default keyword cluster size: 25 keywords from seed expansion.
- Default SERP depth: top 20 organic results.
- Default location: user supplied, usually `United States`.
- Default language: `en`.
- Default device: `desktop`.
- Page text source: DataForSEO OnPage content parsing.
- Similarity stack: local `sentence-transformers`.
- Passage strategy: DataForSEO parsed paragraph/headings text blocks.
- Analysis: regression primary, predictive importance secondary.
- Outputs: Markdown report plus machine-readable JSON artifacts.

V1 must not directly fetch pages outside DataForSEO, model TextRazor entity
features, or make causal claims.

## Endpoints And Data To Retrieve

### DataForSEO Keyword Expansion

Use DataForSEO Labs keyword endpoints exposed through the MCP/API.

Primary candidates:

- Related keywords: `_dataforseo_labs_googl_57cf2ab3dd81`
- Keyword data / enrichment: `_dataforseo_labs_googl_88fad45051ba`
- Google Ads search volume fallback: `_kw_data_google_ads_search_volume`

Retrieve and normalize:

- Seed keyword.
- Expanded keyword.
- Search volume.
- CPC and competition when available.
- Source endpoint.
- Expansion rank/order.
- Location and language.

Filter behavior:

- Deduplicate case-insensitively.
- Include the seed keyword.
- Keep the highest-volume or first-seen duplicate.
- Cap to 25 keywords by default.
- Preserve provenance for every keyword.

### DataForSEO SERP Collection

Use organic live advanced SERP collection:

- `_serp_organic_live_advanced`

Request fields:

- `keyword`
- `language_code`
- `location_name`
- `device`
- `search_engine=google`
- `depth=20`

Retrieve and normalize:

- Keyword.
- Rank group / organic rank position.
- Absolute rank if available.
- URL.
- Domain.
- Title.
- Snippet / description.
- SERP item type.
- Collection timestamp.
- Device, language, location, and search engine.

Only organic results should be included in the first analysis dataset.

### DataForSEO Page Text

Use DataForSEO OnPage parsing as the canonical scrape source:

- `_on_page_content_parsing`

Optional metadata endpoint:

- `_on_page_instant_pages`

Retrieve and normalize:

- Requested URL.
- Final URL when available.
- Crawl/parse status.
- Page title.
- Headings.
- Paragraph or textual content blocks.
- Link URLs and anchors when returned.
- Parse timestamp.
- Provider errors and warnings.

Passage extraction starts from paragraph/headings text blocks. Empty or very
short blocks must be discarded before embedding.

### TextRazor Entities

Use the TextRazor REST API with `TEXTRAZOR_API_KEY`.

Request shape:

- Send DataForSEO parsed page text, not the original URL.
- Use `extractors=entities`.
- Keep provider-specific request logic inside `providers/textrazor.py`.

Retrieve and normalize:

- Matched text.
- Entity id.
- Relevance score.
- Confidence score.
- Entity type(s).
- Freebase, DBpedia, Wikidata, or equivalent links when returned.
- Source URL and passage/page context.
- Provider errors and warnings.

Entity features are captured for future work but excluded from the first
ranking-variation model.

## Internal Data Flow

Recommended package layout:

```text
src/
  seo_rank/
    cli.py
    config.py
    run.py
    providers/
      dataforseo.py
      textrazor.py
    serp/
      schemas.py
      normalizer.py
    text/
      passages.py
      embeddings.py
      similarity.py
    entities/
      normalizer.py
    analysis/
      variance.py
      diagnostics.py
    reports/
      markdown.py
      json_report.py
    storage/
      runs.py
tests/
  unit/
  fixtures/
```

Run artifact layout:

```text
runs/
  RUN_ID/
    input.json
    cluster.json
    serp_raw/
    pages_raw/
    textrazor_raw/
    observations.json
    passages.json
    similarity_features.json
    entities.json
    analysis.json
    report.md
```

## CLI Contract

Primary command:

```bash
seo-rank run \
  --seed "best crm software" \
  --location "United States" \
  --language en \
  --device desktop \
  --cluster-size 25 \
  --depth 20
```

Useful options:

- `--output runs/`
- `--enable-javascript` for DataForSEO page parsing.
- `--model-name` for the sentence-transformers model.
- `--skip-textrazor` for local testing without entity extraction.
- `--dry-run` to validate config and show planned provider calls.

Required environment variables:

```text
DATAFORSEO_LOGIN
DATAFORSEO_PASSWORD
TEXTRAZOR_API_KEY
```

## Similarity Features

For each `(keyword, URL)` observation:

- Embed the keyword with the local sentence-transformers model.
- Embed each extracted passage.
- Compute cosine similarity for every passage.
- Store per-passage similarity with passage index and text provenance.

Aggregate page-level features:

- `mean_similarity`
- `max_similarity`
- `top3_mean_similarity`
- `passage_count`

These features are joined to rank observations by keyword and URL.

## Analysis Behavior

Default target:

```text
log_rank = log(rank_position)
```

Models to report:

- Intercept-only baseline.
- Keyword-controls-only baseline.
- Similarity-feature regression model.
- Secondary predictive importance check over the same feature table.

Required report language:

- Results are observational.
- The sample is censored to collected top-20 organic results.
- Explained variation applies only to observed ranking position within the
  keyword cluster.
- Similarity may be associated with rank variation but does not prove causation.

## Testing Plan

Add deterministic tests using fixtures and mocked providers:

- DataForSEO request construction and auth handling.
- TextRazor request construction and auth handling.
- Keyword expansion deduplication and 25-keyword cap.
- SERP normalization for organic top-20 results.
- Page text normalization and empty/short passage filtering.
- Cosine similarity aggregation for multi-passage pages.
- Run orchestration with mocked provider clients.
- Analysis model comparison with synthetic ranking data.
- CLI smoke test that writes JSON and Markdown artifacts without network calls.

Run verification:

```bash
python -m pytest
```

## Implementation Notes

- Add `pyproject.toml` with package metadata, console script, and dependencies.
- Keep provider-specific payloads at the boundary and normalize into internal
  schemas.
- Store raw provider responses, but do not log or persist secrets.
- Use typed errors for auth failures, rate limits, timeouts, and malformed
  provider responses.
- Retry 429 and 5xx responses with exponential backoff and respect
  `Retry-After` when present.
- Keep direct page fetching out of v1.
