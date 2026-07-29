<!--
SEO Research — SEO Factors Research Tool
Copyright (C) 2026 Andrew Philip Weilbacher

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md
-->
# PAGE_TEXT_RETRIEVAL_PLAN.md


**Status: shipped (2026-07).** All four slices are implemented. This file is the
historical contract and acceptance record, not an open backlog item.

No new CLI command or flag. Existing raw provider responses remain the
diagnostic source of truth. Normalization and scoring eligibility are unchanged:
only the winning (or final attempted) `content_parsing/live` response is retained
per URL.

## Summary

Live and stored-run page-text fetching classify each validated DataForSEO
`content_parsing/live` response, checkpoint each final per-URL response to the
raw lake, escalate rendering only when content is empty or JavaScript-disabled,
recover once from task timeouts and pool-related failures, and on
`--stored-run --live-providers` re-fetch every non-usable stored row.
Fresh live runs bootstrap an atomic manifest and checkpoint keyword expansion
and SERP responses before page-text collection, so an interrupted first run can
also resume in place.

## Slice 1 — Content outcome contract (shipped)

Private classifier `classify_page_text_response(response) -> str` in
`dataforseo.py`. Precedence:

1. `timeout` — any task `status_code == 50402` or `crawl_status == "timeout"`
2. `pool_related` — task `status_message` or result `crawl_status` contains
   access denied, forbidden, location, geo, or unreachable
3. `javascript_disabled` — structured `page_content` or `page_as_markdown`
   contains `javascript is disabled` (not arbitrary raw HTML)
4. `usable` — `parsed_page_text_details()` yields non-blank text or `raw_html`
5. `empty` — successful `20000` / Ok with no usable text/HTML
6. `provider_failure` — any remaining non-success task state

`20000` / Ok is transport success only; it never implies usable.
`page_text_response_is_pool_related()` is separate so pool recovery can still
run when classification prefers `timeout`.

Tests: `tests/unit/test_dataforseo_requests.py` (`test_classify_page_text_*`).

## Slice 2 — Staged live retrieval (shipped)

Shared path `fetch_page_text_for_urls()` (fresh runs and stored-run resume):

1. Baseline — `enable_javascript=False`, `enable_browser_rendering=False`
2. JavaScript/XHR — JS on, browser rendering off
3. Browser — JS and browser rendering on

Return immediately on any outcome other than `empty` or `javascript_disabled`.
`build_page_text_request()` accepts the two rendering flags plus optional
`switch_pool`; defaults remain the fixed US English desktop contract
(`ip_pool_for_scan=us`, `accept_language=en-US`, `store_raw_html=true`,
`browser_preset=desktop`). Locale still does not follow `--location` /
`--language`.

Tests: `tests/unit/test_cli_run.py` (`test_fetch_page_text_for_urls_*` stage
coverage) and request-builder tests in `test_dataforseo_requests.py`.

## Slice 3 — Failure recovery (shipped)

- Each stage attempt goes through
  `execute_validated_dataforseo_request_with_timeout_retry()`: on task-level
  `50402`, wait one second and retry once; only the final response is kept.
- After that attempt, if `page_text_response_is_pool_related()`, issue one
  additional same-rendering request with `switch_pool=True` (also timeout-retried).
- Timeouts are not domain-blocklisted; unreachable client errors still record on
  the domain blocklist as before.

Tests: timeout retry, pool switch, and stage-after-switched-empty coverage in
`test_cli_run.py`.

## Slice 4 — Automatic stored-run backfill (shipped)

During `run --stored-run --live-providers`, inspect stored `page_text`
responses with `classify_page_text_response()`. Keep `usable` rows and
re-fetch every other outcome through the existing staged page-text fetcher.
No CLI flag, raw schema, or normalization contract changes.

### Replay behavior

- The stored-run CLI live-provider overlay applies even when the saved run was
  created offline.
- A latest fetched response replaces the stored non-usable row, including a
  final response that remains non-usable. If a blocked URL returns no response,
  retain its existing diagnostic row.
- Cached similarity and TextRazor rows are content-derived. Replacing page text
  invalidates both for that URL: similarity features and scores are recomputed,
  while stale TextRazor rows are dropped or regenerated when
  `--live-textrazor` is active.
- The fetcher checkpoints final fetched responses on normal completion and in
  atomic per-response writes before a later URL failure or Ctrl-C can discard
  them;
  `write_artifacts()` later rewrites the page-text raw partition from the
  rebuilt payload, then the existing replay chain re-materializes curated
  tables, feature marts, `analysis_mart`, and stats.
- Raw response identity uses `cache_identity_url()`. A usable response wins
  over a stale non-usable tracked-URL variant during replay; otherwise the
  newest response wins.

### Billing and validation

- This may issue billable DataForSEO page-text requests only for non-usable
  rows. Empty or JavaScript-disabled content can advance through all rendering
  stages; timeout retries and pool switching can add requests. A later replay
  retries any row that remains non-usable. Enabled live Gemini or TextRazor
  regeneration can add provider cost; BGE regeneration adds local compute work.
- Unit coverage proves usable rows are not requested and stale rows are
  replaced (`test_build_resumed_keyword_result_refetches_nonusable_stored_page_text`,
  `test_run_stored_run_live_providers_refetches_nonusable_page_text_in_place`).
  Keep live verification opt-in.

## Assumptions (unchanged)

- Attempt-by-attempt persistence is out of scope; only the winning/final
  response is checkpointed per URL. A completed checkpoint is fsynced and
  atomically replaces the prior partition file; a response interrupted before
  that checkpoint begins cannot be recovered.
- File path: `PAGE_TEXT_RETRIEVAL_PLAN.md`.
