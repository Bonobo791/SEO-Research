# Goals

`GOALS.md` is the active-scope contract for this repository. Keep
`ROADMAP.md` for backlog, history, and deferred work.

## Active Objective

Build Phase 4 live **page-level** similarity scoring for SEO ranking similarity
research.

### Current capability

Phase 3 shipped: offline and gated live runs loop every capped cluster keyword,
group outputs under `keyword_results`, and annotate flattened rows with
`target_keyword`.

Phase 4 is in progress: page-level **fixture** scoring exposes **BGE**, **Gemini
Doc Retrieval**, and **Gemini Semantic Similarity** per SERP row in offline and
gated live artifact generation. **Live backend execution is not done yet** —
fixtures stand in until the integration work below ships.

### Phase 4 objective

For each cluster keyword, score **full parsed page text** for every top-20
organic SERP result with **three** page-level measurements:

| Name | JSON key | Live implementation |
|------|----------|---------------------|
| BGE | `bge` | FlagEmbedding cross-encoder reranker |
| Gemini Doc Retrieval | `gemini_doc_retrieval` | Vertex `RETRIEVAL_QUERY` + `RETRIEVAL_DOCUMENT` |
| Gemini Semantic Similarity | `gemini_semantic_similarity` | Vertex `SEMANTIC_SIMILARITY` on keyword and page |

Store every score in artifacts for downstream analysis. Offline runs keep
deterministic fixtures; live runs call real backends when credentials and optional
local compute are available.

### Dev slices

1. **Fixture backends** — done: offline-testable BGE, Gemini Doc Retrieval, and
   Gemini Semantic Similarity scorers behind a shared page-level interface.
2. **Page scope** — done: score parsed page text vs `target_keyword` per
   organic result.
3. **Per-keyword wiring** — done: attach page similarity scores to
   `keyword_results` in offline and live orchestration paths.
4. **Artifacts** — done: expose raw + normalized page similarity in `run.json` /
   `report.md`.
5. **Live integration** — **remaining**: replace fixture scorers with real
   Vertex Gemini embeddings (Doc Retrieval + Semantic Similarity) and local BGE
   inference (see [Remaining live backend work](#remaining-live-backend-work)).
6. **Docs** — in progress: align `ARCHITECTURE.md`, `README.md`, `TESTING.md`,
   `ROADMAP.md`, `.env.example`.

### Remaining live backend work

Implement the slices below in order. Follow `AGENTS.md`: failing test first,
minimal implementation, then `python -m pytest`. Do **not** break offline runs or
existing artifact shape.

**Touchpoints today**

- Scoring entry point: `compute_page_similarity_scores()` in
  `src/seo_rank/similarity.py` (fixtures only).
- Call sites: `build_offline_keyword_result()` and `build_live_keyword_result()`
  in `src/seo_rank/cli.py`.
- Artifact shape under `page_similarity` (extend only with test + doc updates):

```json
{
  "url": "...",
  "page_similarity": {
    "bge": { "raw_score": 0.0, "normalized_score": 0.0 },
    "gemini_doc_retrieval": { "raw_score": 0.0, "normalized_score": 0.0 },
    "gemini_semantic_similarity": { "raw_score": 0.0, "normalized_score": 0.0 }
  }
}
```

Use the **Name** column from the Phase 4 objective table in prose and Markdown
reports; use the **JSON key** column in `run.json` only.

---

#### Slice A — Gemini Doc Retrieval & Gemini Semantic Similarity (Vertex AI)

**Goal:** On live runs, replace the two Gemini fixture paths with real Vertex AI
Text Embeddings. Offline tests and `--dry-run` keep fixtures (`fixture_embedding`
→ Gemini Doc Retrieval, `fixture_semantic_embedding` → Gemini Semantic Similarity).

**1. Dependencies**

Add a `similarity` optional extra in `pyproject.toml`:

```toml
similarity = ["google-cloud-aiplatform>=1.60"]
```

Document install: `pip install -e ".[similarity,dev]"`.

**2. Environment**

Copy `.env.example` to `.env` at the project root. The CLI loads it automatically
via `seo_rank.env.load_project_env()`; **do not** rely on shell exports. Values
in `.env` override conflicting shell variables.

Extend `.env.example` with placeholders (no secrets in git):

- `GOOGLE_CLOUD_PROJECT` — GCP project ID with Vertex AI enabled
- `GOOGLE_CLOUD_REGION` — e.g. `us-central1`
- Credentials via Application Default Credentials (`gcloud auth application-default login`)
  or `GOOGLE_APPLICATION_CREDENTIALS` pointing at a service-account JSON file

Remove or replace stale `GOOGLE_API_KEY` / `GEMINI_API_KEY` placeholders if they
imply AI Studio; this integration uses **Vertex**, not the consumer Gemini chat
API.

**3. Model constant**

Pin one model ID in code (module-level constant or CLI default):

- **Default:** `gemini-embedding-001` (best quality; up to 3072 dims; 2048-token
  max sequence length)
- Alternatives only if you change the constant and docs together:
  `text-embedding-005` (English/code, up to 768 dims),
  `text-multilingual-embedding-002` (multilingual, up to 768 dims)

**4. Implement `src/seo_rank/gemini_embeddings.py` (new module)**

Build a small client with an injectable backend so unit tests never hit the network:

```python
def embed_texts(
    *,
    model_id: str,
    instances: list[dict[str, object]],  # content, task_type, optional title
    output_dimensionality: int | None = None,
    auto_truncate: bool = True,
    client: GeminiEmbeddingClient | None = None,
) -> list[list[float]]: ...
```

Use the Vertex AI Python SDK pattern:

```python
import vertexai
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

vertexai.init(project=..., location=...)
model = TextEmbeddingModel.from_pretrained("gemini-embedding-001")
text_input = TextEmbeddingInput(text, "RETRIEVAL_QUERY")
embedding = model.get_embeddings([text_input], output_dimensionality=3072)
vector = embedding[0].values
```

**5. Task types — set explicitly for each Gemini measurement**

You emit **two** Gemini scores per page. Use separate embed calls; do not reuse
vectors across task types.

**A. Gemini Doc Retrieval → `gemini_doc_retrieval`**

| Input | `task_type` | `content` | Optional fields |
|-------|-------------|-----------|-----------------|
| Target keyword | `RETRIEVAL_QUERY` | keyword string | — |
| Each parsed page | `RETRIEVAL_DOCUMENT` | page body text | `title` = SERP title when available |

Cosine between the two retrieval vectors → `page_similarity.gemini_doc_retrieval`.

**B. Gemini Semantic Similarity → `gemini_semantic_similarity`**

Google documents `SEMANTIC_SIMILARITY` for semantic textual similarity (STS), not
for search retrieval. Keep it as a **separate analysis signal** alongside Gemini
Doc Retrieval.

| Input | `task_type` | `content` |
|-------|-------------|-----------|
| Target keyword | `SEMANTIC_SIMILARITY` | keyword string |
| Each parsed page | `SEMANTIC_SIMILARITY` | page body text |

Do **not** pass `title` with `SEMANTIC_SIMILARITY` (title is only valid with
`RETRIEVAL_DOCUMENT`). Cosine between the two STS vectors →
`page_similarity.gemini_semantic_similarity`.

**6. Scoring logic in `similarity.py`**

Add a live code path (e.g. `compute_page_similarity_scores_live`):

**Gemini Doc Retrieval (`gemini_doc_retrieval`):**

1. Embed keyword once with `RETRIEVAL_QUERY`.
2. For each page, embed body with `RETRIEVAL_DOCUMENT` (+ optional SERP `title`).
3. L2-normalize, cosine, round to 6 decimals → `gemini_doc_retrieval`.

**Gemini Semantic Similarity (`gemini_semantic_similarity`):**

1. Embed keyword with `SEMANTIC_SIMILARITY`.
2. For each page, embed body with `SEMANTIC_SIMILARITY`.
3. L2-normalize, cosine, round to 6 decimals → `gemini_semantic_similarity`.

**Shared:**

- `gemini-embedding-001` takes **one input per `get_embeddings` call** in the
  official Python example — budget **41 embed calls per keyword** at depth 20
  (1 retrieval query + 20 retrieval docs + 1 STS keyword + 20 STS docs).
- Write `raw_score` and `normalized_score` (same value unless you add a separate
  normalization policy later).

**7. Long pages**

Models cap at **2048 tokens**. Default API behavior: `autoTruncate=true` truncates
overlong input. Log or store `statistics.truncated` and `statistics.token_count`
when the SDK exposes them. Do not silently change page-level scope to passage
chunking in this slice.

**8. Wire the live CLI path only**

In `build_live_keyword_result()` (`cli.py`), when live providers are enabled and
Vertex env validates, call the live Gemini path instead of fixture
`compute_page_similarity_scores()`. Keep `build_offline_keyword_result()` on
fixtures.

Append `"vertexai.text_embeddings"` (or similar) to `network_calls` once per
keyword batch or per request — pick one convention and document it.

**9. Tests (write these before implementation)**

| Test | File | Assert |
|------|------|--------|
| Task types and instance shape | `tests/unit/test_gemini_embeddings.py` | Mock receives `RETRIEVAL_QUERY` + `RETRIEVAL_DOCUMENT` for Gemini Doc Retrieval; `SEMANTIC_SIMILARITY` for keyword and each page for Gemini Semantic Similarity |
| Fixture triple scores | `tests/unit/test_similarity_features.py` | `gemini_doc_retrieval` and `gemini_semantic_similarity` both present and can differ |
| Live path selection | `tests/unit/test_cli_run.py` | Injected mock: live keyword result uses live Gemini scorer, offline still fixtures |
| Integration (opt-in) | `tests/integration/` | Mark `@pytest.mark.integration`; gate on project/region/ADC like existing live smoke |

**10. Done when**

- Live `--live-providers` run produces non-fixture **Gemini Doc Retrieval** and
  **Gemini Semantic Similarity** scores when Vertex credentials are present.
- Offline `python -m pytest` stays green with zero network calls.
- `.env.example` and `TESTING.md` describe Vertex gates, not AI Studio keys.

---

#### Slice B — BGE (local cross-encoder)

**Goal:** On live runs, replace the `bge` fixture path with a real FlagEmbedding
reranker. This is a **cross-encoder** (query + document → score), not a
bi-encoder embed model like `bge-base-en-v1.5`.

**1. Dependencies**

Add to the same `similarity` extra:

```toml
similarity = ["google-cloud-aiplatform>=1.60", "FlagEmbedding>=1.2"]
```

**2. Model pin**

Choose and constant-pin a Hugging Face reranker, e.g. a `BAAI/bge-reranker-v2-*`
revision. Document the exact ID in `ARCHITECTURE.md` when merged.

**3. Implement loading**

- Lazy-load once per CLI run (not once per page).
- Optional env gate: `SEO_RANK_ENABLE_BGE=1` before downloading weights.
- Use `use_fp16=True` when GPU is available.
- Batch all `(keyword, page_text)` pairs for a keyword in one rerank call when
  the API allows.

**4. Query handling**

Pass `target_keyword` as the query. If the model card requires a retrieval
instruction prefix, prepend it to the query only — do not mutate document text.

**5. Scores**

Map reranker output to `raw_score` and `normalized_score`. BGE-family scores
cluster high (~0.6–1.0); treat them as **relative rank within a SERP**, not
calibrated probability. Do not rescale to match Gemini Doc Retrieval or Gemini
Semantic Similarity.

**6. Wire like Gemini**

Live path in `build_live_keyword_result()` only; offline stays on
`fixture_bge_reranker_score()`.

**7. Tests**

Mock the reranker in unit tests; optional integration test with
`SEO_RANK_ENABLE_BGE=1` and cached weights.

**8. Done when**

- Live run fills `bge` from FlagEmbedding when enabled.
- Offline tests unchanged.

---

#### Slice C — Shared cleanup

1. **`validate_live_provider_gate()`** — extend credential validation to require
   Vertex project + region when Gemini live similarity is requested (mirror
   DataForSEO/TextRazor error style: no secret values in exceptions).
2. **`pyproject.toml` / README / ARCHITECTURE / ROADMAP / TESTING`** — sync with
   Vertex + FlagEmbedding instructions above; remove stale `google-genai` /
   `gemini-embedding-2` / 8192-token references.
3. **Acceptance criteria below** — check off items as slices land.

## In Scope (current and near-term)

- Python CLI under `src/seo_rank/`.
- Pytest under `tests/unit/` and integration tests as needed.
- Triple page-level scorers (BGE, Gemini Doc Retrieval, Gemini Semantic Similarity)
  on every non-dry live run.
- **Page-level** similarity per organic SERP row (full parsed page text).
- JSON + Markdown artifacts with per-keyword page similarity payloads.

## Out Of Scope

- Passage-level similarity scoring.
- Domain-level URL inventory scoring.
- Storing and processing data with Parquet and Polars.
- `statsmodels` OLS, OLS pre-analysis, Benjamini-Hochberg.
- `runs/RUN_ID/` artifact layout and expanded reporting.
- Entity-derived ranking features.
- Direct page fetching outside DataForSEO.
- Causal claims about ranking factors.
- CI, deployment, databases, cache layers, production hosting.

## Acceptance Criteria (Phase 4)

- [x] Page-level fixture scores for **BGE**, **Gemini Doc Retrieval**, and
  **Gemini Semantic Similarity** exposed per SERP row in artifacts.
- [x] Scores land in `keyword_results` with `target_keyword` preserved.
- [x] Offline fixture tests cover `bge`, `gemini_doc_retrieval`, and
  `gemini_semantic_similarity` at page scope.
- [ ] Live **Gemini Doc Retrieval** and **Gemini Semantic Similarity** via
  Vertex AI (`gemini-embedding-001` default) with env-gated GCP credentials.
- [ ] Live **BGE** cross-encoder via FlagEmbedding with documented model pin
  and score calibration notes.
- [ ] All three live scorers run on every non-dry live similarity path (fixtures
  remain for offline tests only).
- [ ] Documentation and `.env.example` aligned with `ARCHITECTURE.md`,
  `TESTING.md`, `ROADMAP.md`.

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
