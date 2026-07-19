<!-- Part of the split roadmap. Index: ROADMAP.md -->

### Phase 5.6 — Signal factor & proxy diagnostics

Observational methods to distinguish **candidate ranking signals** from
**likely proxies** (signals that co-move with rank because they track length,
semantic relevance, template type, or other confounders). Complements Phase 5
Spearman / pooled OLS / Plackett-Luce confirmatory paths; does **not** replace
them and does **not** support causal claims about Google's ranking function.

**Tracked in Phase 5 slice 34** (umbrella only). **Precursor (partial):**
`analysis/textrazor_ranking_r2.py`, `src/seo_rank/stats/textrazor_explainability.py`,
and `ranking_explainability_viz.py` (similarity + TextRazor univariate and joint
adjusted R², curated multivariate model, PNG charts).

**Panel:** same grain as Phase 5 (`target_keyword_id × canonical_url_hash`,
top-N SERP rows); TextRazor metrics from `textrazor_page_metrics` left-joined
onto `analysis_mart`. **Primary backend for proxy ladder:** `bge_normalized_score`
(pre-registered in `analysis_spec.v1.yaml`).

#### Methods planned

| Method | Purpose | Notes |
| ------ | ------- | ----- |
| **NDCG@k** | Sort-by-metric vs Google order | Per keyword: treat signal as relevance (higher = better), compute NDCG@k vs `serp_rank`; macro mean/median across keywords. Default k = 10; configurable. |
| **Incremental regression after BGE** | Explicit proxy test | Pooled OLS ladder with keyword FE plus the three adjustment controls: baseline → `+ bge_normalized_score` → `+ candidate signal(s)`. Report coefficient, p-value, Δ adjusted R² at each step; shrinkage after BGE ⇒ likely proxy. |
| **Partial correlation** | Association net of similarity | Within-keyword or pooled partial ρ / partial regression of signal vs rank controlling for `bge_normalized_score`, referring domains, deprecated HTML tags, and meta-keyword consistency. |
| **Leave-one-keyword-out (LOKO)** | Stability | Recompute headline metrics (Spearman median, NDCG macro mean, incremental Δ R²) dropping one keyword at a time; flag dominant-keyword dependence. |
| **Out-of-sample validation** | Generalization beyond fit sample | (a) **Keyword holdout:** seeded split by `target_keyword_id` (default 20% held out). (b) **Time-split:** compare metrics across two `run_id`s on overlapping keywords (exploratory). Label `exploratory` when K_train or K_test < 10. |
| **Negative controls** | Falsification | Deliberately null or shuffled predictors (e.g. permuted signal within keyword) should show ρ ≈ 0, Δ R² ≈ 0; candidate must beat controls. |
| **Same-length / same-similarity subsets** | Discriminating comparisons | Restrict to URLs with similar `page_text_length` (binned) or similar `bge_normalized_score` (binned); re-test association within slices. |
| **Factor vs proxy report** | Single dossier artifact | `analysis/signal_factor_report.py` → terminal summary + `runs/{run_id}/stats/signal_factor_report.json` with limitations block. |

**Core module:** `src/seo_rank/stats/signal_dossier.py` (computations) +
`analysis/signal_factor_report.py` (CLI). **v1 dossier candidate registry:**
scalar/structural TextRazor metrics plus an **entity density bundle** (see
below). Registry is exploratory-only in 5.6 — not added to confirmatory
`analysis_spec.v1.yaml` `signal_families` unless promoted after dossier
evidence.

**Scalar / structural candidates (existing):** `textrazor_entity_confidence_score`,
`textrazor_entity_relevance_score`, `textrazor_entailment_score`,
`textrazor_relation_count`, `textrazor_property_count`.

**Entity density bundle (new):** counts and length-normalized rates derived from
TextRazor `entities` and joined `page_text_length` from `analysis_mart`.
Canonical dedupe key matches `analysis/gemini_nwh_similarity.py`:
`entityEnglishId` → `entityId` → `matchedText`.

| Column | Definition | Persisted in `textrazor_page_metrics` | Null when |
| ------ | ---------- | ------------------------------------- | --------- |
| `textrazor_entity_mention_count` | `len(entities)` | yes | `entities` section absent |
| `textrazor_unique_entity_count` | deduped entity rows | yes | `entities` section absent |
| `textrazor_unique_entity_density_per_1k_words` | `unique_count × 1000 / textrazor_word_count` | yes | entities absent or `word_count ≤ 0` |
| `textrazor_entity_mention_density_per_1k_words` | `mention_count × 1000 / textrazor_word_count` | yes | entities absent or `word_count ≤ 0` |
| `textrazor_unique_entity_density_per_1k_chars` | `unique_count × 1000 / page_text_length` | no (derived at dossier panel load) | entities absent or `page_text_length ≤ 0` |

**Proxy-test expectations for density (document in dossier JSON + limitations):**

| Metric class | Expected behavior in incremental ladder |
| ------------ | --------------------------------------- |
| Raw counts | High Δ adjusted R² after length step; often collapses after BGE |
| Word-normalized density | Smaller length-step gain; may still collapse after BGE if tracking relevance |
| Char-normalized density | Same-length bins should show more stable association than raw counts when density is real |

Shared counting logic lives in `src/seo_rank/textrazor.py` (extract from
`gemini_nwh_similarity.py` to avoid drift). Re-normalizing stored runs with
TextRazor responses materializes persisted columns without re-fetching API data.

**Out of scope for 5.6 density v1:** keyword–entity overlap, type-weighted density,
passage-level density (Phase 5.5), confirmatory Spearman/BH on density families.

**Out of scope for 5.6 overall:** causal inference, IV / `PanelOLS`, URL fixed
effects, confirmatory promotion to `actionable_association`, BH adjustment across
dossier tests (exploratory appendix only).

#### Dev slices

**Progress:** 0 of 6 shipped.

0. **[ ] Slice 0 — Entity count & density materialization**
   - Add shared `_entity_dedupe_key()` / `_count_entities()` in `textrazor.py`;
     refactor `analysis/gemini_nwh_similarity.py` to import the helper.
   - Extend `normalize_page_metrics()` with mention count, unique count, and
     word-normalized density columns (`null` when section missing, not silent zero).
   - Update `textrazor_page_metrics_curated` and feature mart schemas in
     `normalize.py` / `features.py` (bounded columns, validation rules).
   - Tests: `test_textrazor_normalization.py`, `test_feature_marts.py` (dedupe,
     null semantics, density formula).

1. **[ ] Slice 1 — Core dossier module + factor vs proxy report**
   - Add `src/seo_rank/stats/signal_dossier.py`: panel load via
     `build_family_source_frames`, dossier candidate registry (including density
     bundle), derive `textrazor_unique_entity_density_per_1k_chars` at panel
     load, JSON-serializable summary envelope, limitations text.
   - Add `analysis/signal_factor_report.py`: `--run`, `--depth`, writes
     `runs/{run_id}/stats/signal_factor_report.json` + terminal table (Density
     metrics section).
   - Wire univariate adjusted R² from existing `textrazor_explainability` where
     applicable; extend `TEXTRAZOR_RANKING_METRICS` with count/density columns.
   - Tests: `tests/unit/test_signal_dossier.py` (panel load, JSON shape,
     char-density derivation).

2. **[ ] Slice 2 — NDCG@k + incremental regression ladder**
   - **NDCG@k** per signal per keyword; macro summaries; configurable k.
   - **Incremental OLS ladder:** baseline → length + keyword FE → `+ bge` →
     `+ textrazor_*` (per metric and joint, including density bundle);
     keyword-clustered SEs when K ≥ 2.
   - Report Δ adjusted R² and coefficient stability at each rung; label proxy
     expectations for raw counts vs word/char density.
   - Tests: synthetic panel where signal matches rank; proxy signal vanishes
     after BGE step; raw count tracks length, density retains signal after length
     step in designed fixture.

3. **[ ] Slice 3 — Partial correlation + subset analyses**
   - **Partial correlation** of each candidate vs rank controlling for BGE
     (and optionally length), within-keyword and pooled variants.
   - **Deprecated-tag strata:** re-run Spearman / NDCG within deprecated-tag
     strata (primary discriminant for structural checks vs raw counts).
   - **Same-similarity bins:** bins on `bge_normalized_score`; re-test within
     bins (discriminating "same relevance, different rank" cases).
   - Tests: partial ρ drops when signal is pure function of BGE; subset slices
     retain signal when confound is binned out.

4. **[ ] Slice 4 — Stability + negative controls**
   - **Leave-one-keyword-out:** median Spearman, NDCG macro mean, incremental
     Δ R² with one keyword removed; surface max influence keyword.
   - **Negative controls:** within-keyword permuted signal (including density
     columns); expect null association; compare candidate metrics to control
     distribution.
   - Optional: rank-decile segments (ranks 1–3 vs 4–10 vs 11–20) as
     exploratory slices (absorbs part of Phase 5.4 backlog).
   - Tests: permuted control ≈ 0; LOKO stable when no single-keyword dominance.

5. **[ ] Slice 5 — Out-of-sample validation + CLI polish**
   - **Keyword holdout:** `--holdout`, `--holdout-fraction` (default 0.2),
     `--seed`; metrics on train vs held-out keywords separately.
   - **Time-split:** `--compare-run RUN_ID_B` for overlapping keywords across
     two crawls; report metric drift (exploratory).
   - Complete terminal report sections; document in `TESTING.md`.
   - Tests: holdout split reproducibility; time-split requires overlapping
     keyword set or explicit skip reason.

#### Phase 5.6 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Entity counts + word densities in `textrazor_page_metrics` | 0 | Open |
| Shared entity dedupe helper (no drift vs `gemini_nwh_similarity`) | 0 | Open |
| Dossier registry includes density bundle + char-density derivation | 1 | Open |
| `signal_dossier.py` + `signal_factor_report.json` schema | 1 | Open |
| NDCG@k per signal with macro summaries | 2 | Open |
| Incremental OLS ladder through BGE then TextRazor (incl. density) | 2 | Open |
| Partial correlation controlling for BGE | 3 | Open |
| Same-length and same-similarity subset re-tests | 3 | Open |
| Leave-one-keyword-out stability block | 4 | Open |
| Negative controls (permuted signal, incl. density) | 4 | Open |
| Keyword holdout validation | 5 | Open |
| Optional time-split across two runs | 5 | Open |
| Limitations: observational, no causal claims; word vs char denominator note | 0–5 | Open |

### Phase 5.7 — TextRazor structured signals & entity salience

Deepen TextRazor usage beyond page-level max scores and structural counts.
Today the main pipeline requests `entities`, `topics`, `words`, `phrases`,
`relations`, `entailments`, `senses`, and `spelling`, but normalizes only a
subset: `max(confidenceScore)`, `max(relevanceScore)` (entity salience per
[TextRazor REST docs](https://www.textrazor.com/docs/rest)), topic/category
max scores, entailment maxes, and relation/property/noun-phrase **counts**.
`parquet/entities/` stores per-mention `relevance` but is not joined into
`analysis_mart` or ranking explainability. Word-quality metrics use a
fixture-only top-level `words` shape instead of `sentences[].words` with real
`senses` and `spellingSuggestions`. The analysis script
`analysis/gemini_nwh_similarity.py` parses more fields but is not wired into
`seo-rank run` or Phase 5 artifacts.

**Tracked in Phase 5 slices 35–42.** **Depends on** shipped TextRazor ingest
(slices 21–28) and family-aware stats (slices 29–30). **Complements** Phase 5.6
(proxy/factor dossier) and slice 31 (golden fixtures). **Does not** replace the
Phase 5 confirmatory estimand on similarity backends.

**Entity salience:** TextRazor exposes salience as `Entity.relevanceScore`
(0–1, document importance) distinct from `confidenceScore` (validity). Phase
5.7 expands salience from a single page `max(relevanceScore)` to distributional
and per-entity features usable in family stats and curated explainability.

**Panel:** same grain (`target_keyword_id × canonical_url_hash`, top-N SERP).
New columns land in `textrazor_page_metrics` (and optionally enriched
`entities` curated); `analysis_mart` similarity columns unchanged.

**Not requested today (deferred unless a future slice adds CLI flags):**
`dependency-trees` (slice 39 adds it), `url` input, Prolog `rules`, custom
entity dictionaries, `cleanup.mode` / `languageOverride`, entity type filters,
Account API quota probes.

#### Unused API surface this phase targets

| Area | Currently | Phase 5.7 target |
| ---- | --------- | ---------------- |
| Entity salience | `max(relevanceScore)` only | Mean, top-k, mention-weighted aggregates; optional keyword overlap |
| Entity metadata | `entity_id`, `matched_text`, `types` in `entities` | `wikidataId`, `wikiLink`, `entityEnglishId`, `freebaseTypes`, `data` |
| Topics | `textrazor_topic_score` max | Top `label`, `wikidataId`, `wikiLink` |
| Categories | Max `score` / `classifierScore`; one classifier | Top label + `classifierId`; add IAB taxonomy on main run |
| Words / senses / spelling | Fixture booleans on wrong key | `sentences[].words`, `senses[]`, `spellingSuggestions[]` |
| Relations / properties / phrases | Counts only | Resolved text/labels where offsets allow |
| Entailments | Max score/prior/context in families only | Promote into curated explainability where useful |
| Syntax | Not requested | `dependency-trees` complexity scalars (slice 39) |

#### Dev slices

**Progress:** 0 of 8 shipped.

1. **[ ] Slice 35 — Word/sense/spelling parse fix**
   - Refactor `normalize_page_metrics()` to walk `response.sentences[].words`.
   - Replace `isGrammar` / `isSense` / `isSpelling` with API fields:
     `senses` (max sense score), `spellingSuggestions` (flag count).
   - Update fixtures to REST-shaped JSON; keep `textrazor_page_metrics_complete`
     section-presence logic accurate.
   - Tests: `tests/unit/test_textrazor_normalization.py` with live-shaped payloads.

2. **[ ] Slice 36 — Entity salience aggregates**
   - Add salience aggregation from `entities.relevance` per page: mean, median,
     top-3 max, mention count, unique entities (extend page-metrics builder).
   - Join onto `textrazor_page_metrics` feature mart at existing keys.
   - Optional exploratory: overlap of top-k salient `entity_id` vs keyword
     tokens (document limitation in JSON).
   - Tests: synthetic entity rows → expected aggregates.

3. **[ ] Slice 37 — Topic & category label features**
   - Persist `textrazor_top_topic_label`, `textrazor_top_topic_score`,
     `textrazor_top_category_label`, `textrazor_top_category_classifier_id`.
   - Add `textrazor_iab_content_taxonomy_3.0` to
     `TEXTRAZOR_PAGE_METRIC_CLASSIFIERS` for main `seo-rank run` requests.
   - Validation: scores in [0, 1]; labels UTF-8 non-null when section present.
   - Tests: multi-classifier fixture → both IPTC and IAB top rows materialized.

4. **[ ] Slice 38 — Structured relation/property/phrase features**
   - Reconstruct top noun phrases from `wordPositions` + sentence words.
   - Emit bounded top-phrase representation and named property samples.
   - Parse relation `params` (SUBJECT/OBJECT) when word offsets resolve.
   - Tests: offset reconstruction + empty-offset graceful degradation.

5. **[ ] Slice 39 — dependency-trees syntactic features**
   - Append `dependency-trees` to `TEXTRAZOR_PAGE_METRIC_EXTRACTORS`.
   - Compute page-level scalars: mean dependency depth, unique
     `relationToParent` count, optional mean sentence length from tokens.
   - Document added latency/token cost in `ARCHITECTURE.md` and `README.md`.
   - Tests: dependency-tree fixture → non-null syntactic columns.

6. **[ ] Slice 40 — Entity KB linkage enrichment**
   - Extend `normalize_entities()` with `entity_english_id`, `wikidata_id`,
     `wiki_link`, `freebase_types`, optional `data` key list (bounded).
   - Page-level: `textrazor_linked_entity_fraction`,
     `textrazor_entity_type_entropy` joined to page mart.
   - Tests: linked vs unlinked entity mix → expected fractions.

7. **[ ] Slice 41 — Signal registry for new families**
   - Add Phase 5.7 columns to `analysis_spec.v1.yaml` `signal_families` (or ship
     `analysis_spec.v2.yaml` if column cardinality forces a version bump).
   - Extend `features.py` validation, `families.py` dispatch, and `stats_*`
     nested `rank_depths.*.families` for new TextRazor families.
   - Tests: `test_stats_spec.py`, `test_stats_family_artifacts.py` with synthetic
     panel including salience + label columns.

8. **[ ] Slice 42 — Salience explainability & golden fixtures**
   - Extend `textrazor_explainability.py` curated candidates with salience
     aggregates and topic/category labels; update
     `ranking_explainability_viz.py` when a new primary salience column wins.
   - Wire `analysis/textrazor_ranking_r2.py` to report new metrics.
   - Golden end-to-end fixture (complements slice 31): known rank ordering for at
     least one salience aggregate vs `serp_rank` on synthetic panel.
   - Tests: `test_textrazor_ranking_explainability.py` + new golden test module.

#### Phase 5.7 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Word metrics parsed from `sentences[].words` | 35 | Open |
| Real sense and spelling suggestion scores materialized | 35 | Open |
| Entity salience aggregates on `textrazor_page_metrics` | 36 | Open |
| Top topic/category labels + IAB classifier on main run | 37 | Open |
| Structured phrase/relation/property features beyond counts | 38 | Open |
| `dependency-trees` extractor + syntactic scalars | 39 | Open |
| Entity KB linkage fields in `entities` + page mart | 40 | Open |
| New TextRazor families in `analysis_spec` and `stats_*` | 41 | Open |
| Salience columns in explainability + golden fixture | 42 | Open |
| Limitations: observational; salience ≠ causal ranking factor | 42 | Open |
