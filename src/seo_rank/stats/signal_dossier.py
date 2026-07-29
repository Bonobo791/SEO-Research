"""Exploratory signal factor vs proxy dossier (Phase 5.6)."""
# SEO Research — SEO Factors Research Tool
# Copyright (C) 2026 Andrew Philip Weilbacher
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md


from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.formula.api as smf
from scipy import stats

from seo_rank.data.scans import scan_curated_table
from seo_rank.stats.panel import build_limitations_for_rank_depth, load_analysis_panel
from seo_rank.stats.rank_depth import filter_panel_by_max_rank
from seo_rank.stats.spec import AnalysisSpec, load_analysis_spec

logger = logging.getLogger(__name__)

CHAR_DENSITY_COLUMN = "textrazor_unique_entity_density_per_1k_chars"

DOSSIER_CANDIDATE_REGISTRY: tuple[tuple[str, str], ...] = (
    ("entity_confidence", "textrazor_entity_confidence_score"),
    ("entity_relevance", "textrazor_entity_relevance_score"),
    ("entailment_score", "textrazor_entailment_score"),
    ("relation_count", "textrazor_relation_count"),
    ("property_count", "textrazor_property_count"),
    ("entity_mention_count", "textrazor_entity_mention_count"),
    ("unique_entity_count", "textrazor_unique_entity_count"),
    ("unique_entity_density_per_1k_words", "textrazor_unique_entity_density_per_1k_words"),
    ("entity_mention_density_per_1k_words", "textrazor_entity_mention_density_per_1k_words"),
    ("unique_entity_density_per_1k_chars", CHAR_DENSITY_COLUMN),
)

DOSSIER_CANDIDATE_COLUMNS: tuple[str, ...] = tuple(
    column for _, column in DOSSIER_CANDIDATE_REGISTRY
)

_PERSISTED_DOSSIER_COLUMNS: tuple[str, ...] = tuple(
    column for column in DOSSIER_CANDIDATE_COLUMNS if column != CHAR_DENSITY_COLUMN
)

_DENSITY_COLUMNS: tuple[str, ...] = (
    "textrazor_entity_mention_count",
    "textrazor_unique_entity_count",
    "textrazor_unique_entity_density_per_1k_words",
    "textrazor_entity_mention_density_per_1k_words",
    CHAR_DENSITY_COLUMN,
)

_PROXY_EXPECTATION_BY_COLUMN: dict[str, str] = {
    "textrazor_entity_mention_count": "raw_count",
    "textrazor_unique_entity_count": "raw_count",
    "textrazor_relation_count": "raw_count",
    "textrazor_property_count": "raw_count",
    "textrazor_unique_entity_density_per_1k_words": "word_density",
    "textrazor_entity_mention_density_per_1k_words": "word_density",
    CHAR_DENSITY_COLUMN: "char_density",
}


def derive_char_density(frame: pl.DataFrame) -> pl.DataFrame:
    """Derive unique-entity density per 1k characters from panel columns."""

    if (
        "textrazor_unique_entity_count" not in frame.columns
        or "page_text_length" not in frame.columns
    ):
        return frame.with_columns(pl.lit(None).cast(pl.Float64).alias(CHAR_DENSITY_COLUMN))

    return frame.with_columns(
        pl.when(
            pl.col("textrazor_unique_entity_count").is_not_null()
            & pl.col("page_text_length").is_not_null()
            & (pl.col("page_text_length") > 0)
        )
        .then(
            pl.col("textrazor_unique_entity_count").cast(pl.Float64)
            * 1000.0
            / pl.col("page_text_length").cast(pl.Float64)
        )
        .otherwise(None)
        .alias(CHAR_DENSITY_COLUMN)
    )


def load_dossier_panel(
    run_dir: Path,
    *,
    rank_depth: str | None = None,
    spec: AnalysisSpec | None = None,
) -> tuple[pl.DataFrame, str, dict[str, str], AnalysisSpec]:
    """Load analysis_mart joined to dossier TextRazor columns at a rank depth."""

    analysis_spec = spec or load_analysis_spec()
    depth_key = rank_depth or analysis_spec.primary_rank_depth
    panel_result = load_analysis_panel(run_dir, spec=analysis_spec)
    analysis_mart = panel_result.analysis_mart
    textrazor_path = Path(run_dir) / "parquet" / "textrazor_page_metrics"
    if textrazor_path.exists():
        try:
            textrazor = scan_curated_table(run_dir, "textrazor_page_metrics").collect()
        except OSError:
            textrazor = pl.DataFrame()
    else:
        textrazor = pl.DataFrame()

    join_keys = ["run_id", "target_keyword_id", "canonical_url_hash"]
    if textrazor.is_empty():
        merged = analysis_mart.with_columns(
            [pl.lit(None).alias(column) for column in _PERSISTED_DOSSIER_COLUMNS]
        )
    else:
        available = [
            column
            for column in _PERSISTED_DOSSIER_COLUMNS
            if column in textrazor.columns
        ]
        missing = [
            column
            for column in _PERSISTED_DOSSIER_COLUMNS
            if column not in textrazor.columns
        ]
        selected = [*join_keys, *available]
        selected = [column for column in selected if column in textrazor.columns]
        # Deduplicate while preserving order.
        seen: set[str] = set()
        selected_unique: list[str] = []
        for column in selected:
            if column not in seen:
                seen.add(column)
                selected_unique.append(column)
        merged = analysis_mart.join(
            textrazor.select(selected_unique),
            on=join_keys,
            how="left",
        )
        if missing:
            merged = merged.with_columns(
                [pl.lit(None).alias(column) for column in missing]
            )

    merged = derive_char_density(merged)
    max_rank = analysis_spec.rank_depth_limit(depth_key)
    filtered = filter_panel_by_max_rank(merged, max_rank=max_rank)
    limitations = build_limitations_for_rank_depth(analysis_spec, depth_key)
    limitations = {
        **limitations,
        "exploratory_dossier": (
            "Signal factor dossier metrics are exploratory appendix only; "
            "they are not confirmatory Phase 5 estimands."
        ),
        "word_vs_char_denominator": (
            "Word-normalized densities use textrazor_word_count; "
            "char-normalized density uses page_text_length and is derived at panel load."
        ),
    }
    logger.info(
        "loaded dossier panel run_dir=%s depth=%s rows=%d",
        run_dir,
        depth_key,
        filtered.height,
    )
    return filtered, depth_key, limitations, analysis_spec


def build_signal_factor_report(
    panel: pl.DataFrame,
    *,
    run_id: str,
    rank_depth: str,
    limitations: Mapping[str, str],
    spec: AnalysisSpec | None = None,
    ndcg_k: int = 10,
    holdout_fraction: float | None = None,
    holdout_seed: int = 0,
    compare_panel: pl.DataFrame | None = None,
) -> dict[str, Any]:
    """Build the exploratory signal_factor_report.json envelope."""

    del spec  # reserved for future estimand metadata
    candidates = tuple(
        column for column in DOSSIER_CANDIDATE_COLUMNS if column in panel.columns
    )
    keyword_ids = (
        panel["target_keyword_id"].unique().to_list()
        if "target_keyword_id" in panel.columns and not panel.is_empty()
        else []
    )
    keyword_count = len(keyword_ids)

    report: dict[str, Any] = {
        "status": "exploratory",
        "run_id": run_id,
        "rank_depth": rank_depth,
        "keyword_count": keyword_count,
        "row_count": panel.height,
        "candidates": {
            "registry": [
                {"label": label, "column": column}
                for label, column in DOSSIER_CANDIDATE_REGISTRY
            ],
            "columns": list(candidates),
        },
        "density": {
            "columns": list(_DENSITY_COLUMNS),
            "notes": {
                "word_vs_char_denominator": limitations.get(
                    "word_vs_char_denominator",
                    "Word densities use textrazor_word_count; char density uses page_text_length.",
                ),
                "proxy_expectations": {
                    "raw_count": (
                        "High Δ adjusted R² after length step; often collapses after BGE."
                    ),
                    "word_density": (
                        "Smaller length-step gain; may still collapse after BGE if tracking relevance."
                    ),
                    "char_density": (
                        "Same-length bins should show more stable association than raw counts "
                        "when density is real."
                    ),
                },
            },
        },
        "ndcg": ndcg_at_k_for_signals(panel, columns=candidates, k=ndcg_k),
        "incremental_ols": incremental_ols_ladder(panel, candidates=candidates),
        "partial_correlation": partial_correlation_block(panel, candidates=candidates),
        "subsets": subset_retests(panel, candidates=candidates),
        "loko": leave_one_keyword_out(panel, candidates=candidates),
        "negative_controls": negative_control_permutation(panel, candidates=candidates),
        "rank_deciles": rank_decile_slices(panel, candidates=candidates),
        "limitations": dict(limitations),
    }

    if holdout_fraction is not None:
        split = keyword_holdout_split(
            [str(value) for value in keyword_ids],
            holdout_fraction=holdout_fraction,
            seed=holdout_seed,
        )
        train_panel = panel.filter(pl.col("target_keyword_id").is_in(split["train"]))
        holdout_panel = panel.filter(pl.col("target_keyword_id").is_in(split["holdout"]))
        report["holdout"] = {
            "fraction": holdout_fraction,
            "seed": holdout_seed,
            "train_keywords": split["train"],
            "holdout_keywords": split["holdout"],
            "train": _holdout_metrics(train_panel, candidates=candidates, ndcg_k=ndcg_k),
            "holdout": _holdout_metrics(
                holdout_panel, candidates=candidates, ndcg_k=ndcg_k
            ),
        }

    if compare_panel is not None:
        report["time_split"] = time_split_overlap(
            panel, compare_panel, candidates=candidates, ndcg_k=ndcg_k
        )

    return report


def ndcg_at_k_for_signals(
    panel: pl.DataFrame,
    *,
    columns: Sequence[str],
    k: int = 10,
    group_column: str = "target_keyword_id",
) -> dict[str, Any]:
    """Macro NDCG@k treating each signal as a relevance score (higher = better)."""

    signals: dict[str, Any] = {}
    if panel.is_empty() or group_column not in panel.columns or "serp_rank" not in panel.columns:
        return {"k": k, "signals": signals}

    work = panel.to_pandas()
    for column in columns:
        if column not in work.columns:
            signals[column] = {
                "macro_mean": None,
                "macro_median": None,
                "keyword_count": 0,
                "status": "missing_column",
            }
            continue
        scores: list[float] = []
        for _, group in work.groupby(group_column, sort=False):
            usable = group.dropna(subset=[column, "serp_rank"])
            if len(usable) < 2:
                continue
            score = _ndcg_at_k(
                relevance=(usable["serp_rank"].max() + 1 - usable["serp_rank"]).to_numpy(
                    dtype=float
                ),
                scores=usable[column].to_numpy(dtype=float),
                k=k,
            )
            if score is not None:
                scores.append(score)
        if not scores:
            signals[column] = {
                "macro_mean": None,
                "macro_median": None,
                "keyword_count": 0,
                "status": "insufficient_data",
            }
            continue
        signals[column] = {
            "macro_mean": float(np.mean(scores)),
            "macro_median": float(np.median(scores)),
            "keyword_count": len(scores),
            "status": "computed",
        }
    return {"k": k, "signals": signals}


def incremental_ols_ladder(
    panel: pl.DataFrame,
    *,
    candidates: Sequence[str],
) -> dict[str, Any]:
    """Pooled OLS ladder: baseline → length → BGE → candidate."""

    required = (
        "serp_rank",
        "target_keyword_id",
        "site_scale",
        "authority_proxy",
        "page_text_length",
        "bge_normalized_score",
    )
    if panel.is_empty() or any(column not in panel.columns for column in required):
        return {"status": "skipped", "reason": "missing_required_columns", "candidates": {}}

    frame = panel.select([*required, *[c for c in candidates if c in panel.columns]]).drop_nulls(
        subset=list(required)
    )
    if frame.height < 4:
        return {"status": "skipped", "reason": "insufficient_rows", "candidates": {}}

    work = frame.to_pandas()
    work["outcome"] = -np.log(work["serp_rank"].astype(float))
    work["log_page_text_length"] = np.log(work["page_text_length"].astype(float) + 1.0)
    keyword_count = int(work["target_keyword_id"].nunique())
    use_cluster = keyword_count >= 2

    baseline_formula = "outcome ~ site_scale + authority_proxy + C(target_keyword_id)"
    length_formula = baseline_formula + " + log_page_text_length"
    bge_formula = length_formula + " + bge_normalized_score"

    baseline_fit = _fit_ols(work, baseline_formula, use_cluster=use_cluster)
    length_fit = _fit_ols(work, length_formula, use_cluster=use_cluster)
    bge_fit = _fit_ols(work, bge_formula, use_cluster=use_cluster)

    results: dict[str, Any] = {}
    for column in candidates:
        if column not in work.columns:
            continue
        candidate_work = work.dropna(subset=[column]).copy()
        if candidate_work.empty:
            continue
        candidate_formula = bge_formula + f" + {column}"
        # Refit shared rungs on the candidate complete-case subset.
        cand_baseline = _fit_ols(candidate_work, baseline_formula, use_cluster=use_cluster)
        cand_length = _fit_ols(candidate_work, length_formula, use_cluster=use_cluster)
        cand_bge = _fit_ols(candidate_work, bge_formula, use_cluster=use_cluster)
        cand_full = _fit_ols(candidate_work, candidate_formula, use_cluster=use_cluster)
        rungs = {
            "baseline": cand_baseline,
            "plus_length": {
                **cand_length,
                "delta_adj_r2_vs_previous": _delta_adj_r2(cand_length, cand_baseline),
            },
            "plus_bge": {
                **cand_bge,
                "delta_adj_r2_vs_previous": _delta_adj_r2(cand_bge, cand_length),
            },
            "plus_candidate": {
                **cand_full,
                "delta_adj_r2_vs_previous": _delta_adj_r2(cand_full, cand_bge),
                "candidate_coefficient": cand_full.get("coefficients", {}).get(column),
                "candidate_p_value": cand_full.get("p_values", {}).get(column),
            },
        }
        results[column] = {
            "proxy_expectation": _PROXY_EXPECTATION_BY_COLUMN.get(column, "scalar"),
            "rungs": rungs,
            "row_count": int(len(candidate_work)),
            "keyword_count": int(candidate_work["target_keyword_id"].nunique()),
        }

    return {
        "status": "computed",
        "shared_rungs": {
            "baseline": baseline_fit,
            "plus_length": {
                **length_fit,
                "delta_adj_r2_vs_previous": _delta_adj_r2(length_fit, baseline_fit),
            },
            "plus_bge": {
                **bge_fit,
                "delta_adj_r2_vs_previous": _delta_adj_r2(bge_fit, length_fit),
            },
        },
        "candidates": results,
    }


def partial_correlation_block(
    panel: pl.DataFrame,
    *,
    candidates: Sequence[str],
) -> dict[str, Any]:
    """Partial correlation of candidates vs rank controlling for BGE (± length)."""

    results: dict[str, Any] = {}
    if panel.is_empty() or "serp_rank" not in panel.columns:
        return {"candidates": results}

    work = panel.to_pandas()
    for column in candidates:
        if column not in work.columns:
            continue
        pooled = _partial_rho(
            work,
            column=column,
            controls=("bge_normalized_score",),
        )
        pooled_length = _partial_rho(
            work,
            column=column,
            controls=("bge_normalized_score", "page_text_length"),
        )
        within: list[float] = []
        if "target_keyword_id" in work.columns:
            for _, group in work.groupby("target_keyword_id", sort=False):
                rho = _partial_rho(
                    group,
                    column=column,
                    controls=("bge_normalized_score",),
                )
                if rho is not None:
                    within.append(rho)
        results[column] = {
            "pooled_partial_rho": pooled,
            "pooled_partial_rho_controlling_length": pooled_length,
            "within_keyword_median_partial_rho": (
                float(np.median(within)) if within else None
            ),
            "within_keyword_count": len(within),
        }
    return {"candidates": results}


def subset_retests(
    panel: pl.DataFrame,
    *,
    candidates: Sequence[str],
) -> dict[str, Any]:
    """Same-length, same-similarity, and deprecated-tag subset Spearman re-tests."""

    out: dict[str, Any] = {
        "same_length": {},
        "same_similarity": {},
        "deprecated_html_tags": {},
    }
    if panel.is_empty():
        return out

    work = panel.to_pandas()
    if "page_text_length" in work.columns:
        work["length_bin"] = pd.qcut(
            work["page_text_length"].rank(method="first"),
            q=min(3, max(1, work["page_text_length"].nunique())),
            duplicates="drop",
        )
        out["same_length"] = _spearman_by_group(work, "length_bin", candidates)
    if "bge_normalized_score" in work.columns:
        work["similarity_bin"] = pd.qcut(
            work["bge_normalized_score"].rank(method="first"),
            q=min(3, max(1, work["bge_normalized_score"].nunique())),
            duplicates="drop",
        )
        out["same_similarity"] = _spearman_by_group(work, "similarity_bin", candidates)
    if "deprecated_html_tags" in work.columns:
        out["deprecated_html_tags"] = _spearman_by_group(
            work, "deprecated_html_tags", candidates
        )
    return out


def leave_one_keyword_out(
    panel: pl.DataFrame,
    *,
    candidates: Sequence[str],
) -> dict[str, Any]:
    """LOKO stability for median Spearman / NDCG / incremental ΔR² of first candidate."""

    if panel.is_empty() or "target_keyword_id" not in panel.columns:
        return {
            "max_influence_keyword_id": None,
            "candidates": {},
        }

    keyword_ids = [str(value) for value in panel["target_keyword_id"].unique().to_list()]
    if len(keyword_ids) < 2:
        return {
            "max_influence_keyword_id": keyword_ids[0] if keyword_ids else None,
            "candidates": {},
        }

    candidate_results: dict[str, Any] = {}
    influence_scores: dict[str, float] = {keyword_id: 0.0 for keyword_id in keyword_ids}

    for column in candidates:
        if column not in panel.columns:
            continue
        full_ndcg = ndcg_at_k_for_signals(panel, columns=(column,), k=3)
        full_mean = full_ndcg["signals"].get(column, {}).get("macro_mean")
        full_spearman = _median_spearman(panel, column)
        drops: list[dict[str, Any]] = []
        for keyword_id in keyword_ids:
            subset = panel.filter(pl.col("target_keyword_id") != keyword_id)
            ndcg = ndcg_at_k_for_signals(subset, columns=(column,), k=3)
            mean = ndcg["signals"].get(column, {}).get("macro_mean")
            spearman = _median_spearman(subset, column)
            delta = 0.0
            if full_mean is not None and mean is not None:
                delta += abs(full_mean - mean)
            if full_spearman is not None and spearman is not None:
                delta += abs(full_spearman - spearman)
            influence_scores[keyword_id] = influence_scores.get(keyword_id, 0.0) + delta
            drops.append(
                {
                    "dropped_keyword_id": keyword_id,
                    "median_spearman": spearman,
                    "ndcg_macro_mean": mean,
                    "influence_delta": delta,
                }
            )
        candidate_results[column] = {
            "full_median_spearman": full_spearman,
            "full_ndcg_macro_mean": full_mean,
            "drops": drops,
        }

    max_keyword = max(influence_scores, key=influence_scores.get) if influence_scores else None
    return {
        "max_influence_keyword_id": max_keyword,
        "influence_by_keyword": influence_scores,
        "candidates": candidate_results,
    }


def negative_control_permutation(
    panel: pl.DataFrame,
    *,
    candidates: Sequence[str],
    n_permutations: int = 50,
    seed: int = 0,
) -> dict[str, Any]:
    """Within-keyword permutation negative controls for candidate Spearman medians."""

    results: dict[str, Any] = {}
    if panel.is_empty() or "target_keyword_id" not in panel.columns:
        return {"candidates": results, "n_permutations": n_permutations, "seed": seed}

    work = panel.to_pandas()
    rng = np.random.default_rng(seed)
    for column in candidates:
        if column not in work.columns:
            continue
        observed = _median_spearman_pandas(work, column)
        permuted: list[float] = []
        for _ in range(n_permutations):
            shuffled = work.copy()
            shuffled[column] = (
                shuffled.groupby("target_keyword_id", group_keys=False)[column]
                .transform(lambda values: rng.permutation(values.to_numpy()))
            )
            value = _median_spearman_pandas(shuffled, column)
            if value is not None:
                permuted.append(value)
        results[column] = {
            "observed_median_spearman": observed,
            "permuted_median_spearman": float(np.median(permuted)) if permuted else None,
            "permuted_mean_abs_spearman": (
                float(np.mean(np.abs(permuted))) if permuted else None
            ),
            "n_permutations": len(permuted),
        }
    return {"candidates": results, "n_permutations": n_permutations, "seed": seed}


def rank_decile_slices(
    panel: pl.DataFrame,
    *,
    candidates: Sequence[str],
) -> dict[str, Any]:
    """Exploratory rank-decile Spearman slices (1–3 / 4–10 / 11–20)."""

    bands = {
        "ranks_1_3": (1, 3),
        "ranks_4_10": (4, 10),
        "ranks_11_20": (11, 20),
    }
    out: dict[str, Any] = {}
    if panel.is_empty() or "serp_rank" not in panel.columns:
        return out
    for label, (low, high) in bands.items():
        subset = panel.filter(
            (pl.col("serp_rank") >= low) & (pl.col("serp_rank") <= high)
        )
        out[label] = {
            "row_count": subset.height,
            "spearman": {
                column: _median_spearman(subset, column)
                for column in candidates
                if column in subset.columns
            },
        }
    return out


def keyword_holdout_split(
    keywords: Sequence[str],
    *,
    holdout_fraction: float = 0.2,
    seed: int = 0,
) -> dict[str, list[str]]:
    """Seeded keyword holdout split."""

    unique = sorted({str(keyword) for keyword in keywords})
    if not unique:
        return {"train": [], "holdout": []}
    rng = np.random.default_rng(seed)
    order = rng.permutation(unique)
    holdout_n = max(1, int(round(len(unique) * holdout_fraction))) if len(unique) > 1 else 0
    holdout_n = min(holdout_n, len(unique) - 1) if len(unique) > 1 else 0
    holdout = sorted(order[:holdout_n].tolist())
    train = sorted(order[holdout_n:].tolist())
    return {"train": train, "holdout": holdout}


def time_split_overlap(
    panel_a: pl.DataFrame,
    panel_b: pl.DataFrame,
    *,
    candidates: Sequence[str],
    ndcg_k: int = 10,
) -> dict[str, Any]:
    """Compare dossier metrics across overlapping keywords of two runs."""

    if panel_a.is_empty() or panel_b.is_empty():
        return {"status": "skipped", "skip_reason": "empty panel"}
    if "target_keyword_id" not in panel_a.columns or "target_keyword_id" not in panel_b.columns:
        return {"status": "skipped", "skip_reason": "missing target_keyword_id"}

    keys_a = set(panel_a["target_keyword_id"].unique().to_list())
    keys_b = set(panel_b["target_keyword_id"].unique().to_list())
    overlap = sorted(keys_a & keys_b)
    if not overlap:
        return {
            "status": "skipped",
            "skip_reason": "no overlapping keywords between runs",
            "overlap_keywords": [],
        }

    a = panel_a.filter(pl.col("target_keyword_id").is_in(overlap))
    b = panel_b.filter(pl.col("target_keyword_id").is_in(overlap))
    return {
        "status": "computed",
        "overlap_keywords": [str(value) for value in overlap],
        "run_a": _holdout_metrics(a, candidates=candidates, ndcg_k=ndcg_k),
        "run_b": _holdout_metrics(b, candidates=candidates, ndcg_k=ndcg_k),
    }


def _holdout_metrics(
    panel: pl.DataFrame,
    *,
    candidates: Sequence[str],
    ndcg_k: int,
) -> dict[str, Any]:
    keyword_count = (
        int(panel["target_keyword_id"].n_unique())
        if "target_keyword_id" in panel.columns and not panel.is_empty()
        else 0
    )
    mode = (
        "confirmatory"
        if keyword_count >= 10
        else "exploratory"
        if keyword_count >= 2
        else "underpowered"
    )
    return {
        "keyword_count": keyword_count,
        "inference_mode": mode,
        "ndcg": ndcg_at_k_for_signals(panel, columns=candidates, k=ndcg_k),
        "median_spearman": {
            column: _median_spearman(panel, column)
            for column in candidates
            if column in panel.columns
        },
    }


def _ndcg_at_k(
    *,
    relevance: np.ndarray,
    scores: np.ndarray,
    k: int,
) -> float | None:
    if relevance.size < 2 or scores.size != relevance.size:
        return None
    order = np.argsort(-scores)
    ranked = relevance[order]
    cutoff = min(k, ranked.size)
    discounts = 1.0 / np.log2(np.arange(2, cutoff + 2))
    dcg = float(np.sum((np.power(2.0, ranked[:cutoff]) - 1.0) * discounts))
    ideal = np.sort(relevance)[::-1]
    idcg = float(np.sum((np.power(2.0, ideal[:cutoff]) - 1.0) * discounts))
    if idcg <= 0:
        return None
    return dcg / idcg


def _fit_ols(
    frame: pd.DataFrame,
    formula: str,
    *,
    use_cluster: bool,
) -> dict[str, Any]:
    try:
        model = smf.ols(formula, data=frame)
        fitted = model.fit(
            cov_type="cluster",
            cov_kwds={"groups": frame["target_keyword_id"]},
        ) if use_cluster else model.fit()
    except Exception as error:  # noqa: BLE001 — exploratory path; surface status
        logger.warning("dossier ols fit failed formula=%s error=%s", formula, error)
        return {
            "status": "error",
            "formula": formula,
            "adjusted_r_squared": None,
            "coefficients": {},
            "p_values": {},
            "error": str(error),
        }
    coefficients = {
        str(name): float(value)
        for name, value in fitted.params.items()
        if not str(name).startswith("C(")
    }
    p_values = {
        str(name): float(value)
        for name, value in fitted.pvalues.items()
        if not str(name).startswith("C(")
    }
    return {
        "status": "computed",
        "formula": formula,
        "adjusted_r_squared": float(fitted.rsquared_adj),
        "coefficients": coefficients,
        "p_values": p_values,
    }


def _delta_adj_r2(current: Mapping[str, Any], previous: Mapping[str, Any]) -> float | None:
    current_value = current.get("adjusted_r_squared")
    previous_value = previous.get("adjusted_r_squared")
    if not isinstance(current_value, (int, float)) or not isinstance(
        previous_value, (int, float)
    ):
        return None
    return float(current_value) - float(previous_value)


def _partial_rho(
    frame: pd.DataFrame,
    *,
    column: str,
    controls: Sequence[str],
) -> float | None:
    required = [column, "serp_rank", *[control for control in controls if control in frame.columns]]
    if column not in frame.columns or "serp_rank" not in frame.columns:
        return None
    usable = frame.dropna(subset=required)
    if len(usable) < 4:
        return None
    y = usable["serp_rank"].astype(float).to_numpy()
    x = usable[column].astype(float).to_numpy()
    control_cols = [control for control in controls if control in usable.columns]
    if not control_cols:
        rho, _ = stats.spearmanr(x, y)
        return float(rho) if np.isfinite(rho) else None
    design = np.column_stack(
        [np.ones(len(usable)), usable[control_cols].astype(float).to_numpy()]
    )
    try:
        beta_x, _, _, _ = np.linalg.lstsq(design, x, rcond=None)
        beta_y, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    resid_x = x - design @ beta_x
    resid_y = y - design @ beta_y
    if np.std(resid_x) == 0 or np.std(resid_y) == 0:
        return None
    rho, _ = stats.spearmanr(resid_x, resid_y)
    return float(rho) if np.isfinite(rho) else None


def _spearman_by_group(
    frame: pd.DataFrame,
    group_column: str,
    candidates: Sequence[str],
) -> dict[str, Any]:
    groups: dict[str, Any] = {}
    for group_key, group in frame.groupby(group_column, sort=False):
        groups[str(group_key)] = {
            column: _median_spearman_pandas(group, column)
            for column in candidates
            if column in group.columns
        }
    return groups


def _median_spearman(panel: pl.DataFrame, column: str) -> float | None:
    if panel.is_empty() or column not in panel.columns:
        return None
    return _median_spearman_pandas(panel.to_pandas(), column)


def _median_spearman_pandas(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns or "serp_rank" not in frame.columns:
        return None
    if "target_keyword_id" not in frame.columns:
        usable = frame.dropna(subset=[column, "serp_rank"])
        if len(usable) < 2:
            return None
        rho, _ = stats.spearmanr(usable[column], usable["serp_rank"])
        return float(rho) if np.isfinite(rho) else None
    values: list[float] = []
    for _, group in frame.groupby("target_keyword_id", sort=False):
        usable = group.dropna(subset=[column, "serp_rank"])
        if len(usable) < 2:
            continue
        rho, _ = stats.spearmanr(usable[column], usable["serp_rank"])
        if np.isfinite(rho):
            values.append(float(rho))
    if not values:
        return None
    return float(np.median(values))
