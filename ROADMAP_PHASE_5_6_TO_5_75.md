# Phase 5.6 — Signal factor dossier (umbrella)

Deliverable: `runs/{run_id}/stats/signal_factor_report.json` plus a new
`stats_report.md` subsection. This phase answers: does a signal add ranking
information beyond what we already have, or is it a proxy for existing signals?

Six slices build it (spec: slices 0–5 in Phase 5 slice table; acceptance rows
labeled **5.6**). **Factor vs proxy** uses a **staged ladder** on existing
Phase 5 machinery:

1. **Baseline adjusted R²** — pooled OLS, keyword FE + length (slice 5).
2. **+ Similarity family** — BGE/Gemini blocks.
3. **+ New TextRazor family** — incremental adjusted R² (marginal contribution).
4. **Proxy battery** — per-family Spearman, within-family Pearson correlation
   matrix, partial correlations controlling for primary similarity backend.
5. **NDCG@k on top 20** — sort pages by metric; per-keyword NDCG vs
   `serp_rank` 1–20 (revealed relevance); mean/median across keywords.

**LOKO:** drop one keyword, refit pooled model per depth, record coefficient and
adjusted R²; flag instability when coefficient signs flip or move > 50%.
**Holdout:** 80/20 keyword split; train on 80%, test predictive performance on
20%; optional time split if run history supports it.
**Negative controls:** shuffle outcome within keyword; shuffle one feature
within keyword; verify correlations collapse.
**Subset analyses:** length-matched and similarity-matched strata.

#### Dev slices

**Progress:** 0 of 6 shipped, 6 open.

1. **[ ] Slice 0 — Entity density materialization**
   - Count entities per page; words per page (TextRazor `words` array).
   - Compute `entity_density = entity_count / word_count`.
   - Persist in `textrazor_page_metrics` (`entity_count`, `word_count`,
     `entity_density`); validation bounds `entity_density` in [0, 1].
   - Tests: `tests/unit/test_textrazor_page_metrics_density.py` (zero words
     → null density; mock response → correct counts).

2. **[ ] Slice 1 — Factor report core**
   - `stats/factor_report.py`: `build_signal_factor_report(marts, spec)` runs
     the staged ladder; JSON schema + schema validation tests.
   - Golden fixture: `tests/unit/test_signal_factor_report.py`.

3. **[ ] Slice 2 — Proxy battery**
   - Per-family Spearman + within-family correlation matrix + partial
     correlations vs BGE primary.
   - Tests: `tests/unit/test_proxy_battery.py` (known collinear pair → partial
     correlation ≈ 0).

4. **[ ] Slice 3 — NDCG@k**
   - `stats/ndcg.py`: per-keyword NDCG@20 for each similarity + TextRazor
     metric; summary stats in factor report.
   - Tests: `tests/unit/test_ndcg.py` (perfect order → 1.0; reverse → ~0).

5. **[ ] Slice 4 — LOKO + holdout**
   - LOKO stability metrics; keyword holdout evaluation; optional time split.
   - Tests: `tests/unit/test_loko_holdout.py` (known model → LOKO recovers
     coefficients).

6. **[ ] Slice 5 — Negative controls + subsets**
   - Null predictors (shuffled outcome/feature); length/similarity-matched
     subsets.
   - Tests: `tests/unit/test_negative_controls.py` (shuffled → ρ ≈ 0).

#### Phase 5.6 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `signal_factor_report.json` with staged ladder R² and marginal contribution | 1 | Open |
| Proxy battery with partial correlations | 2 | Open |
| NDCG@20 per metric with keyword distribution | 3 | Open |
| LOKO stability and holdout evaluation | 4 | Open |
| Negative controls collapse as expected | 5 | Open |
| Entity density in `textrazor_page_metrics` | 0 | Open |

---

# Phase 5.7 — TextRazor extraction depth

Parse the full TextRazor response beyond entities/topics/categories: word/sense/
spelling data, entity salience, structured relations/properties/phrases,
dependency trees, and knowledge-base linkage. Converts slices 35–42 from
trackers into full specification.

**Primary decision (v1):** each extraction depth is an independent signal
family in `analysis_spec.v1.yaml` with its own grain and join key; no changes
to existing entity/topic/category families (backward compatibility preserved).

#### Dev slices

**Progress:** 0 of 8 shipped, 8 open (slices 35–42 in Phase 5 table).

See slice 35–42 rows in Phase 5 slice table and acceptance table for
specification and status.

#### Phase 5.7 acceptance criteria

See Phase 5 acceptance table rows for slices 35–42.

---

# Phase 5.75 — Retrieve-then-rerank (deferred)

Add a bi-encoder retrieval stage before the BGE cross-encoder reranker: embed
query and pages separately with `BAAI/bge-m3`, score by dot product, take the
top-k candidates, then rerank with the existing BGE cross-encoder. Reduces
cross-encoder cost on large panels and produces self-owned dual-encoder vectors
as a side effect.

**Status:** deferred. **Promoted to Phase 10 Slice 3** (the embedding store
needs the dual-encoder path for self-owned vectors). The retrieval-side cost
optimization remains valid independent motivation.
