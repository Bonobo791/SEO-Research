# Deferred

Items parked pending prerequisites, data availability, or explicit re-scoping.

- **GSC behavioral feed** — first-party Google Search Console data (queries,
  clicks, impressions, positions) as the `w_beh` term in the universe model
  and as validation ground truth. Account-gated; requires OAuth setup and
  property verification. When added, becomes Phase 14.
- **Real-time serving** — the universe model as a live API for content
  scoring. Requires Phase 13 validation to pass first.
- **Passage-level Plackett-Luce** — passage-grain ranking model. Requires
  Phase 11.5 passage embeddings.
- **Vertex AI Gemini** — switch from AI Studio to Vertex for billing
  consolidation. Not needed until usage justifies it.
- **Multi-language support** — non-English SERP collection and embedding
  models. Requires language-specific embedding model selection.

---

# History

Shipped phases and their final state.

### Phase 1–4 (shipped)

- **Phase 1:** Core pipeline — DataForSEO SERP → page_text → parquet lake.
- **Phase 2:** Gemini embeddings integration (AI Studio).
- **Phase 3:** BGE cross-encoder reranker (local CUDA).
- **Phase 4:** TextRazor entities/topics/categories extraction.

### Phase 5 slices 1–10, 15–20, 21–26, 27–30, 32–33 (shipped)

Statistical analysis engine: per-keyword Spearman + BH, pooled OLS with
keyword FE + clustered SEs, Plackett-Luce at four rank depths, guardrails,
golden fixtures, TextRazor-only ingestion, signal family registry,
family-aware stats dispatch, combined artifacts.
