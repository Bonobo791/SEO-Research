# Phase 10 — Embedding Store (keystone)

Persist the dense vectors that BGE and Gemini already compute and throw away,
so centroid/radius/focus math and the universe layer have something to compute
on. Today `bge_reranker.py` is a cross-encoder that returns a scalar logit per
(keyword, page) pair (no vector exists to store), and `gemini_embeddings.py`
writes the full `EmbedContentResponse` (with the 3072-d vector) into
`raw_responses/endpoint=gemini_embeddings` but nothing parses it into a usable
form. This phase adds a curated embeddings mart and a self-owned dual-encoder
path going forward.

**Primary decision (v1):** two write paths. (1) **Normalize-from-raw:** a
curated `embeddings` table materialized from the existing
`endpoint=gemini_embeddings` raw payloads (no re-fetch), unit-normalized, keyed
`(run_id, target_keyword_id, canonical_url_hash, role)` where
`role ∈ {query, page, passage}`. (2) **Live dual-encoder:** the deferred Phase
5.75 BGE-m3 bi-encoder becomes the forward-looking source of self-owned vectors
(query and page encoded separately → dot-product = retrieval score), persisted
to the same mart. Model name/version is pinned in `run.json` `config` and in
every `embeddings` row — scores are only comparable within one model.

**Mart columns (v1):** `run_id`, `target_keyword_id`, `canonical_url_hash`
(null for `role=query`), `role`, `model`, `dim`, `vector` (fixed-size list of
float32, L2-normalized), `source` (`gemini_embeddings_raw` | `bge_m3_live`).

**Guardrails:** a row whose `model` differs from the run's pinned model is
excluded from any pooled computation (never silently mix spaces); `dim` must
match the model registry entry; passage rows require a non-null
`page_id`/`passage_id` join key to `passages`.

**Out of scope for 10:** centroid/radius/focus computation (Phase 11), any
stats wiring (Phase 11 registers these as families), passage MaxSim scoring
(Phase 11.5).

#### Dev slices

**Progress:** 0 of 6 shipped.

1. **[ ] Slice 1 — Gemini raw → curated embeddings**
   - `build_embeddings_frame()` in `data/normalize.py`: parse
     `endpoint=gemini_embeddings` payloads, extract the float vector per
     (role, keyword, URL), L2-normalize, emit the mart schema above.
   - Null/excluded when payload missing, malformed, or model mismatch.
   - Tests: `test_run_normalize.py` with real-shaped `EmbedContentResponse`
     fixtures; unit-norm assertion; dedupe on latest `timestamp`.

2. **[ ] Slice 2 — Embeddings feature mart + validation**
   - `data/features.py` entry; fixed-size-list validation (`dim` consistent
     per model); `vector` excluded from `ANALYSIS_REQUIRED_COLUMNS` (it is a
     store, not a predictor column).
   - Tests: `test_feature_marts.py` schema + bounds.

3. **[ ] Slice 3 — BGE-m3 dual-encoder live path (promote Phase 5.75 Slice 2)**
   - Query and page encoded separately with `BAAI/bge-m3`; dot-product
     retrieval score; vectors persisted to the same mart with
     `source=bge_m3_live`.
   - `--live-bge` wiring; defer model load until first scorable keyword
     (consistent with Phase 5.2 Slice 3).
   - Tests: score shaping; dot-product == persisted retrieval score.

4. **[ ] Slice 4 — Query + passage embeddings**
   - Extend both write paths to `role=query` (keyword text) and
     `role=passage` (from `passages`); passage rows carry join keys.
   - Tests: passage grain round-trip; query rows have null URL hash.

5. **[ ] Slice 5 — Model registry + pinning**
   - `EMBEDDING_MODEL_REGISTRY` (name → dim, normalize rule); `run.json`
     records the pinned model; cross-model exclusion guard.
   - Tests: mixed-model panel → foreign-model rows dropped with a logged reason.

6. **[ ] Slice 6 — Golden fixture + stored-run regression**
   - Synthetic `endpoint=gemini_embeddings` payloads with known vectors;
     assert the curated mart reproduces them (values, norms, keys) without
     re-fetching.
   - Stored-run: re-normalize an old run materializes `embeddings` from raw
     with zero live calls.

#### Phase 10 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `embeddings` mart materialized from Gemini raw payloads, no re-fetch | 1, 6 | Open |
| Unit-normalized fixed-size vectors with model pinned per row | 1, 2, 5 | Open |
| BGE-m3 dual-encoder path writes self-owned query/page vectors | 3 | Open |
| Query and passage roles populated with correct join keys | 4 | Open |
| Cross-model rows excluded from pooled computation | 5 | Open |
| Golden fixture + stored-run regression green | 6 | Open |

---

# Phase 11 — Site/Topic Layer (centroids, radii, focus)

Compute the site-level topical metrics — domain centroid (`siteEmbedding`
analog), per-page radius (`siteRadius` analog), site focus (`siteFocusScore`
analog), and domain↔query topic fit — and register them as **new signal
families** so the entire existing Phase 5 engine (Spearman + BH, pooled OLS,
diagnostics, Plackett-Luce at all four rank depths) runs on them for free via
`stats/families.py`. This is the first direct test of "does the centroid
distance even matter" at the associational level, using machinery already
built and tested.

**Primary decision (v1):** centroid = **robust** (component-wise median
direction, then L2-normalized) over a domain's page vectors, not the mean —
a single off-topic page must not drag the core. Radius = `1 − cos(page_vec,
centroid)`. Focus = `1 − mean(radius over the domain's pages)`. Topic fit =
`cos(centroid, query_vec)`. All computed per `run_id` from the Phase 10
`embeddings` mart, joined back to the `analysis_mart` panel grain via the
derived `domain` column (same derivation as `domain_features`).

**Family registration:** new kind `site_topic` mapped to a
`site_topic_features` mart in `SOURCE_MART_BY_KIND`; families appended (never
reordered) to `analysis_spec.v1.yaml`: `site_topic_fit`
(`domain_query_cosine`), `site_focus` (`site_focus_score`), `page_radius`
(`page_site_radius`, sign-flipped so higher = more central). No
`analysis_mart` schema bump — mirrors the Phase 6.2/7.x pattern.

**Guardrails:** a domain with < 3 embedded pages yields `null` centroid/focus
(not a fabricated value); if the run's `embeddings` mart is empty or the
model is unpinned, the family registers as `skipped` with a reason rather than
hard-failing the whole stats run (consistent with family hard-fail semantics
in Slice 30).

**Out of scope for 11:** temporal change tracking (Phase 12), using these as
model features for prediction (Phase 13), passage MaxSim (Phase 11.5).

#### Dev slices

**Progress:** 0 of 7 shipped.

1. **[ ] Slice 1 — Centroid/radius/focus computation**
   - `data/site_topic.py`: group `embeddings` by domain → robust centroid;
     per-page radius; per-domain focus. Pure functions on the mart.
   - Tests: synthetic domain with a planted off-topic page → median centroid
     isolates it, mean does not (known-answer fixture).

2. **[ ] Slice 2 — `site_topic_features` mart + domain join**
   - Join page radius + domain focus onto the panel grain via derived
     `domain`; `domain_query_cosine` via query vectors.
   - Bounded validation: radius/focus/fit ∈ [−1, 1] (fit) / [0, 2] (radius).
   - Tests: `test_feature_marts.py`.

3. **[ ] Slice 3 — Family registry + spec**
   - `site_topic` kind in `VALID_SIGNAL_FAMILY_KINDS` +
     `SOURCE_MART_BY_KIND`; three families appended to `analysis_spec.v1.yaml`.
   - Tests: `test_stats_families.py`, `test_stats_spec.py`.

4. **[ ] Slice 4 — Stats wiring**
   - Family-aware Spearman/OLS/diagnostics/PL consume `site_topic_features`;
     `#### Family: site_topic_*` blocks in `stats_*`.
   - Tests: `test_stats_family_artifacts.py` with a synthetic panel where
     topic fit has a known rank relationship.

5. **[ ] Slice 5 — Small-domain null semantics**
   - Domains under the page threshold → nulls; completeness flag
     `site_topic_complete`.
   - Tests: under-threshold domain rows null, over-threshold rows populated.

6. **[ ] Slice 6 — Golden fixtures**
   - Known-focus synthetic sites; assert focus ordering and that the stats
     engine recovers a planted topic-fit ↔ rank association.
   - Complements Phase 5 Slice 31 (unblocks its similarity+TextRazor fixture
     pattern for site-topic families).

7. **[ ] Slice 7 — Docs**
   - `ARCHITECTURE.md` (mart + family), `TESTING.md`, limitations text:
     centroid metrics are associational, model-dependent, and not Google's
     literal `siteFocusScore`.

#### Phase 11 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Robust domain centroids resist planted off-topic pages | 1 | Open |
| Radius/focus/fit join onto panel grain with bounds validation | 2 | Open |
| `site_topic` families registered without `analysis_mart` schema bump | 3 | Open |
| Full Phase 5 stats run on site-topic families at all rank depths | 4 | Open |
| Under-threshold domains yield nulls, not fabricated values | 5 | Open |
| Golden fixtures prove known focus/fit relationships | 6 | Open |

---

# Phase 11.5 — Passage MaxSim scoring

Add passage-level relevance: split pages into passages (already have
`passages` / `passage_features`), embed them (Phase 10 Slice 4), and score a
page's relevance to a query as `max over passages cos(query, passage)` — the
ColBERT late-interaction pattern and the closest analog to Google's passage
ranking. Registers as a similarity-adjacent signal family.

**Primary decision (v1):** `page_maxsim_score = max_p cos(query_vec,
passage_vec)` per (keyword, page); also persist `best_passage_id` for
explainability. Family `passage_maxsim` (kind `site_topic` reused or a new
`passage_sim` kind) at the panel grain.

#### Dev slices

**Progress:** 0 of 3 shipped.

1. **[ ] Slice 1 — MaxSim computation + mart columns**
   - `data/site_topic.py` (or `similarity.py`): join passage embeddings to
     query vectors, reduce to per-page max; persist `page_maxsim_score`,
     `best_passage_id`.
   - Tests: multi-passage page where one passage matches the query → max
     selects it.

2. **[ ] Slice 2 — Family registration + stats wiring**
   - Append `passage_maxsim` family; family-aware stats consume it.
   - Tests: `test_stats_family_artifacts.py`.

3. **[ ] Slice 3 — Golden fixture**
   - Synthetic page with a planted best-matching passage; assert MaxSim
     outranks a page whose relevance is diffuse.
