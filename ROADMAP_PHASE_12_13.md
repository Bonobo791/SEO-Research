# Phase 12 — Temporal Panel (the bottleneck: a clock, not code)

Runs today are isolated snapshots; nothing connects the same
`(keyword, URL)` across time. This phase turns repeated runs into a
longitudinal panel and adds the lead-lag and difference-in-differences
machinery that separates a *live* signal from a static artifact. **Start the
recurring collection immediately** — the validation timeline is bounded by
data accumulation (content updates take ~1 month to show rank effects, new
pages 3–5 months), not by engineering.

**Primary decision (v1):** a `panel` mart keyed `(target_keyword_id,
canonical_url_hash, snapshot_date)`, materialized by joining across run trees
on overlapping keywords. Each row carries the full Phase 5 feature set plus
the Phase 10–11 vector-derived metrics, versioned by `snapshot_date`. The
`--stored-run` replay machinery already makes re-collection idempotent; a
scheduler (cron / CI schedule) triggers a fresh run on a fixed keyword set on
a fixed cadence (weekly SERP + embeddings; monthly full re-embed).

**Lead-lag:** `panel_leadlag` table pairs `Δmetric(t → t+1)` with
`Δrank(t+1 → t+2)` per page-keyword, with lag windows matched to the
documented effect latencies (4–6 weeks for refreshes, 12+ weeks for new
pages). **DiD:** a `treatment_log` (you record your own content changes:
publish / refresh / consolidate / prune, with date and target pages) drives a
difference-in-differences estimate — treated pages' rank change minus matched
unchanged pages' change over the same window — expressible in the existing
pooled-OLS-with-FE machinery.

**Guardrails:** metrics are only comparable within a pinned embedding model —
a model upgrade forces a full re-embed of the archive and a `model_version`
break in the panel (never bridge across it silently); SERP rows are
geo-pinned and de-personalized so Δrank reflects the algorithm, not
measurement noise.

**Out of scope for 12:** predictive modeling on the panel (Phase 13),
behavioral/GSC feed (deferred — account-gated).

#### Dev slices

**Progress:** 0 of 8 shipped.

1. **[ ] Slice 1 — Panel schema + cross-run join**
   - `data/panel.py`: scan multiple run trees, join on
     `(target_keyword_id, canonical_url_hash)`, emit `snapshot_date` rows.
   - Tests: two synthetic runs with overlapping keywords → one panel row per
     page per date.

2. **[ ] Slice 2 — Recurring-run scheduler contract**
   - Fixed keyword set config; idempotent re-collection via `--stored-run`;
     `run.json` records `schedule_id` and `snapshot_date`.
   - Tests: replay of a scheduled run produces the same panel keys.

3. **[ ] Slice 3 — Δmetric / Δrank computation**
   - Per page-keyword, diff consecutive snapshots for every registered
     feature + vector metric.
   - Tests: planted metric change appears with correct sign and timing.

4. **[ ] Slice 4 — Lead-lag tables**
   - `panel_leadlag` with configurable lag windows (default 4–6 / 12+ weeks).
   - Tests: lag-window assignment correctness.

5. **[ ] Slice 5 — Treatment log data model**
   - `treatment_log` schema (date, action, target pages/keywords, optional
     predicted delta); manual-entry interface (CLI or YAML).
   - Tests: schema validation; join to panel.

6. **[ ] Slice 6 — Difference-in-differences estimation**
   - Treated vs matched-control rank change; OLS-with-FE implementation;
     clustered SEs.
   - Tests: synthetic treated group with a known effect recovers it.

7. **[ ] Slice 7 — Model-version break guard**
   - `model_version` on the panel; cross-version bridging raises/splits.
   - Tests: mixed-model panel refuses pooled Δ computation.

8. **[ ] Slice 8 — Golden fixture + regression**
   - A 3-snapshot synthetic panel with a planted treatment effect; assert
     lead-lag and DiD recover it.

#### Phase 12 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| `panel` mart joins the same page-keyword across run trees | 1 | Open |
| Recurring runs are idempotent and produce stable panel keys | 2 | Open |
| Δmetric/Δrank computed per page-keyword across snapshots | 3 | Open |
| Lead-lag tables respect effect-latency windows | 4 | Open |
| Treatment log validated and joined to the panel | 5 | Open |
| DiD recovers a planted treatment effect | 6, 8 | Open |
| Model-version breaks prevent silent cross-model comparison | 7 | Open |

---

# Phase 13 — Predictive & Universe Layer

Turn the (now temporal) feature set into a validated predictor and a
controllable simulation. Two halves: **(13a) the bake-off** that answers
"what's the correct model" under out-of-time validation with formal ablation,
and **(13b) the universe** — a shared embedding space of queries, pages, and
site centroids that you perturb to simulate ranking changes. 13a is the
validation gate; 13b is only trustworthy once 13a passes.

**Primary decision (13a):** candidate models evaluated on **out-of-time
NDCG@10** — train on earlier snapshots, score held-out *future* SERPs, per
query, averaged (the production LTR evaluation standard; your Phase 5.6
time-split slice is the seed). Candidates, in increasing complexity: (a) a
**linear force model** (`w_sem·cos(q,p) + w_auth·authority + w_site·site_fit
+ w_beh·ctr_delta`, weights fitted); (b) a **gradient-boosted classifier**
(top-10 probability, HistGradientBoosting/LightGBM); (c) **LambdaMART**
(lambdarank objective — statistically adjacent to your Plackett-Luce work);
(d) a **feature-free cosine baseline** (raw query·page cosine only) as the
null every other model must beat. **Ablation:** retrain the winner minus
`site_fit`, minus `radius`; the NDCG cost (paired bootstrap over queries) is
the definitive answer to "do the centroid terms even matter." Selection rule:
adopt the simplest model that beats the baseline out-of-time, passes ablation
for the features you intend to intervene on, and is calibrated (predicted
top-10 probabilities match realized frequencies in deciles).

**Primary decision (13b):** a `universe` module — nodes
(query/page/site-centroid) in one shared space; typed forces (semantic,
site-membership, link authority via PageRank, behavioral proxy); a SERP as a
computed readout `sorted(score(q,p))`; and `simulate(query, intervention)`
that runs a SERP, applies a change (publish / refresh / consolidate / add a
link), re-runs, and returns rank diffs. Force weights come from the 13a
winner. **Honest ceiling (documented in limitations):** the behavioral term
for competitors defaults to zero (you can only observe your own CTR), so the
universe predicts *direction and relative magnitude* for the topical/authority
components — never exact positions.

**Guardrails:** rolling-forward validation only (never random splits — they
leak query-level patterns); a model whose out-of-time NDCG collapses in the
fold after a core update flags a regime change and is not trusted for
prediction until refit; every universe prediction is logged with its
assumptions and date so it can be scored against realized outcomes.

**Out of scope for 13:** real-time serving, the behavioral/GSC feed
(deferred — account-gated; when added it becomes the `w_beh` term for your
own pages), any claim of exact-position prediction.

#### Dev slices

**Progress:** 0 of 10 shipped.

1. **[ ] Slice 1 — Out-of-time evaluation harness**
   - `stats/evaluate.py`: rolling-forward splits on the Phase 12 panel;
     NDCG@k per query; top-10 AUC; paired keyword bootstrap CIs.
   - Tests: synthetic panel with known ordering → correct NDCG; bootstrap CI
     coverage.

2. **[ ] Slice 2 — Feature-free cosine baseline**
   - The null model every candidate must beat.
   - Tests: baseline NDCG computed and recorded.

3. **[ ] Slice 3 — Linear force model**
   - Fit `w_sem…w_beh` by regression on the panel.
   - Tests: weights recovered from a synthetic panel with known ground truth.

4. **[ ] Slice 4 — Gradient-boosted classifier**
   - Top-10 probability; same features + controls.
   - Tests: out-of-time AUC reported per fold.

5. **[ ] Slice 5 — LambdaMART ranker**
   - Lambdarank objective; per-query grouping.
   - Tests: NDCG@10 on held-out queries.

6. **[ ] Slice 6 — Ablation studies**
   - Retrain the winner minus `site_fit`, minus `radius`; paired bootstrap on
     the NDCG difference.
   - Tests: ablation cost with CI; `adds_value` verdict.

7. **[ ] Slice 7 — Calibration + model selection**
   - Decile calibration of predicted probabilities; selection rule applied;
     chosen model persisted with its feature list and weights.
   - Tests: calibration table; selection respects the rule.

8. **[ ] Slice 8 — Universe module**
   - `universe/`: nodes, typed forces, PageRank authority, `simulate()`.
   - Tests: golden synthetic universe — planted off-topic page ranks last;
     in-topic draft strengthens focus; refresh flips a near-tied pair.

9. **[ ] Slice 9 — Prediction logging + prospective scoring**
   - Every intervention prediction logged with date/assumptions; scored
     against realized SERPs after the effect window.
   - Tests: log schema; prospective accuracy computed.

10. **[ ] Slice 10 — Golden fixtures + docs**
    - End-to-end synthetic universe with known interventions; limitations
      text (mechanism model, behavioral ceiling, not Google's literal scores).

#### Phase 13 acceptance criteria

| Acceptance item | Slice(s) | Status |
| --------------- | -------- | ------ |
| Rolling-forward NDCG@10 harness with keyword bootstrap CIs | 1 | Open |
| Feature-free baseline recorded as the null to beat | 2 | Open |
| All four candidates evaluated out-of-time on the panel | 3–5 | Open |
| Ablation proves (or disproves) centroid-feature value with NDCG cost | 6 | Open |
| Model selected by the simplest-calibrated rule and persisted | 7 | Open |
| Universe reproduces known interventions in a golden fixture | 8, 10 | Open |
| Predictions logged and scored prospectively | 9 | Open |
