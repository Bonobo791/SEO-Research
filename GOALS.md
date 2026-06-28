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
gated live artifact generation. **Optional live provider controls** (`--live-gemini`,
`--live-textrazor`, env gates, hard failures) are shipped. **Live Gemini and BGE
backend execution is not done yet** — live runs still use fixtures for
`page_similarity` unless the remaining integration slices land.

### Phase 4 objective

For each cluster keyword, score **full parsed page text** for every top-20
organic SERP result with **three** page-level measurements:

| Name | JSON key | Live implementation |
|------|----------|---------------------|
| BGE | `bge` | FlagEmbedding cross-encoder reranker |
| Gemini Doc Retrieval | `gemini_doc_retrieval` | Asymmetric **search result** prompt prefixes (query vs document) |
| Gemini Semantic Similarity | `gemini_semantic_similarity` | Symmetric **sentence similarity** prompt prefix on keyword and page |

Store every score in artifacts for downstream analysis. Offline runs keep
deterministic fixtures; live runs call real backends when credentials and optional
local compute are available.

### Dev slices

1. **Fixture backends** — **done**: offline-testable BGE, Gemini Doc Retrieval, and
   Gemini Semantic Similarity scorers behind a shared page-level interface.
2. **Page scope** — **done**: score parsed page text vs `target_keyword` per
   organic result.
3. **Per-keyword wiring** — **done**: attach page similarity scores to
   `keyword_results` in offline and live orchestration paths.
4. **Artifacts** — **done**: expose raw + normalized page similarity in `run.json` /
   `report.md`.
5. **Provider controls** — **done**: `--live-gemini`, `--live-textrazor`, matching
   env gates, and hard failures when flags or credentials are missing.
6. **TextRazor live selection** — **done**: live TextRazor runs only when
   `--live-textrazor` is passed; default live runs skip entities.
7. **Live similarity backends** — **remaining**: `gemini_embeddings.py` +
   `gemini-embedding-2` scoring when `--live-gemini` is enabled; FlagEmbedding BGE
   when its gate ships (see [Remaining live backend work](#remaining-live-backend-work)).
8. **Docs** — **done** for root contract (`ARCHITECTURE.md`, `README.md`,
   `TESTING.md`, `ROADMAP.md`, `.env.example`). **Remaining:** `pyproject.toml`
   `similarity` extra and opt-in Gemini integration tests when backends land.

### Remaining live backend work

Implement the slices below in order. Follow `AGENTS.md`: failing test first,
minimal implementation, then `python -m pytest`. Do **not** break offline runs or
existing artifact shape.

### Approved live-provider contract

Live provider behavior for Phase 4 is now fixed unless a later goals update
changes it:

- `--live-providers` always enables live DataForSEO. There is no useful live run
  without it because DataForSEO provides keyword expansion, SERP results, and
  parsed page text.
- `--live-gemini` is optional and requires both `--live-providers` and an env
  safety gate. If requested without its env gate or credentials, the CLI fails
  hard.
- `--live-textrazor` is optional and requires both `--live-providers` and an env
  safety gate. If requested without its env gate or credentials, the CLI fails
  hard.
- If live Gemini is not enabled, `page_similarity` still remains present in
  artifacts and Gemini fields stay populated from deterministic fixtures for
  comparability.
- If live TextRazor is not enabled, live runs skip TextRazor entities entirely.

### Approved remaining slice order

| # | Slice | Status |
|---|-------|--------|
| 1 | **Provider controls** — `--live-gemini`, `--live-textrazor`, env gates, hard validation | **Done** |
| 2 | **Gemini live integration** — `gemini_embeddings.py`, real `gemini-embedding-2` scores when `--live-gemini` | **Remaining** |
| 3 | **TextRazor live selection** — opt-in only via `--live-textrazor` | **Done** |
| 4 | **BGE live integration** — FlagEmbedding reranker behind its own gate | **Remaining** |
| 5 | **Docs and integration pass** — root docs done; `pyproject.toml` extra + Gemini integration tests pending | **In progress** |

**Touchpoints today**

- Scoring entry point: `compute_page_similarity_scores()` in
  `src/seo_rank/similarity.py` (**fixtures only** for all paths today).
- Live Gemini gate: `validate_live_gemini_config()` in `cli.py` runs when
  `--live-gemini` is set but does **not** swap in live embeddings yet.
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

#### Slice A — Gemini embeddings (Gen AI SDK) — **remaining**

**Goal:** When `--live-gemini` is set, live runs call **`gemini-embedding-2`**
via the **`google-genai`** SDK. Offline tests, default live runs, and `--dry-run`
keep fixtures.

**1. Dependency**

```toml
similarity = ["google-genai>=1.0"]
```

Install: `pip install -e ".[similarity,dev]"`.

**2. Environment** (`.env`; loaded by CLI — do not rely on shell exports)

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) API key for local runs |

**3. Model**

Pin **`gemini-embedding-2`** (GA; 8192 input tokens; up to 3072 dims with MRL).
Use `output_dimensionality` when you want fewer dims.

**4. Client** — add `src/seo_rank/gemini_embeddings.py` with injectable backend and
prompt formatters. **`gemini-embedding-2` has no `task_type` param** — task goes
in the input string:

```python
from google import genai
from google.genai.types import EmbedContentConfig

def prepare_query(query: str) -> str:
    return f"task: search result | query: {query}"

def prepare_document(content: str, title: str | None = None) -> str:
    return f"title: {title or 'none'} | text: {content}"

def prepare_semantic_input(text: str) -> str:
    return f"task: sentence similarity | query: {text}"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

vector = client.models.embed_content(
    model="gemini-embedding-2",
    contents=prepare_query(keyword),
    config=EmbedContentConfig(output_dimensionality=3072),
).embeddings[0].values
```

**5. Task formatting** — two scores per page; separate embed calls. Do **not** mix
asymmetric retrieval with symmetric similarity.

| Score | Pattern | Keyword / query side | Page / document side |
|-------|---------|----------------------|----------------------|
| `gemini_doc_retrieval` | Asymmetric **search result** | `task: search result \| query: {keyword}` | `title: {serp_title or none} \| text: {page body}` |
| `gemini_semantic_similarity` | Symmetric **sentence similarity** | `task: sentence similarity \| query: {keyword}` | `task: sentence similarity \| query: {page body}` |

Use **search result** for retrieval only. **Sentence similarity** is for STS
(recommendations, dedup) — not search retrieval. Keep each task consistent across
all inputs for that score.

Cosine similarity on API embeddings; round to 6 decimals. Budget **41 embed calls
per keyword** at depth 20. Overlong inputs: Gemini truncates and normalizes
automatically (8192-token cap). No client-side truncation or re-normalization.

**6. Wire + test**

- Swap fixtures in `build_live_keyword_result()` only when `config.live_gemini`
  is true (gate already validated in `build_live_payload()`).
- Append `genai.embed_content` to `network_calls`.
- Tests first: `test_gemini_embeddings.py` (mock formatted inputs: search-result
  query + title|text doc; sentence-similarity on keyword and page), existing
  fixture tests unchanged, `test_cli_run.py` live-path selection, opt-in
  integration gate.

**Done when:** `--live-gemini` run returns real Gemini scores with
`GEMINI_API_KEY` set; live runs without the flag still use fixtures; offline
pytest stays network-free.

---

#### Slice B — BGE (local cross-encoder) — **remaining**

**Goal:** When BGE live is enabled, replace the `bge` fixture path in live runs
with a real FlagEmbedding **cross-encoder** reranker (not a bi-encoder embed
model). Default live runs keep fixture BGE.

**1. Dependencies**

Add to the same `similarity` extra:

```toml
similarity = ["google-genai>=1.0", "FlagEmbedding>=1.2"]
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

#### Slice C — Shared cleanup — **in progress**

1. **`validate_live_gemini_config()`** — **done** (called when `--live-gemini` is
   set; mirrors DataForSEO/TextRazor hard-fail style).
2. **`pyproject.toml` / integration tests** — **remaining**: add `similarity`
   optional extra; ship opt-in Gemini integration coverage when Slice A lands.
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
- [x] Optional live provider flags (`--live-gemini`, `--live-textrazor`) with
  env gates and hard failures when misconfigured.
- [x] Live TextRazor is opt-in only; default live runs skip entity extraction.
- [x] Documentation and `.env.example` aligned with `ARCHITECTURE.md`,
  `TESTING.md`, `ROADMAP.md`.
- [ ] Live **Gemini Doc Retrieval** and **Gemini Semantic Similarity** via
  Gen AI SDK (`gemini-embedding-2`) when `--live-gemini` is enabled.
- [ ] Live **BGE** cross-encoder via FlagEmbedding with documented model pin
  and score calibration notes.
- [ ] `pyproject.toml` `similarity` optional extra for `google-genai` and
  `FlagEmbedding`.
- [ ] Opt-in integration tests for live Gemini (and BGE when shipped).

## Operating Rules

- Follow `AGENTS.md` and the `$sdlc` skill for every implementation slice.
- Write the failing test first for code-shaped changes.
- Run the narrowest relevant check, then `python -m pytest`, before finishing.
- Delete stale scaffolding when replacing it; no compatibility layers for
  unshipped code.
- Keep slices small enough to review and verify.
