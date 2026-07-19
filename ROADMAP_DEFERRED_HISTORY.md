<!-- Part of the split roadmap. Index: ROADMAP.md -->

## Deferred

- Entity-derived features beyond Phase 5.6 density bundle (keyword–entity overlap,
  type-weighted density, passage-level density)
- CI, release packaging, coverage thresholds
- Production deployment, databases, cache
- Parquet `Variant` type for provider payloads
- Content Analysis API (citation-index brand mentions) — marginal value over
  TextRazor, doesn't fit a per-URL/per-domain grain cleanly (considered and
  cut from Phase 7/8 scope)
- Majestic, Ahrefs, Moz, Similarweb, Google Search Console, Google Natural
  Language API — paid/account-gated third-party signals (considered and cut
  from Phase 8 scope in favor of free-tier sources). GSC resurfaces in
  Phases 12–13 as the optional behavioral (`w_beh`) feed for your own pages.

## History

- **Page-text staged retrieval shipped (2026-07):** `PAGE_TEXT_RETRIEVAL_PLAN.md`
  slices 1–4 — `classify_page_text_response()`, staged
  `fetch_page_text_for_urls()` (baseline → JavaScript → browser), `50402`
  timeout retry + `switch_pool` recovery, and automatic non-usable
  `page_text` re-fetch on `run --stored-run --live-providers` with similarity /
  TextRazor invalidation for refreshed URLs. No new CLI flag.
- Repository scaffold: `pyproject.toml`, `src/seo_rank/`, `tests/`.
- **Phase 1 shipped:** offline CLI, DataForSEO/TextRazor fixtures, keyword/SERP/
  passage/similarity/entity normalization, `run.json` + `report.md`, unit tests,
  root product docs (`ARCHITECTURE.md`, `GOALS.md`, `ROADMAP.md`).
- SDLC wizard surface: hooks, manifest, `GOALS.md` active contract.
- **Phase 2 shipped:** provider request builders (DataForSEO keyword expansion,
  organic SERP, page-text parsing; TextRazor parsed-text entities), credential
  validation without secrets in errors, non-default CLI live-provider gate
  (`--live-providers` + `SEO_RANK_ENABLE_LIVE_PROVIDERS=1`), standard-library
  HTTP clients with injectable transports, env-gated live smoke integration test
  (`SEO_RANK_RUN_LIVE_INTEGRATION=1`), and Phase 2 documentation/test coverage.
- **Phase 2 deferred to later backlog:** broader live provider integration beyond
  the minimal smoke path.
- **GOALS retargeted to Phase 3:** full cluster orchestration for every capped
  keyword in offline and live paths.
- **Phase 3 shipped:** per-keyword cluster orchestration in offline and gated
  live paths.
  - `build_offline_keyword_result` / `build_live_keyword_result` loop every capped
    keyword (up to the configured keyword limit, default 1) with that keyword as
    `target_keyword`.
  - Per-keyword SERP, page text, passages, fixture similarity, TextRazor entities.
  - `keyword_results[]` in `run.json` / `report.md` with per-keyword raw provider
    payloads; top-level rollup preserved.
  - Flattened aggregate rows annotated with `target_keyword`.
  - `.env.example` documents live-provider and integration env gates.
  - Tests: 1-keyword default offline cluster + injected live cluster orchestration
    in `test_cli_run.py`.
- **GOALS retargeted to Phase 4:** live similarity backends and passage/page/domain
  scoring.
- **Phase 4 started:** fixture page-level scoring for **BGE**, **Gemini Doc
  Retrieval**, and **Gemini Semantic Similarity** wired through offline and
  gated live artifact generation, including JSON/Markdown exposure and unit
  coverage.
- **Env loading:** CLI and pytest auto-load project-root `.env` via
  `seo_rank.env` (`.env` overrides shell exports; no `source` required). Integration
  gate now requires `SEO_RANK_RUN_LIVE_INTEGRATION=1` explicitly (fixes `"0"` being
  treated as enabled).
- **Phase 4 shipped:** live page-level similarity backends behind opt-in CLI flags.
  - Fixture scorers in `similarity.py` for offline, `--dry-run`, and default live runs.
  - `gemini_embeddings.py` + `--live-gemini` for **Gemini Doc Retrieval** and
    **Gemini Semantic Similarity** via `gemini-embedding-2` / `google-genai`.
  - `bge_reranker.py` + `--live-bge` for local **BGE** via `FlagEmbedding`
    (`BAAI/bge-reranker-v2-m3`, CUDA, once per live run).
  - Optional `similarity` extra in `pyproject.toml`; env gates in `.env.example`.
  - Unit tests for prompt formatting, CLI path selection, and BGE batching; env-gated
    integration smoke with optional Gemini/BGE flags.
- **GOALS retargeted to Phase 4.5:** run-scoped Parquet lake storage.
- **Phase 4.5 scoped:** run-scoped Parquet architecture (`raw_responses`, curated
  tables, feature marts, `analysis_mart`), Polars LazyFrame data package
  (`src/seo_rank/data/`), CLI `normalize` / `build-features` / `analyze` /
  `replay`, and validation-before-sink contract.
- **Phase 4.5 Slice 1 shipped:** `seo-rank run` writes run-scoped `raw_responses`
  Parquet partitions plus `run.json` catalog metadata without duplicating raw
  payloads in JSON.
- **Phase 4.5 Slice 2 shipped:** stored `raw_responses` normalize into curated
  Parquet tables (`keywords`, `serp_items`, `pages`, `passages`, `entities`,
  `similarity_scores`) and refresh the run catalog from disk.
- **Phase 4.5 Slice 3 shipped:** `normalize_run()` scans `raw_responses`, filters
  by `endpoint`, and normalizes via lazy `map_batches` / `map_groups` UDFs with
  per-table streaming collect at sink. Package: `scans`, `normalize`, `features`,
  `marts`, `validate` under `src/seo_rank/data/`.
- **Phase 4.5 Slice 4 shipped:** feature marts (`keyword_serp`, `page_features`,
  `passage_features`, `domain_features`) materialized from curated tables via lazy
  Polars joins.
- **Phase 4.5 Slice 5 shipped:** `analysis_mart` materializes as a lazy panel
  joined from feature marts (one row per `target_keyword × SERP URL`);
  `raw_responses` excluded from analytical joins.
- **Phase 4.5 Slice 6 shipped:** CLI surfaces `normalize`, `build-features`,
  `analyze`, and `replay`; `run --stored-run` resumes partial runs in place from
  the saved raw lake and existing keyword results, then re-materializes marts
  from a stored run tree.
- **Phase 4.5 Slice 7 shipped:** `pyarrow` + `polars` declared; docs aligned;
  round-trip regression in `test_round_trip.py` and `test_sdlc_docs.py`.
- **Phase 4.5 Slice 8 shipped:** curated tables sink via Polars
  `sink_parquet(..., compression="zstd", statistics=True)` with sorted retrieval
  keys (replaces PyArrow `write_table` on curated path).
- **Phase 4.5 Slice 9 shipped:** feature marts and `analysis_mart` use lazy
  `sink_parquet` with statistics; catalog row counts from Parquet file metadata.
- **Phase 4.5 Slice 10 shipped:** `validate_frame_contract` stays schema-only and
  lazy; row-level uniqueness, null, and range checks at the sink edge only.
- **Phase 4.5 signed off (2026-06-29):** 10 dev slices shipped; 11 acceptance
  items complete. Run-scoped lake under `runs/{run_id}/` with authoritative
  `raw_responses`, six curated tables, four feature marts, `analysis_mart`, lazy
  Polars transforms, validation-before-sink, and storage CLI commands. Residual:
  batch Python UDFs for JSON parse and similarity grouping; post-sign-off polish
  tracked in `FIXUPS.md` § Phase 4.5.
- **Phase 4.77 shipped:** adapter schema validation at the DataForSEO boundary
  with endpoint-scoped parse errors and drift coverage for missing fields,
  type mismatches, and valid pass-through fixtures.
- **GOALS retargeted to Phase 5 (2026-07-01):** statistical analysis on
  `analysis_mart` — Spearman-first observational association, pooled OLS with
  keyword-clustered SEs, guardrails, BH policy, `analysis_spec.v1.yaml`, and
  `stats_*` artifacts wired through `seo-rank analyze`.
- **Phase 5 Slice 1 shipped:** `analysis_spec.v1.yaml` locks the v1 estimand
  (Spearman-first, pooled OLS secondary, BGE primary backend, BH per backend
  when K ≥ 10, guardrail thresholds, actionable-association rule, multivariate
  drop order, limitations); cross-linked in `ARCHITECTURE.md`,
  `PHASE5-STATS-PLAN-REVIEW.md`, and `ROADMAP.md`.
- **Phase 5 Slice 2 shipped:** `src/seo_rank/stats/` package scaffold with
  `spec.py` (`load_analysis_spec`), `artifacts.py` (`build_stats_output_metadata`),
  and placeholder modules for panel, Spearman, regression, BH, and diagnostics;
  `statsmodels`, `numpy`, `scipy`, and `PyYAML` declared in `pyproject.toml`;
  `tests/unit/test_stats_spec.py` covers spec load and estimand-version metadata.
- **Phase 5 Slice 5 shipped:** `regression.py` now fits pooled baseline and
  univariate backend models on `-log(serp_rank)` with keyword fixed effects,
  keyword-clustered SEs, effect-size translation, and a two-way-cluster
  sensitivity on repeated URLs; `run_phase5_stats()` writes regression summaries
  into `stats_summary.json` and `stats_report.md`, covered by
  `tests/unit/test_stats_regression.py`.
- **Phase 5 Slice 6 shipped:** `diagnostics.py` summarizes pooled OLS RESET,
  Breusch–Pagan (with HC3 recommendation when flagged), Cook's D, leverage,
  studentized residuals, DFFITS, and DFBETAs per backend; `run_phase5_stats()`
  writes `stats_diagnostics.json` and a Diagnostics section in `stats_report.md`
  on passing guardrails, covered by `tests/unit/test_stats_diagnostics.py`.
  `normalize` now materializes `similarity_scores` from `run.json`
  `page_similarity` instead of recomputing scores during curation.
- **Phase 5 Slice 7 shipped:** `diagnostics.py` fits the joint three-backend
  multivariate sensitivity model with spec-driven VIF threshold and backend drop
  order; `run_phase5_stats()` writes `rank_depths.top_20.multivariate_sensitivity`
  to `stats_diagnostics.json` and a `### Robustness` section in
  `stats_report.md`; `spec.py` exposes `multivariate_vif_threshold` and
  `backend_drop_order`; covered by `tests/unit/test_stats_diagnostics.py` and
  `tests/unit/test_stats_spec.py`.
- **Phase 5 Slices 16–20 shipped (2026-07-02):** parallel confirmatory rank-depth
  bundles at `top_20`, `top_10`, `top_5`, and `top_3` — `rank_depths` and
  `limitations_by_depth` in `analysis_spec.v1.yaml`, `rank_depth.py` panel
  filtering, per-depth Spearman/OLS/Plackett-Luce/diagnostics, nested
  `rank_depths` in `stats_summary.json` / `stats_diagnostics.json`, four
  `## Rank depth:` sections in `stats_report.md`,
  `actionable_association_by_rank_depth`, leave-one-out IIA on `top_20` only;
  covered by `tests/unit/test_stats_rank_depth.py`.
- **Phase 5 Slices 27–28 shipped (2026-07-02):** TextRazor signal-family registry
  in `analysis_spec.v1.yaml` and `families.py`; curated
  `textrazor_page_metrics_curated` plus feature mart `textrazor_page_metrics`
  at `target_keyword × SERP URL` grain; full page-metrics TextRazor extractors;
  similarity `analysis_mart` unchanged. Covered by `test_stats_families.py`,
  `test_textrazor_normalization.py`, and `test_feature_marts.py`.
- **Phase 5 Slices 29–30 shipped (2026-07-02):** family-aware Spearman, pooled
  OLS, diagnostics, and Plackett-Luce per registered signal family; combined
  `stats_*` artifact tree with nested `rank_depths.*.families` for similarity
  and TextRazor families; top-level similarity blocks kept for compatibility.
  Covered by `test_stats_family_dispatch.py` and `test_stats_family_artifacts.py`.
- **Phase 5 Slices 32–33 shipped (2026-07-02):** TextRazor page-metrics
  completeness (`textrazor_page_metrics_complete`, null-not-zero section
  counts) and small-K inference labeling (`keyword_count`, `inference_mode` in
  `stats_*`). Covered by `test_textrazor_normalization.py`,
  `test_feature_marts.py`, and `test_stats_family_artifacts.py`.
- **Phase 5 Slices 21–26 shipped (2026-07-02):** TextRazor-only ingestion path —
  `--live-textrazor-only` / `--refresh-textrazor` CLI flags and gates,
  `TEXTRAZOR_ENDPOINTS` registry, `fetch_textrazor_entities_for_pages()`,
  `merge_raw_response_records()` for `endpoint=entities`, stored-run backfill
  via `backfill_textrazor_run()`, and brand-new runs via
  `write_textrazor_only_artifacts()` (fixture DataForSEO structure + live
  TextRazor, zero `dataforseo.*` in `network_calls`). Cross-doc schema contract
  (slice 26) is shipped.
- **Phase 5.1 updated (2026-07-16):** DataForSEO top-level and task-level
  failures now log warnings, retain raw responses, and let live runs continue;
  failed SERP tasks produce empty SERP rows for the affected keyword. Fatal-task
  classification and preflight remain deferred hardening.
- **Phase 5 Slices 8–10 shipped (2026-07-03):** influence refit appendix
  (`influence_sensitivity` block, `### Influence robustness` report sections,
  `influential_rows_rate` warn guardrail), similarity golden fixtures
  (`test_stats_golden_fixtures.py` schema/boundary contracts), and expanded
  ranking explainability (`textrazor_ranking_r2.py` similarity + TextRazor
  adjusted R², `ranking_r2.json`, curated-model PNG via
  `ranking_explainability_viz.py`, optional `matplotlib` dependency).
- **Backlinks two-call summary API (2026-07-04, Phase 5.91):** live runs issue
  two `POST /v3/backlinks/summary/live` calls per SERP URL (unfiltered summary
  plus dofollow-filtered summary, ~$0.04/target combined). Each variant
  persists immediately to `raw_responses/endpoint=backlinks_summary` or
  `endpoint=backlinks_dofollow_summary` via `persist_backlink_raw_responses()`
  (dedupe on `(target_keyword, url, variant)`). Normalization merges both into
  one curated row per `target_keyword × URL`; `dofollow_backlinks_count` is
  `null` and `backlinks_metrics_complete` is `false` when the dofollow variant
  is missing. Legacy `endpoint=backlinks` rows (pre-5.91 `/backlinks/backlinks/live`
  shape) remain read-compatible on normalize. Stored-run replay overlays
  `--live-providers` onto offline runs; `--skip-textrazor` stays sticky via
  `merge_stored_run_cli_overlay()`. Supersedes the 2026-07-03 single-partition
  summary migration.
- **Phase 6.2 shipped (2026-07-05):** `backlinks_analysis` feature mart
  (`analysis_mart` grain + curated `backlinks` counts), `backlinks_counts`
  signal family (`backlinks_metric` kind) in `analysis_spec.v1.yaml`, and
  family-aware stats/report blocks for `backlinks_count`,
  `referring_domains_count`, and `dofollow_backlinks_count`. `analysis_mart.v1`
  unchanged; `ensure_feature_marts_for_analysis` requires `backlinks_analysis`
  and `onpage_features`; `run_phase5_stats` invokes the same guard before loading
  family source frames.
- **Phase 7.1 slice 13 shipped (2026-07-07):** OnPage `htags` counts
  (`h1_count`/`h2_count`/`h3_count` from `meta.htags` array lengths via the
  Slice 12 `_optional_mapping_len` helper) and `social_media_tags` presence
  flags (`has_og_tags`/`has_twitter_tags` via new `_has_prefix_key` helper).
  5 new columns on `onpage_signals`; `onpage_features` bounded columns added
  for the three count fields. Fixture updated with representative
  `htags` + `social_media_tags`. Tests in `tests/unit/test_run_normalize.py`.
  Stats family wiring remains Slice 17.
- **Phase 7.1 slice 14 shipped (2026-07-07):** Within-keyword rank, percentile,
  and z-score columns added to `analysis_mart` (schema `v2`) for all three
  similarity backends (`bge`, `gemini_doc_retrieval`, `gemini_semantic_similarity`).
  `emit_keyword_analysis` JSON output includes rank/pct/z; `report.md` Page
  Similarity sorted by BGE rank with `[rank X/N, pct 0.00]` annotation.
  Tests in `test_data_marts.py`, `test_analysis_mart.py`, `test_cli_keyword_analysis.py`.
- **Phase 7.1 slices 1–14 shipped (2026-07-06):** OnPage `instant_pages` live
  path from request/fixture through raw `endpoint=onpage_instant_pages`,
  curated `onpage_signals` (46 `checks` booleans via Slice 11; 18 `meta` metrics
  via Slice 12),
  feature mart `onpage_features`, and three
  `onpage_metric` signal families (`onpage_content_quality`,
  `onpage_core_web_vitals`, `onpage_technical_checks`) with Spearman, pooled OLS,
  diagnostics, and family Plackett-Luce at all confirmatory rank depths.
  `ensure_feature_marts_for_analysis()` lives in `data/features.py` and rebuilds
  missing `onpage_features` on legacy run trees (when `run.json` exists) from
  both `seo-rank analyze` and `run_phase5_stats()`. Slice 18 stored-run
  end-to-end regression and full-layer CLI pipeline tests shipped (Jul 2026).
- **Phase 6.1 Slice 3 partial (2026-07-03):** `src/seo_rank/data/ranks.py`
  ships Polars-lazy `add_within_keyword_similarity_ranks()` with unit tests in
  `tests/unit/test_within_keyword_ranks.py`; mart wiring remains Slice 4.
- **Phase 5.6 planned (2026-07-03):** signal factor & proxy diagnostics —
  NDCG@k, incremental TextRazor-after-BGE regression ladder, partial
  correlation, leave-one-keyword-out stability, keyword holdout and optional
  time-split validation, negative controls, same-length / same-similarity subset
  analyses, and unified `signal_factor_report` artifact. Tracked as Phase 5
  slice 34; precursor `textrazor_ranking_r2.py` ships similarity + TextRazor
  adjusted R², curated multivariate model, and PNG charts.
- **Phase 5.6 entity density planned (2026-07-03):** Slice 0 materializes
  entity mention/unique counts and word-normalized densities in
  `textrazor_page_metrics`; dossier registry adds char-normalized density and
  proxy-test expectations for counts vs densities (six slices total in § 5.6).
- **Phase 5.2 planned (2026-07-02):** live Gemini/BGE fail-fast on empty scoring
  work — abort when a keyword yields zero `parsed_pages` or zero
  `page_similarity` with live scoring on; skip Gemini query embeds on empty
  pages; defer BGE GPU load; accurate `network_calls`; AI Studio billing clarity
  (not GCP console). Complements 5.1; depends on 5.1 slice 4 for stored-run
  CLI live-flag override.
- **GOALS retargeted to Phase 4.75 (2026-06-29):** page_text curation hardening
  after stored-run normalize failed on live nested `page_content` payloads.
- **Phase 4.75 Slice 1 shipped:** `parsed_page_text()` decodes nested DataForSEO
  `content_parsing` items; `build_pages_and_passages_frame()` uses the shared
  parser instead of flat `tasks[0].result[0]` indexing.
- **Phase 4.75 Slice 2 shipped:** `_extract_page_content_text()` now walks all
  relevant `page_content` regions, so `header` and other nested sections are
  included in normalized page `text` and passage splitting.
- **Phase 4.75 Slice 3 shipped:** `build_pages_and_passages_frame()` skips
  `page_text` responses with no URL or no text, automatically dropping empty
  bodies without any CLI flag and preventing blank curated rows or duplicate
  `page_id` warnings from crawl failures.
- **GOALS retargeted to Phase 4.76 (2026-07-01):** structured
  `content_parsing/live` capture — per-field curated storage, aggregate
  `pages.text`, raw HTML, and a fixed US English desktop request contract.
- **Phase 4.76 Slice 1 shipped:** `build_page_text_request()` always emits the
  fixed US English desktop contract (`ip_pool_for_scan=us`,
  `accept_language=en-US`, baseline JS/rendering off, `store_raw_html=true`); the
  `--javascript-parsing` CLI knob was removed. Later staged retrieval (2026-07)
  escalates rendering on empty / JavaScript-disabled outcomes without changing
  that baseline contract or restoring a CLI toggle.
- **Phase 4.76 Slice 3 shipped:** curated `page_content_fields` now materialize
  one row per decoded `content_parsing/live` field with stable ids and JSON
  path metadata while leaving aggregate `pages.text` unchanged.
- **Phase 4.76 Slice 4 shipped:** normalization now preserves the aggregate
  `pages.text` path and writes raw HTML to a sibling `page_html` table keyed by
  `page_id` / `response_id`.
- **Phase 4.76 Slice 5 shipped:** unit tests and stored-run re-normalize smoke
  now cover multi-field content parsing fixtures, HTML retention, aggregate text
  parity, and structured-only round-trip payloads.
- **Roadmap split + vision phases planned (2026-07-19):** `ROADMAP.md` split
  into per-phase files (index remains in `ROADMAP.md`); Phases 10–13 added —
  embedding store (keystone), site/topic layer (robust centroids, radius,
  focus as signal families), passage MaxSim, temporal panel (lead-lag + DiD),
  and the predictive/universe layer (out-of-time NDCG bake-off, ablation,
  simulation). Original sections preserved verbatim from `main`.
- **Phase 11.75 planned (2026-07-20):** vector-space visualization — kNN
  similarity graph with cosine-weighted edges over the Phase 10 embeddings
  mart, deterministic UMAP projection (t-SNE comparison render), static
  per-run PNG/SVG linked from `report.md`, optional self-contained
  interactive HTML explorer, and a cross-snapshot coordinate-alignment hook
  for Phase 12. Guardrailed as display-only: all metrics stay computed in
  full dimensionality; projection coordinates never become features.
