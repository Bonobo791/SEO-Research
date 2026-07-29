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
# Entity-Signal Mart Implementation Plan


## Summary

Implement an automatic extension of the existing TextRazor analysis pipeline.
Build a separate long-form `entity_signals` mart from stored
`parquet/entities`, then produce per-entity statistical results in
`entity_stats.parquet`, with compact JSON and Markdown summaries.

## Data model and eligibility

- One page-level row per `target_keyword_id × canonical_url_hash × entity_id`.
- Preserve `entity_id`, deduplicated `matched_texts`, deduplicated
  `entity_types`, exact `url`, `canonical_url_hash`, keyword metadata,
  `serp_rank`, presence, mention count, mean confidence, and mean relevance.
- Group only by `entity_id`; retain matched text and types as provenance.
- Exclude blocklisted URLs.
- Treat pages without a usable TextRazor entity response as unknown and exclude
  them from that entity's analysis.
- Require at least 10 distinct present pages across at least 3 distinct
  keywords.
- Compare each entity only within keywords where it appears, including present
  and absent usable pages.
- Do not impose a hard cap on eligible entities.

## Statistical analysis

- Keep `entity_signals` separate from the wide `analysis_mart`.
- Primary signal: `entity_present`.
- Secondary signals: `entity_mention_count`, `entity_confidence_mean`, and
  `entity_relevance_mean`.
- Reuse keyword-level Spearman and pooled keyword-fixed-effect OLS, plus
  existing diagnostics and rank-depth conventions where estimable.
- Analyze confidence/relevance only on present pages; absent values remain
  `null`.
- Mark results `significant`, `non-significant`, `underpowered`, or
  `non-estimable`.
- Entities with fewer than 10 usable keywords retain descriptive results and
  raw p-values but receive no BH inferential claim.
- Apply Benjamini–Hochberg separately for each metric.
- Document that the model outcome is `-log(rank)`, so ranking interpretation is
  inverse: lower SERP rank numbers represent better rankings.

## Outputs and CLI

- Build and validate `entity_signals` during normal `build-features` and
  `analyze` execution; empty entity input produces an empty validated mart.
- Write typed per-entity results to `entity_stats.parquet`.
- Add entity summaries to `stats_summary.json` and `stats_report.md`.
- Analyze all eligible entities by default.
- Add repeatable filtering by canonical ID:

  ```text
  --entity-id ENTITY_A --entity-id ENTITY_B
  ```

- Include every eligible entity in detailed results, with raw coefficients and
  the `-log(rank)` interpretation note rather than directional ranking labels.
- Show up to three deterministic provenance examples per entity, ordered by
  best SERP rank, keyword, then URL; include entity ID, URL, and matched text.
- Include entity signals in combined-run analysis and recalculate eligibility
  and statistics after merging, using existing last-run-wins keyword ownership.

## Implementation areas

- `src/seo_rank/data/features.py`: mart construction, lazy joins, blocklist
  filtering, schemas, validation, and writes.
- `src/seo_rank/stats/`: entity-specific analysis, correction, statuses, and
  Parquet artifacts.
- `analysis_spec.v1.yaml` and CLI handling: thresholds, metrics, correction
  policy, and repeatable `--entity-id` filtering.
- Keep existing entity normalization as the detailed occurrence-level source
  of truth; do not add snippet extraction.

## Tests and acceptance criteria

- Multiple mentions aggregate correctly without overweighting pages.
- All matched texts and entity types are preserved.
- Exact URL and canonical hash are retained.
- Absent pages receive presence/count zero and null confidence/relevance.
- Missing TextRazor responses are excluded, not treated as absence.
- Blocklisted URLs are excluded.
- Eligibility uses distinct present pages and keywords.
- Synthetic tests verify Spearman/OLS effect direction.
- Non-estimable, underpowered, filtering, BH, and combined-run cases are
  covered.
- `entity_stats.parquet`, `stats_summary.json`, and `stats_report.md` agree.
- Full test suite passes.

## Assumptions

- No feature flag or new dependency is required.
- Existing runs are regenerated with
  `seo-rank build-features --run RUN_DIR`; no migration utility is added.
- This is active implementation scope, not deferred backlog work.

## Review follow-up bugs

- **[x] P1 — Distinct-page eligibility:** eligibility must count distinct
  `target_keyword_id × canonical_url_hash` present pages, not raw rows, so
  duplicate rows cannot satisfy the 10-page threshold.
- **[x] P1 — Underpowered descriptive results:** entities below eligibility or
  inference support still need estimable Spearman and OLS descriptive results
  plus raw p-values; only BH claims are withheld.
- **[x] P2 — Report provenance:** every rendered entity example must include its
  source URL and matched text, not the URL alone.

<!-- randomized-text: blue comets fold into a paper garden c37b92fd16af77d7 -->
