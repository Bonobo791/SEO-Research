<!-- Part of the split roadmap. Index: ROADMAP.md -->

### Phase 5.1 — Live provider failure handling

DataForSEO top-level and task-level failures are logged as warnings and the live
run continues. The failed response is retained in `parquet/raw_responses`; its
empty result is allowed to flow through normalization so the run can finish and
report the affected keyword.

**Root cause (Columbus run, 2026-07-02):** SERP schema allows `result: null`;
`normalize_serp_results()` returns `[]` without checking `status_code`. Runs
before `raise_for_failed_dataforseo_tasks()` (shipped in `74ea7c0`) looped all
keywords and persisted failed payloads. The current `--stored-run` path
resumes from the saved raw lake and existing keyword results, so completed work
survives replay; interrupting mid-run still loses in-RAM SERP + embedding
progress for in-flight refresh work.

**Implemented behavior**

- Log a warning for a failed top-level DataForSEO response.
- Log a warning for each failed task, including endpoint, task index, status,
  and keyword context when available.
- Preserve failed raw responses and continue the keyword loop; a failed SERP
  task produces no SERP rows for that keyword.
- `replay_stored_run` / `expand_stored_run`: CLI `--live-providers`,
  `--live-gemini`, `--live-bge` override stale `run.json` config for execution.

**CLI contract:** a failed DataForSEO task does not by itself change the exit
code. The warning includes `status_code`, endpoint, and `target_keyword` when
known; raw response persistence and the normal completion marker still occur.
Transport and configuration errors remain hard failures.

The preflight/fatal-classifier ideas in the remaining dev slices are deferred
hardening, not the current live-run contract. Related follow-ups are S5-11,
S6-10, and S6-12.

#### Dev slices

**Progress:** 0 of 5 shipped, 5 open.

1. **[ ] Slice 1 — Shared fatal task classifier**
   - Add `dataforseo_task_is_fatal()` / `dataforseo_task_is_success()` in
     `dataforseo.py` (fatal set: `40207`, `40101`, `40102`; extend from
     DataForSEO docs as needed).
   - Wire `raise_for_failed_dataforseo_tasks()` and
     `stored_serp_response_is_usable()` through the shared helper (S6-12).
   - Unit tests in `tests/unit/test_dataforseo_requests.py`.

2. **[ ] Slice 2 — Optional fatal-task policy hardening**
   - If a future policy distinguishes fatal auth/IP responses, keep the current
     warning-and-continue default explicit and add an opt-in abort contract.
   - Preserve the current behavior that failed SERP tasks are retained and the
     keyword loop continues.

3. **[ ] Slice 3 — DataForSEO preflight before multi-keyword loops**
   - Cheap DataForSEO connectivity / auth probe before keyword iteration on
     live `run` and live `stored-run` refresh paths (BGE defer + Gemini preflight:
     Phase 5.2).
   - Clear stderr when IP whitelist is the likely fix (link to DataForSEO API
     access panel).
   - Unit test: probe failure → exit `2` without network keyword loop.

4. **[ ] Slice 4 — Stored-run respects CLI live flags**
   - Pass CLI `RunConfig` into `expand_stored_run`; merge `--live-providers`,
     `--live-gemini`, `--live-bge`, `--live-textrazor` over stored `run.json`
     config for execution.
   - Test: stored `live_providers: false` + CLI `--live-providers` uses live path.

5. **[ ] Slice 5 — Safer stale-SERP raw retention (optional)**
   - On `expand_stored_run` refresh, latest-wins per keyword for `endpoint=serp`
     raw rows; drop retained failed row when refresh succeeds (S6-10).
   - Test: inject stale `40207` parquet row, successful live refresh replaces it.

#### Phase 5.1 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Shared fatal classifier; no drift vs `stored_serp_response_is_usable` | 1 | Open |
| Live expansion / SERP / page_text abort on fatal `status_code` | 2 | Open |
| Crawl-null `page_text` still skips URL without aborting run (S5-11) | 2 | Open |
| Preflight before multi-keyword live loop (DataForSEO) | 3 | Open |
| CLI `--live-*` flags override stored config on replay | 4 | Open |
| Stale failed SERP rows not retained after successful refresh | 5 | Open |

### Phase 5.2 — Live Gemini/BGE fail-fast on empty scoring work

Stop multi-keyword live runs when a keyword produces **no scorable panel rows**
after upstream fetches, instead of logging `gemini embeddings` / `bge scoring`,
burning API calls on empty inputs, or loading GPU models for doomed runs.
Complements Phase 5.1 (DataForSEO fatal task codes); does not replace it.

**Root cause (Columbus run, 2026-07-02):** after SERP denial or all-empty
`page_text`, the keyword loop continued. Progress looked healthy while
`page_similarity` stayed empty. User saw **no Google Cloud billing** because
live Gemini uses **Google AI Studio** (`genai.Client(vertexai=False,
api_key=GEMINI_API_KEY)`), not Vertex/GCP console billing. BGE is **local CUDA**
only — never appears in cloud spend.

**Observed gaps today**

- `compute_gemini_page_similarity_scores()` issues **two keyword embed API calls**
  even when `pages` is empty (doc-retrieval + semantic queries).
- `network_calls` records `genai.embed_content` only when `parsed_pages` is
  non-empty — undercounts actual Gemini calls on empty keywords.
- `prepare_live_run_context()` loads the full BGE reranker before any keyword;
  `compute_bge_page_similarity_scores()` returns `[]` silently when there are no
  valid pages but the run still logs `bge scoring` and advances.
- No abort when SERP returned URLs but **every** `page_text` parse is empty
  (distinct from S5-11 per-URL crawl skip).
- No run-start clarity on **where Gemini bills** (AI Studio vs GCP).

**Primary behavior**

- After each keyword's SERP + `page_text` merge in live mode: if
  `len(parsed_pages) == 0` and the keyword had SERP URLs (or live providers
  were enabled for that keyword), **abort entire run** with exit **2** and a
  message naming `target_keyword`, upstream stage, and likely fix (DataForSEO IP
  whitelist, crawl failures, stale stored replay).
- After similarity merge: if `--live-gemini` and/or `--live-bge` is on but
  `page_similarity` for this keyword is empty while SERP had candidates, abort
  (catches silent embed/rerank failures).
- **Defer BGE model load** until the first keyword with `len(parsed_pages) > 0`
  (or until first keyword passes SERP+page_text gate).
- **Skip Gemini query embeds** when `len(pages) == 0` — do not spend API quota
  on keywords with nothing to score.
- **Accurate `network_calls`:** count each live `embed_content` and BGE
  `compute_score` batch; surface in `run.json` metadata and progress.
- **Run-start billing note** on `--live-gemini`: stderr one-liner that billing
  is Google AI Studio / API key usage, not GCP project billing unless Vertex is
  added later.
- Optional **Gemini embed probe** before multi-keyword loop (reuse connectivity
  script or one cheap embed); abort on `404` / auth errors (FIXUPS S476-13).

**CLI contract:** live `seo-rank run` exits **2** on first keyword with zero
scorable output when live Gemini or BGE is enabled; stderr includes
`target_keyword`, `parsed_pages` count, and whether Gemini/BGE were live.
No partial `run.json` flush on abort mid-loop (same as Phase 5.1).

**Related FIXUPS:** S476-13 (Gemini embed health / model endpoint),
S5-11 (per-URL `page_text` null skip vs keyword-level empty panel abort).

**Depends on:** Phase 5.1 slice 4 (CLI `--live-*` override on stored-run) so
empty-output guards run against the intended live/offline config.

#### Dev slices

**Progress:** 0 of 6 shipped, 6 open.

1. **[ ] Slice 1 — Keyword-level empty panel guard**
   - After `build_live_keyword_result` assembles `parsed_pages`, if live
     providers or live Gemini/BGE and `parsed_pages` empty while SERP had items
     (or expansion included this keyword), raise `CliCommandError` → exit `2`.
   - Unit + CLI tests: SERP ok + all `page_text` empty → abort before Gemini;
     zero SERP rows after successful task → abort (or defer to 5.1 if already
     fatal).

2. **[ ] Slice 2 — Skip wasteful Gemini calls on empty pages**
   - Short-circuit `compute_gemini_page_similarity_scores()` when `pages` is
     empty (no query embeds).
   - Align `network_calls` with actual `embed_content` invocations.
   - Test: empty pages → zero embed calls; N pages → `2 + 4N` calls.

3. **[ ] Slice 3 — Defer BGE load until scorable work exists**
   - Move `load_bge_reranker()` from run start to first keyword with
     `parsed_pages > 0` when `--live-bge`.
   - Test: keyword 1 empty → model not loaded; keyword 1 has pages → load once,
     reuse for keyword 2.

4. **[ ] Slice 4 — Empty similarity output guard**
   - After Gemini/BGE merge, if live scoring enabled and `similarity_scores`
     empty for keyword with non-empty `parsed_pages`, abort exit `2`.
   - Test: mock embed failure → no silent advance to next keyword.

5. **[ ] Slice 5 — Billing clarity and optional Gemini preflight**
   - Stderr banner for `--live-gemini` (AI Studio billing target).
   - Optional cheap embed probe before keyword loop; fail fast on S476-13
     conditions.
   - Document in `README.md` / `TESTING.md` where to check Gemini usage.

6. **[ ] Slice 6 — Stored-run + progress honesty**
   - Progress lines distinguish `similarity (fixture)` vs `gemini embeddings
     (live)` vs skipped (empty panel).
   - Stored-run refresh: apply guards when CLI `--live-gemini` / `--live-bge`
     override stored config (requires 5.1 slice 4).

#### Phase 5.2 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Abort when keyword has SERP URLs but zero `parsed_pages` in live mode | 1 | Open |
| No Gemini query embeds when `pages` is empty | 2 | Open |
| `network_calls` matches actual live embed invocations | 2 | Open |
| BGE model loads only after first scorable keyword | 3 | Open |
| Abort when live scoring yields zero `page_similarity` rows | 4 | Open |
| Run-start Gemini billing note + optional embed preflight | 5 | Open |
| Progress distinguishes fixture vs live vs skipped | 6 | Open |

### Phase 5.4 — Exploratory extensions (deferred)

- Rank-decile segments (ranks 1–3 vs 4–10 vs 11–20).
- Keyword heterogeneity deep-dives (decision C): per-keyword slopes as
  exploratory only, separate BH family if promoted to confirmatory.
- Random 20% keyword holdout for confirmatory pass — **Phase 5.6** (slice 5).
- LOWESS / CCPR diagnostic plots as optional artifacts.

### Phase 5.5 - Analysis Expansion

- Per keyword: top-20 SERP; passage and domain URL scoring vs target
  keyword; domain URL cap 1000; skip domains over 1000 URLs
