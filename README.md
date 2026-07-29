# SEO-Research

Python CLI (`seo-rank`) for SEO ranking research across DataForSEO, TextRazor,
BGE, and Gemini signals. Runs write a Parquet lake under `runs/{run_id}/`
(or `--output-dir`). Progress goes to **stderr** (`[seo-rank]` prefix); stdout
stays clean for piping.

## What works today

Offline `seo-rank run` expands a seed from fixtures, scores pages with fixture
**BGE**, **Gemini Doc Retrieval**, and **Gemini Semantic Similarity**, and
writes JSON/Markdown/Parquet with **no network calls**. Opt-in `--live-providers`
gates live DataForSEO (SERP, staged page text, OnPage; backlinks behind
`--live-backlinks`), plus optional live TextRazor / Gemini / BGE. After raw
artifacts, `run` chains normalize → build-features → analyze → Phase 5 stats
unless `--dry-run` (stats skipped via `run_manifest_is_dry_run()`). The same
stats path runs from `materialize_run_tree()`.

## Commands by use case

Copy `.env.example` to `.env` for live work. The CLI and pytest load `.env`
automatically (no `source`). Each command extends the same run tree under
`runs/{run_id}/`.

### Offline / fixtures

**Fresh data** (1 keyword smoke):

```bash
seo-rank run --seed "technical seo" --dry-run
seo-rank run --seed "technical seo" --dry-run --output-dir artifacts
```

**Full offline cluster** (25 fixture keywords):

```bash
seo-rank run --seed "technical seo" --dry-run --keyword-limit 25
seo-rank run --seed "technical seo" --dry-run --keyword-limit 25 --depth 3 --skip-textrazor
```

| Flag | Role |
|------|------|
| `--dry-run` | Fixture/offline run; skips Phase 5 stats |
| `--keyword-limit` | Requested cluster maximum (default `1`); live runs warn and continue if DataForSEO returns fewer unique keywords |
| `--depth` | Max organic SERP rows (default `20`) |
| `--skip-textrazor` | Skip TextRazor entities |
| `--output-dir` | Run root (default `runs/{run_id}`) |

### Resume and expand stored runs

**Resume stored run in place** (reuse raw responses; backfill missing work;
re-materialize downstream):

```bash
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID
```

Use `--stored-run` to resume stored runs in place. It reuses existing raw responses
and completed measurements. Without an explicit `--keyword-limit`, replay uses the
persisted limit. A requested limit is not guaranteed: the single-seed Google Ads
expansion may return fewer unique keywords, in which case the CLI warns and continues.

**Expand existing run** (raise the keyword cap on the same tree):

```bash
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --keyword-limit 25
```

| Flag | Role |
|------|------|
| `--stored-run` | Resume/expand in place |
| `--keyword-limit` | Requested cluster maximum; DataForSEO availability can yield a smaller cluster |
| `--skip-textrazor` | Sticky on replay: suppresses TextRazor even if the saved run had it on |

### Live DataForSEO

Requires `SEO_RANK_ENABLE_LIVE_PROVIDERS=1`, `DATAFORSEO_LOGIN`,
`DATAFORSEO_PASSWORD`.

**Live smoke** (DataForSEO live; fixture similarity):

```bash
seo-rank run --seed "technical seo" --live-providers --output-dir artifacts
```

**Live + Gemini / BGE / TextRazor**:

```bash
# .env: SEO_RANK_ENABLE_GEMINI=1, GEMINI_API_KEY
seo-rank run --seed "technical seo" --live-providers --live-gemini

# .env: SEO_RANK_ENABLE_BGE=1 + CUDA
seo-rank run --seed "technical seo" --live-providers --live-bge

# .env: SEO_RANK_ENABLE_TEXTRAZOR=1, TEXTRAZOR_API_KEY
seo-rank run --seed "technical seo" --live-providers --live-textrazor
```

| Flag | Env gate | Role |
|------|----------|------|
| `--live-providers` | `SEO_RANK_ENABLE_LIVE_PROVIDERS` | Live DataForSEO: expansion, SERP, staged page text, OnPage |
| `--live-backlinks` | same | Also fetch missing backlinks summaries |
| `--live-bge` | `SEO_RANK_ENABLE_BGE` | Live BGE rerank (CUDA) |
| `--live-gemini` | `SEO_RANK_ENABLE_GEMINI` | Live Gemini embeddings |
| `--live-textrazor` | `SEO_RANK_ENABLE_TEXTRAZOR` | Live TextRazor entities |

With `--live-providers` only, backlinks stay off until `--live-backlinks`.
Optional live scorers are skipped unless their flags are passed. Page-text
crawls use a fixed US English desktop contract; rendering escalates baseline →
JS → browser on empty / JavaScript-disabled content (`PAGE_TEXT_RETRIEVAL_PLAN.md`).
`--location` / `--language` still apply to expansion and SERP only.

**Removed flags:** `--javascript-parsing` was dropped; argparse rejects it.

### Stored-run backfills (live overlays)

CLI live flags overlay onto the saved config for this invocation
(`merge_stored_run_cli_overlay`), even when the stored run was created offline.

**Re-fetch non-usable stored page text**

There is **no** `--refresh-page-text` (or similar) CLI flag. Classification
decides what to re-pull: on `--stored-run --live-providers`, every stored
`page_text` row that is not `usable` is fetched again through staged retrieval
(baseline → JavaScript → browser, plus `50402` retry and `switch_pool`). Usable
rows are kept. A later replay retries any row that remains non-usable.

```bash
# Re-pull non-usable page text only (fixture similarity; TextRazor rows for
# refreshed URLs are dropped, not regenerated)
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-providers

# Same re-pull, then regenerate TextRazor for refreshed URLs
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID \
  --live-providers --live-textrazor

# Same re-pull with live similarity for refreshed URLs
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID \
  --live-providers --live-gemini --live-bge

# Full content-derived refresh after page-text replacement
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID \
  --live-providers --live-textrazor --live-gemini --live-bge
```

| Flag | Required? | Role in page-text re-pull |
|------|-----------|---------------------------|
| `--stored-run` | yes | Resume the existing lake in place |
| `--live-providers` | yes | Enables live DataForSEO; triggers non-usable `page_text` re-fetch |
| `--live-textrazor` | no | After a URL's page text is replaced, drop stale `entities` and regenerate with live TextRazor (needs `SEO_RANK_ENABLE_TEXTRAZOR` + `TEXTRAZOR_API_KEY`) |
| `--live-gemini` | no | Recompute Gemini scores for refreshed URLs (needs `SEO_RANK_ENABLE_GEMINI` + `GEMINI_API_KEY`) |
| `--live-bge` | no | Recompute BGE scores for refreshed URLs (needs `SEO_RANK_ENABLE_BGE` + CUDA) |
| `--skip-textrazor` | — | Sticky on replay: keeps TextRazor off even if the saved run had it enabled |

Without `--live-textrazor`, stale TextRazor rows for refreshed URLs are removed
and not regenerated. Without `--live-gemini` / `--live-bge`, similarity for
those URLs is rebuilt with fixture scorers. Billable DataForSEO page-text
requests are issued only for non-usable rows; staged rendering, timeout retry,
and pool switching can add attempts per URL. See `PAGE_TEXT_RETRIEVAL_PLAN.md`.

Stored-run reuse treats known click-tracking query parameters as non-identity
data, so URL variants such as `?utm_source=...` and `?srsltid=...` share cached
provider results while the original URL remains in the report.

**Backfill DataForSEO backlinks on a stored run** (also fetches missing
`endpoint=onpage_instant_pages` rows):

```bash
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-providers --live-backlinks
```

Only missing URL/variant rows are requested; usable stored rows are reused.
Backlinks: up to two `backlinks/summary/live` calls per URL (unfiltered +
dofollow). OnPage: one `on_page/instant_pages/live` call per missing URL. Raw partitions:
`backlinks_summary`, `backlinks_dofollow_summary`, `onpage_instant_pages`.

**Backfill live TextRazor on a stored run** (no DataForSEO HTTP):

```bash
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-textrazor-only
seo-rank run --seed "technical seo" --stored-run runs/RUN_ID --live-textrazor-only --refresh-textrazor
```

Requires `SEO_RANK_ENABLE_TEXTRAZOR=1` and `TEXTRAZOR_API_KEY`. Mutually
exclusive with `--live-providers` and `--skip-textrazor`. Pass
`--refresh-textrazor` to replace existing `endpoint=entities` rows for the same
`(target_keyword, url)`; without it, already-materialized entity rows are
skipped.

**Brand-new run with live TextRazor only** (fixture DataForSEO structure + live
entities; no `dataforseo.*` in `network_calls`):

```bash
seo-rank run --seed "technical seo" --live-textrazor-only --output-dir runs/demo
```

TextRazor rows land in `raw_responses/endpoint=entities` with
`provider=textrazor` under the shared `RAW_RESPONSE_SCHEMA`. Normalize writes
`parquet/entities/` and `parquet/textrazor_page_metrics_curated/`; the feature
mart `parquet/textrazor_page_metrics/` feeds Phase 5 TextRazor families.

### Lake pipeline (existing run tree)

`seo-rank run` already chains these after raw artifacts. Use them on an
existing tree when you need a single layer:

```bash
seo-rank normalize --run runs/RUN_ID
seo-rank build-features --run runs/RUN_ID
seo-rank analyze --run runs/RUN_ID
```

| Goal | Command |
|------|---------|
| Curated Parquet tables | `seo-rank normalize --run runs/RUN_ID` |
| Feature marts | `seo-rank build-features --run runs/RUN_ID` |
| Analysis mart + Phase 5 stats | `seo-rank analyze --run runs/RUN_ID` |
| Re-run stats only | `seo-rank analyze --run runs/RUN_ID` (exit `1` on guardrail hard-fail) |
| Inspect one keyword | `seo-rank analyze --run runs/RUN_ID --keyword "technical seo"` |
| Combine stored runs | `seo-rank analyze --run runs/A --run runs/B --output-dir runs/combined` |

`analyze` backfills missing feature marts (including `backlinks_analysis` and
`onpage_features` when upstream data allows). Exit codes: `0` success; `1`
guardrail hard-fail on non–dry-run; `2` missing data / unknown `--keyword`.
Multi-`--run` combine requires `--output-dir`.

Typical offline research path:

```bash
seo-rank run --seed "technical seo" --dry-run --keyword-limit 25
seo-rank normalize --run runs/RUN_ID
seo-rank build-features --run runs/RUN_ID
seo-rank analyze --run runs/RUN_ID
```

### Audit and tests

```bash
seo-rank replay --run runs/RUN_ID --response-id RESPONSE_ID
python -m pytest
python -m pytest tests/integration -m integration   # opt-in; needs SEO_RANK_RUN_LIVE_INTEGRATION=1
```

Storage commands exit `2` on missing run data or unknown ids (stderr only).

---

## What `seo-rank run` executes

Per expanded cluster keyword:

1. SERP normalization (top *N* organic rows, default 20)
2. Backlinks (`--live-providers --live-backlinks`): two calls per SERP URL →
   `endpoint=backlinks_summary` / `backlinks_dofollow_summary`
3. OnPage (live providers on): one call per SERP URL →
   `endpoint=onpage_instant_pages` → curated `onpage_signals` →
   `onpage_features` (`onpage_content_quality`, `onpage_core_web_vitals`,
   `onpage_technical_checks`)
4. Page text (fixtures or staged `content_parsing/live`: baseline → JS →
   browser; `50402` retry; `switch_pool` on pool failures)
5. Passage splitting
6. Passage-level similarity features
7. Page-level similarity scores (three backends)
8. TextRazor page metrics (fixture unless `--live-textrazor` / textrazor-only)
9. Artifacts: `run.json`, `report.md`, Parquet lake, Phase 5 stats (not on
   `--dry-run`)

After materialization, TextRazor confidence/relevance from
`textrazor_page_metrics` sync into `run.json` `page_similarity` and
`report.md`.

## Ranking signal backends

All three backends always appear in JSON/Markdown. Default runs use fixture
scorers in `similarity.py` (pipeline shape / tests, not production retrieval).

| Backend | JSON key | Default | Live override |
|---------|----------|---------|---------------|
| BGE cross-encoder | `bge` | Fixture | `--live-providers --live-bge` |
| Gemini Doc Retrieval | `gemini_doc_retrieval` | Fixture | `--live-providers --live-gemini` |
| Gemini Semantic Similarity | `gemini_semantic_similarity` | Fixture | same `--live-gemini` |

Live BGE merges real scores over base rows; it does not replace Gemini columns.
Retrieve-then-rerank is not implemented (`ROADMAP.md`).

## `seo-rank analyze` and Phase 5 stats

`analyze` writes `parquet/analysis_mart/` (SERP rank, three similarity scores,
page text length). TextRazor metrics stay in separate marts
(`textrazor_page_metrics_curated`, `textrazor_page_metrics`) with
`textrazor_page_metrics_complete`. It does not re-fetch pages or re-embed.

Stats (guardrails, Spearman, pooled OLS, page-level Plackett-Luce summaries) run
at four confirmatory rank depths (`top_20`, `top_10`, `top_5`, `top_3`) for every
registered signal family into `runs/{run_id}/stats/`, including nested
`rank_depths` / `rank_depths.*.families` in `stats_summary.json` and
`stats_diagnostics.json`, four `## Rank depth:` report sections, and
`actionable_association_by_rank_depth`.

**Robustness appendix (primary depth `top_20` only):**

- **### Robustness** (slice 7): multivariate VIF sensitivity; drop order Gemini
  Semantic Similarity → Gemini Doc Retrieval → keep BGE.
- **### Influence robustness** (slice 8): Cook's D refit; `influential_rows_rate`
  warn guardrail.

Each depth reports `keyword_count` and `inference_mode` (`confirmatory` /
`exploratory` / `underpowered`). Golden contracts:
`tests/unit/test_stats_golden_fixtures.py`.

## Flag reference (`seo-rank run`)

| Flag | Default | Purpose |
|------|---------|---------|
| `--seed` | *(required)* | Seed keyword |
| `--location` | `United States` | Expansion/SERP location |
| `--language` | `en` | Expansion/SERP language |
| `--device` | `desktop` | `desktop` or `mobile` |
| `--depth` | `20` | Max organic SERP rows |
| `--keyword-limit` | `1` | Requested cluster maximum; live/replay runs warn when fewer unique keywords are available |
| `--output-dir` | `runs/{run_id}` | Run root |
| `--model-name` | `fixture-similarity-v1` | Recorded in `run.json` |
| `--dry-run` | off | Fixture/offline; skip Phase 5 stats |
| `--debug` | `0` | With `1`, write full intermediate payloads including raw provider data to `debug.json` |
| `--skip-textrazor` | off | Skip TextRazor; sticky on stored-run replay |
| `--stored-run` | — | Resume/expand; with `--live-providers`, re-fetch non-usable `page_text` |
| `--live-providers` | off | Live DataForSEO + staged page text; on stored-run, also re-pulls non-usable `page_text` |
| `--live-backlinks` | off | Live backlinks (needs `--live-providers`) |
| `--live-backlinks-detail` | off | Also fetch backlinks detail (needs `--live-backlinks`) |
| `--live-bge` | off | Live BGE; on page-text re-pull, recomputes BGE for refreshed URLs |
| `--live-gemini` | off | Live Gemini; on page-text re-pull, recomputes Gemini for refreshed URLs |
| `--live-textrazor` | off | Live TextRazor; on page-text re-pull, regenerates entities for refreshed URLs |
| `--live-textrazor-only` | off | Live TextRazor without DataForSEO HTTP |
| `--refresh-textrazor` | off | Replace existing `entities` rows when backfilling TextRazor |
| `--domain-blocklist` | `domain_blocklist.txt` | Domains skipped for page text / backlinks / OnPage |

## Storage layout

```text
runs/{run_id}/
  run.json
  report.md
  parquet/
    raw_responses/endpoint={keyword_expansion|serp|page_text|entities|backlinks_summary|backlinks_dofollow_summary|onpage_instant_pages}/part-*.parquet
    keywords/  serp_items/  pages/  passages/  entities/
    backlinks/  onpage_signals/  textrazor_page_metrics_curated/  similarity_scores/
    keyword_serp/  page_features/  passage_features/  domain_features/
    backlinks_analysis/  onpage_features/  textrazor_page_metrics/  analysis_mart/
  stats/
    stats_summary.json
    stats_diagnostics.json
    stats_report.md
```

Transforms use Polars LazyFrames until a boundary `collect(engine="streaming")`
or `sink_parquet(..., compression="zstd")`. `raw_responses` is not joined in
normal analysis; use `replay` to re-parse one body.

## Standalone scripts

`analysis/gemini_nwh_similarity.py` — one-off block-scoring experiment (not
part of default `run`).

`analysis/textrazor_ranking_r2.py` — adjusted R² explainability on a completed
run (`parquet/analysis_mart` + `parquet/textrazor_page_metrics`):

```bash
python analysis/textrazor_ranking_r2.py --run runs/RUN_ID
python analysis/textrazor_ranking_r2.py --run runs/RUN_ID --depth top_10
python analysis/textrazor_ranking_r2.py --run runs/RUN_ID --no-show
python analysis/textrazor_ranking_r2.py --run runs/RUN_ID --individual-signals
```

The default runs high-precision grouped importance with 5 folds, 10 keyword-CV
repeats, 500 bootstraps, 2,000 Shapley permutations, and 10 domain-CV repeats.
`--individual-signals` applies the same measurements to each signal. Long-running
stage progress is logged to stderr; explicit resampling arguments override defaults.

Writes `stats/ranking_r2.json`, `stats/ranking_r2_curated_model.png`, and
`stats/ranking_r2_entity_relevance.png`.

## Repository layout

| Path | Purpose |
|------|---------|
| `src/seo_rank/` | CLI, providers, `progress.py` |
| `src/seo_rank/data/` | Polars lake: `scans`, `normalize`, `ranks`, `features`, `marts`, `validate` |
| `src/seo_rank/stats/` | Phase 5 analysis package |
| `tests/unit/` | Unit tests |
| `ARCHITECTURE.md` | Architecture and data flow |
| `GOALS.md` | Active-scope contract |
| `FIXUPS.md` | Small-fixes backlog |
| `ROADMAP.md` | Backlog and history |
| `PAGE_TEXT_RETRIEVAL_PLAN.md` | Staged page-text retrieval (shipped) |
| `TESTING.md` | Verification contract |
| `analysis/` | Standalone scripts above |

## Documentation

- Architecture: `ARCHITECTURE.md`
- Active scope: `GOALS.md`
- Backlog: `ROADMAP.md`
- Testing: `TESTING.md`
- Process: `AGENTS.md`, `SDLC.md`

Verification: `python -m pytest` (live integration opt-in — see `TESTING.md`).

## License

yt-mod is dual-licensed:

- **Open source:** [GNU AGPLv3](LICENSE) — free to use, modify, and
  self-host, including commercially, as long as you comply with AGPLv3
  (which includes releasing the source of any modified version you
  offer as a network service).
- **Commercial license:** if you want to use yt-mod in a proprietary
  product or offer it as a hosted service without AGPL obligations,
  contact <your-email> for a commercial license.
