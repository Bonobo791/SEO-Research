# Product Architecture

Detailed architecture for the SEO-Research CLI. Repo process and SDLC wiring
live in the root `ARCHITECTURE.md`.

## Purpose

Expand a seed keyword into a keyword cluster, collect organic SERP observations,
normalize provider-parsed page text, compute passage-level similarity features,
capture TextRazor entities for future work, and (planned) test whether
similarity features explain variation in observed top-20 rankings.

Analysis is **observational**. It does not claim causal ranking factors.

## Current Implementation (shipped)

### Package layout

| Module | Role |
|--------|------|
| `src/seo_rank/cli.py` | `seo-rank run` command, `RunConfig`, offline payload assembly, JSON/Markdown artifacts |
| `src/seo_rank/dataforseo.py` | Offline DataForSEO-shaped fixtures and normalizers for keyword expansion, SERP, page text |
| `src/seo_rank/text.py` | Passage splitting and short-text filtering from parsed page text |
| `src/seo_rank/similarity.py` | Deterministic fixture embeddings and page-level cosine similarity aggregation |
| `src/seo_rank/textrazor.py` | Offline TextRazor-shaped entity fixtures and normalization |

### CLI

```bash
seo-rank run --seed "technical seo" [options]
```

Options today: `--location`, `--language`, `--device`, `--depth`, `--output-dir`,
`--model-name`, `--javascript-parsing`, `--dry-run`, `--skip-textrazor`.

### Offline run pipeline (no network)

1. Expand seed to a deduplicated keyword list (cap 25) from a DataForSEO fixture.
2. Fetch SERP fixture for the **first** expanded keyword only; normalize organic
   rows up to `--depth` (default 20).
3. Load page-text fixtures for each SERP URL; normalize passages (min 5 words).
4. Compute page-level similarity features from fixture embeddings against the
   first keyword.
5. Unless `--skip-textrazor`, attach TextRazor entity fixtures per page URL and
   normalize entities.
6. Write `run.json` and `report.md` under `--output-dir` (default `artifacts/`).

### Run artifact shape (`run.json`)

Top-level keys written today:

- `config` — serialized `RunConfig`
- `keywords` — normalized keyword list (max 25)
- `serp_results` — organic rows: `keyword`, `rank`, `url`, `title`, `description`
- `passages` — `url`, `passage_id`, `source`, `text`, `word_count`
- `similarity_features` — per URL: `passage_count`, `max_similarity`,
  `mean_similarity`, `best_passage_id`
- `textrazor_entities` — empty when skipped; otherwise normalized entity rows
- `raw_provider_data.dataforseo` — keyword expansion, SERP, page-text fixtures
- `raw_provider_data.textrazor` — present only when TextRazor is not skipped
- `network_calls` — always `[]` in offline mode

`report.md` lists run config, network call count, and SERP titles/URLs.

### Tests

`python -m pytest` collects **10** unit tests under `tests/unit/` covering:

- CLI smoke and TextRazor skip/include paths
- Keyword expansion cap and deduplication
- SERP organic filtering and depth cap
- Passage normalization
- Fixture similarity aggregation
- TextRazor entity normalization
- SDLC doc and product-doc guards

## Known gaps (not shipped)

- Live DataForSEO or TextRazor HTTP clients, request builders, or credential
  validation
- SERP / page text / similarity for **every** keyword in the cluster (today:
  first keyword only)
- Live similarity backends (`BGE-reranker-v2`, Gemini embedding)
- Passage-, page-, and domain-level live similarity procedure
- Domain URL inventory proxy scoring and 1000-URL domain filter
- `statsmodels` OLS analysis, OLS pre-analysis diagnostics, Benjamini-Hochberg
  correction
- Artifact layout under `runs/RUN_ID/` (today: user-supplied `--output-dir`)
- Entity-derived ranking features

See `docs/implementation/dataforseo-textrazor-ranking-similarity-plan.md` for
the phased plan and `ROADMAP.md` for backlog.

## Planned live pipeline

When live integration ships, each run will:

1. Walk **every** keyword in the capped cluster.
2. Collect organic top-20 SERP per keyword; score similarity at passage, page,
   and domain URL scope against that keyword as the target keyword.
3. Run **both** similarity backends every time: cross-encoder `BGE-reranker-v2`
   and bi-encoder Gemini embedding with cosine similarity alone.
4. Complete OLS pre-analysis preparation, fit baseline and similarity-feature
   models with `statsmodels`, apply Benjamini-Hochberg correction, and report.

Full procedure: root `ARCHITECTURE.md` sections *Planned Cosine Similarity Run*,
*Planned Per-Run Statistical Analysis*, and *OLS Pre-Analysis Preparation*.

## External providers

- **DataForSEO** — keyword expansion, organic SERP, parsed page text (canonical
  source; no direct page crawl in v1).
- **TextRazor** — entity extraction from DataForSEO parsed text only (not from
  raw URLs).

## Architecture decisions

Recorded in `docs/architecture/adr/`:

- [0001](adr/0001-keyword-cluster-observational-analysis.md) — keyword-cluster
  observational analysis
- [0002](adr/0002-censored-top20-validation-and-reporting.md) — censored top-20
  validation and reporting
