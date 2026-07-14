"""Ranking explainability summaries for similarity and TextRazor metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.formula.api as smf
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from tld import get_fld

from seo_rank.stats.artifacts import build_family_source_frames
from seo_rank.stats.panel import build_limitations_for_rank_depth, load_analysis_panel
from seo_rank.stats.rank_depth import filter_panel_by_max_rank
from seo_rank.stats.regression import (
    REGRESSION_CONTROL_COLUMNS,
    REGRESSION_REQUIRED_COLUMNS,
    SIMILARITY_SCORE_COLUMNS,
    summarize_regression_for_score_column,
    _inference_metadata,
    _parameter_confidence_interval,
    _parameter_p_value,
    _parameter_value,
    _public_baseline_formula,
)
from seo_rank.stats.spec import AnalysisSpec, load_analysis_spec

TEXTRAZOR_RANKING_METRICS: tuple[tuple[str, str], ...] = (
    ("entity_confidence", "textrazor_entity_confidence_score"),
    ("entity_relevance", "textrazor_entity_relevance_score"),
    ("entailment_score", "textrazor_entailment_score"),
    ("relation_count", "textrazor_relation_count"),
    ("property_count", "textrazor_property_count"),
)

SIMILARITY_RANKING_METRICS: tuple[tuple[str, str], ...] = tuple(
    (backend, SIMILARITY_SCORE_COLUMNS[backend])
    for backend in ("bge", "gemini_doc_retrieval", "gemini_semantic_similarity")
)

SIMILARITY_SCORE_COLUMNS_RANKING: tuple[str, ...] = tuple(
    column for _, column in SIMILARITY_RANKING_METRICS
)

COMBINED_RANKING_SCORE_COLUMNS: tuple[str, ...] = (
    *SIMILARITY_SCORE_COLUMNS_RANKING,
    *(column for _, column in TEXTRAZOR_RANKING_METRICS),
)

CURATED_RANKING_SCORE_COLUMNS: tuple[str, ...] = (
    "textrazor_relation_count",
    "textrazor_property_count",
    "textrazor_entity_relevance_score",
    "gemini_semantic_similarity_normalized_score",
)

CURATED_MULTIVARIATE_LABEL = "relation_property_relevance_gemini_semantic"

CURATED_PREDICTOR_LABELS: dict[str, str] = {
    "textrazor_relation_count": "Relation count",
    "textrazor_property_count": "Property count",
    "textrazor_entity_relevance_score": "Entity relevance",
    "gemini_semantic_similarity_normalized_score": "Gemini semantic similarity",
}

OUTCOME_DESCRIPTION = "-log(serp_rank)"


def load_similarity_explainability_panel(
    run_dir: Path,
    *,
    rank_depth: str | None = None,
    spec: AnalysisSpec | None = None,
) -> tuple[pl.DataFrame, str, dict[str, str], AnalysisSpec]:
    """Load the analysis mart panel for similarity explainability."""

    analysis_spec = spec or load_analysis_spec()
    depth_key = rank_depth or analysis_spec.primary_rank_depth
    panel_result = load_analysis_panel(run_dir, spec=analysis_spec)
    max_rank = analysis_spec.rank_depth_limit(depth_key)
    filtered = filter_panel_by_max_rank(panel_result.analysis_mart, max_rank=max_rank)
    limitations = build_limitations_for_rank_depth(analysis_spec, depth_key)
    return filtered, depth_key, limitations, analysis_spec


def load_textrazor_explainability_panel(
    run_dir: Path,
    *,
    rank_depth: str | None = None,
    spec: AnalysisSpec | None = None,
) -> tuple[pl.DataFrame, str, dict[str, str], AnalysisSpec]:
    """Load the TextRazor-merged panel for explainability analysis."""

    analysis_spec = spec or load_analysis_spec()
    depth_key = rank_depth or analysis_spec.primary_rank_depth
    panel_result = load_analysis_panel(run_dir, spec=analysis_spec)
    source_frames = build_family_source_frames(
        run_dir,
        analysis_mart=panel_result.analysis_mart,
        spec=analysis_spec,
    )
    textrazor_panel = source_frames["textrazor_page_metrics"]
    max_rank = analysis_spec.rank_depth_limit(depth_key)
    filtered = filter_panel_by_max_rank(textrazor_panel, max_rank=max_rank)
    limitations = build_limitations_for_rank_depth(analysis_spec, depth_key)
    return filtered, depth_key, limitations, analysis_spec


def summarize_ranking_explainability(
    similarity_panel: pl.DataFrame,
    textrazor_panel: pl.DataFrame,
    *,
    run_id: str,
    rank_depth: str,
    spec: AnalysisSpec | None = None,
    limitations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Summarize adjusted R² for similarity backends and TextRazor metrics."""

    analysis_spec = spec or load_analysis_spec()
    resolved_limitations = limitations or build_limitations_for_rank_depth(
        analysis_spec,
        rank_depth,
    )
    keyword_count = (
        int(similarity_panel["target_keyword_id"].n_unique())
        if not similarity_panel.is_empty()
        else 0
    )
    similarity = _summarize_metric_group(
        similarity_panel,
        metrics=SIMILARITY_RANKING_METRICS,
        multivariate_label="all_similarity_backends",
    )
    textrazor = _summarize_metric_group(
        textrazor_panel,
        metrics=TEXTRAZOR_RANKING_METRICS,
        multivariate_label="all_textrazor_metrics",
    )
    multivariate = _summarize_multivariate_metrics(
        textrazor_panel,
        score_columns=COMBINED_RANKING_SCORE_COLUMNS,
        label="all_similarity_and_textrazor_metrics",
    )
    multivariate_curated = _summarize_multivariate_metrics(
        textrazor_panel,
        score_columns=CURATED_RANKING_SCORE_COLUMNS,
        label=CURATED_MULTIVARIATE_LABEL,
    )

    return {
        "run_id": run_id,
        "rank_depth": rank_depth,
        "estimand": {
            "outcome": OUTCOME_DESCRIPTION,
            "baseline_formula": _public_baseline_formula(keyword_count),
        },
        "similarity": similarity,
        "textrazor": textrazor,
        "multivariate": multivariate,
        "multivariate_curated": multivariate_curated,
        "limitations": resolved_limitations,
    }


def summarize_similarity_ranking_explainability(
    panel: pl.DataFrame,
    *,
    run_id: str,
    rank_depth: str,
    spec: AnalysisSpec | None = None,
    limitations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Summarize univariate and multivariate adjusted R² for similarity backends."""

    return _summarize_metric_family(
        panel,
        metrics=SIMILARITY_RANKING_METRICS,
        multivariate_label="all_similarity_backends",
        run_id=run_id,
        rank_depth=rank_depth,
        spec=spec,
        limitations=limitations,
    )


def summarize_textrazor_ranking_explainability(
    panel: pl.DataFrame,
    *,
    run_id: str,
    rank_depth: str,
    spec: AnalysisSpec | None = None,
    limitations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Summarize univariate and multivariate adjusted R² for TextRazor metrics."""

    return _summarize_metric_family(
        panel,
        metrics=TEXTRAZOR_RANKING_METRICS,
        multivariate_label="all_textrazor_metrics",
        run_id=run_id,
        rank_depth=rank_depth,
        spec=spec,
        limitations=limitations,
    )


def _summarize_metric_family(
    panel: pl.DataFrame,
    *,
    metrics: Sequence[tuple[str, str]],
    multivariate_label: str,
    run_id: str,
    rank_depth: str,
    spec: AnalysisSpec | None = None,
    limitations: dict[str, str] | None = None,
) -> dict[str, Any]:
    analysis_spec = spec or load_analysis_spec()
    resolved_limitations = limitations or build_limitations_for_rank_depth(
        analysis_spec,
        rank_depth,
    )
    keyword_count = (
        int(panel["target_keyword_id"].n_unique()) if not panel.is_empty() else 0
    )
    metric_group = _summarize_metric_group(
        panel,
        metrics=metrics,
        multivariate_label=multivariate_label,
    )
    return {
        "run_id": run_id,
        "rank_depth": rank_depth,
        "estimand": {
            "outcome": OUTCOME_DESCRIPTION,
            "baseline_formula": _public_baseline_formula(keyword_count),
        },
        **metric_group,
        "limitations": resolved_limitations,
    }


def _summarize_metric_group(
    panel: pl.DataFrame,
    *,
    metrics: Sequence[tuple[str, str]],
    multivariate_label: str,
) -> dict[str, Any]:
    keyword_count = (
        int(panel["target_keyword_id"].n_unique()) if not panel.is_empty() else 0
    )
    score_columns = tuple(column for _, column in metrics)
    univariate = [
        _summarize_univariate_metric(panel, label=label, score_column=column)
        for label, column in metrics
    ]
    multivariate = _summarize_multivariate_metrics(
        panel,
        score_columns=score_columns,
        label=multivariate_label,
    )
    return {
        "panel": {
            "rows": panel.height,
            "keywords": keyword_count,
            "metric_coverage": _metric_coverage(panel, metrics),
        },
        "univariate": univariate,
        "multivariate": multivariate,
    }


def _summarize_univariate_metric(
    panel: pl.DataFrame,
    *,
    label: str,
    score_column: str,
) -> dict[str, Any]:
    summary = summarize_regression_for_score_column(
        panel,
        label=label,
        score_column=score_column,
    )
    return {
        "label": label,
        "score_column": score_column,
        "status": summary.get("status", "computed"),
        "skipped_reason": summary.get("skipped_reason"),
        "row_count": summary.get("row_count", 0),
        "keyword_count": summary.get("keyword_count", 0),
        "baseline_model": summary.get("baseline_model"),
        "feature_model": _public_feature_model(summary),
        "descriptive_fit_delta": summary.get("descriptive_fit_delta"),
    }


def _public_feature_model(summary: dict[str, object]) -> dict[str, object] | None:
    feature_model = summary.get("feature_model")
    if not isinstance(feature_model, dict):
        return None
    return {
        "formula": feature_model.get("formula"),
        "coefficient": feature_model.get("coefficient"),
        "p_value": feature_model.get("p_value"),
        "adjusted_r_squared": feature_model.get("adjusted_r_squared"),
        "covariance": feature_model.get("covariance"),
    }


def _metric_coverage(
    panel: pl.DataFrame,
    metrics: Sequence[tuple[str, str]],
) -> dict[str, dict[str, int]]:
    total = panel.height
    coverage: dict[str, dict[str, int]] = {}
    for _, column in metrics:
        if column not in panel.columns:
            coverage[column] = {"non_null": 0, "null": total, "total_rows": total}
            continue
        non_null = int(panel[column].is_not_null().sum())
        coverage[column] = {
            "non_null": non_null,
            "null": total - non_null,
            "total_rows": total,
        }
    return coverage


def _summarize_multivariate_metrics(
    panel: pl.DataFrame,
    *,
    score_columns: Sequence[str],
    label: str,
) -> dict[str, Any]:
    fit = fit_multivariate_ranking_model(panel, score_columns=score_columns)
    if fit is None:
        return {
            "label": label,
            "status": "skipped",
            "skipped_reason": "no_usable_rows",
            "row_count": 0,
            "keyword_count": 0,
            "score_columns": list(score_columns),
        }
    if fit.get("status") == "skipped":
        return {
            "label": label,
            **fit,
            "score_columns": list(score_columns),
        }

    baseline_result = fit["baseline_result"]
    feature_result = fit["feature_result"]
    clustered_result = fit["clustered_result"]
    keyword_count = int(fit["keyword_count"])
    row_count = int(fit["row_count"])
    feature_formula = str(fit["feature_formula"])

    coefficients = {
        column: _parameter_value(clustered_result, column)
        for column in score_columns
    }
    p_values = {
        column: _parameter_p_value(clustered_result, column)
        for column in score_columns
    }
    confidence_intervals = {
        column: _parameter_confidence_interval(clustered_result, column)
        for column in score_columns
    }

    return {
        "label": label,
        "status": "computed",
        "row_count": row_count,
        "keyword_count": keyword_count,
        "score_columns": list(score_columns),
        "baseline_model": {
            "formula": _public_baseline_formula(keyword_count),
            "adjusted_r_squared": float(baseline_result.rsquared_adj),
        },
        "feature_model": {
            "formula": feature_formula,
            "coefficients": coefficients,
            "p_values": p_values,
            "confidence_intervals": confidence_intervals,
            "adjusted_r_squared": float(feature_result.rsquared_adj),
            "covariance": _inference_metadata(keyword_count),
        },
        "descriptive_fit_delta": {
            "adjusted_r_squared": float(
                feature_result.rsquared_adj - baseline_result.rsquared_adj
            ),
        },
    }


def fit_multivariate_ranking_model(
    panel: pl.DataFrame,
    *,
    score_columns: Sequence[str],
) -> dict[str, Any] | None:
    """Fit the pooled multivariate OLS model used by ranking explainability."""

    model_frame = _prepare_multivariate_frame(panel, score_columns)
    if model_frame.is_empty():
        return None
    if model_frame.height < 3:
        return {
            "status": "skipped",
            "skipped_reason": "insufficient_rows",
            "row_count": model_frame.height,
            "keyword_count": int(model_frame["target_keyword_id"].n_unique()),
        }

    model_data = model_frame.to_pandas().copy()
    keyword_count = int(model_data["target_keyword_id"].nunique())
    model_data["outcome"] = -np.log(model_data["serp_rank"].astype(float))
    control_columns = tuple(
        column
        for column in REGRESSION_CONTROL_COLUMNS
        if column in model_data.columns and not model_data[column].isna().any()
    )

    try:
        if keyword_count >= 2:
            baseline_formula = _public_baseline_formula(keyword_count, control_columns)
            feature_formula = _multivariate_feature_formula(
                score_columns, keyword_count, control_columns
            )
            baseline_result = smf.ols(baseline_formula, data=model_data).fit()
            feature_result = smf.ols(feature_formula, data=model_data).fit()
            if feature_result.df_resid <= 0:
                return {
                    "status": "skipped",
                    "skipped_reason": "non_positive_residual_df",
                    "row_count": model_frame.height,
                    "keyword_count": keyword_count,
                }
            # df_resid uses matrix rank, but statsmodels' cluster-robust small-sample
            # correction divides by (nobs - raw exog column count). A column-rank-
            # deficient design (e.g. tied predictor values within a keyword group)
            # can leave df_resid > 0 while nobs <= exog.shape[1], causing a
            # ZeroDivisionError inside get_robustcov_results.
            if feature_result.nobs <= feature_result.model.exog.shape[1]:
                return {
                    "status": "skipped",
                    "skipped_reason": "non_positive_residual_df",
                    "row_count": model_frame.height,
                    "keyword_count": keyword_count,
                }
            clustered_result = feature_result.get_robustcov_results(
                cov_type="cluster",
                groups=model_data["target_keyword_id"],
            )
        else:
            baseline_formula = _public_baseline_formula(keyword_count, control_columns)
            feature_formula = _multivariate_feature_formula(
                score_columns, keyword_count, control_columns
            )
            baseline_result = smf.ols(baseline_formula, data=model_data).fit()
            feature_result = smf.ols(feature_formula, data=model_data).fit()
            if feature_result.df_resid <= 0:
                return {
                    "status": "skipped",
                    "skipped_reason": "non_positive_residual_df",
                    "row_count": model_frame.height,
                    "keyword_count": keyword_count,
                }
            clustered_result = feature_result.get_robustcov_results(cov_type="HC3")
    except (np.linalg.LinAlgError, ValueError):
        # ponytail: match entities.py — SVD/singular OLS must not abort Phase 5
        return {
            "status": "skipped",
            "skipped_reason": "svd_did_not_converge",
            "row_count": model_frame.height,
            "keyword_count": keyword_count,
        }

    return {
        "status": "computed",
        "row_count": model_frame.height,
        "keyword_count": keyword_count,
        "feature_formula": feature_formula,
        "model_data": model_data,
        "baseline_result": baseline_result,
        "feature_result": feature_result,
        "clustered_result": clustered_result,
    }


def _prepare_multivariate_frame(
    panel: pl.DataFrame,
    score_columns: Sequence[str],
) -> pl.DataFrame:
    required = [*score_columns, *REGRESSION_REQUIRED_COLUMNS]
    present = [column for column in required if column in panel.columns]
    if len(present) != len(required):
        return pl.DataFrame()
    return panel.drop_nulls(required)


def _multivariate_feature_formula(
    score_columns: Sequence[str],
    keyword_count: int,
    control_columns: Sequence[str],
) -> str:
    control_terms = list(control_columns)
    terms = " + ".join([*score_columns, *control_terms])
    if keyword_count >= 2:
        return f"outcome ~ {terms} + C(target_keyword_id)"
    return f"outcome ~ {terms}"


RANKING_IMPORTANCE_GROUP_ORDER: tuple[str, ...] = (
    "similarity",
    "textrazor",
    "backlinks",
    "metadata_lengths",
    "performance",
    "crawl_architecture",
    "structured_markup",
    "document_structure",
    "quality_flags",
    "resource_footprint",
    "presentation_metadata",
    "delivery_configuration",
    "legacy_embedding",
    "content",
)

CURATED_IMPORTANCE_COLUMNS: tuple[str, ...] = (
    "referring_domains_count",
    "gemini_doc_retrieval_normalized_score",
    "textrazor_entailment_score",
    "onpage_score",
    "plain_text_rate",
    "flesch_kincaid_readability_index",
    "title_length",
    "description_length",
)
IMPORTANCE_MAX_MISSING_FRACTION = 0.5
IMPORTANCE_MIN_VARYING_KEYWORDS = 5
IMPORTANCE_CORRELATION_THRESHOLD = 0.95

_RANKING_IMPORTANCE_FAMILY_KEYS: dict[str, tuple[str, ...]] = {
    "similarity": (),
    "textrazor": (),
    "backlinks": ("backlinks_counts",),
    "performance": ("onpage_core_web_vitals",),
    "content": ("onpage_content_quality",),
}

_ONPAGE_IMPORTANCE_GROUP_COLUMNS: dict[str, tuple[str, ...]] = {
    "crawl_architecture": (
        "is_redirect",
        "follow",
        "inbound_links_count",
        "click_depth",
        "seo_friendly_url",
    ),
    "structured_markup": (
        "has_valid_structured_data",
        "has_micromarkup",
        "has_micromarkup_errors",
    ),
    "document_structure": (
        "h1_count",
        "h2_count",
        "h3_count",
        "high_content_rate",
        "high_character_count",
    ),
    "quality_flags": (
        "duplicate_meta_tags_count",
        "duplicate_content",
        "lorem_ipsum",
    ),
    "resource_footprint": (
        "images_count",
        "images_size",
        "scripts_count",
        "stylesheets_count",
        "encoded_size",
        "small_page_size",
        "resource_warnings_count",
    ),
    "presentation_metadata": (
        "has_og_tags",
        "has_twitter_tags",
        "no_favicon",
        "no_image_title",
    ),
    "delivery_configuration": (
        "cache_control_cachable",
        "cache_control_ttl",
    ),
    "legacy_embedding": ("flash", "frame"),
}

_RANKING_IMPORTANCE_JOIN_KEYS: tuple[str, ...] = (
    "run_id",
    "target_keyword_id",
    "canonical_url_hash",
)


def ranking_importance_factor_columns(spec: AnalysisSpec) -> dict[str, tuple[str, ...]]:
    """Map high-level factor groups to registry signal columns."""

    groups: dict[str, tuple[str, ...]] = {}
    for group in RANKING_IMPORTANCE_GROUP_ORDER:
        if group in _ONPAGE_IMPORTANCE_GROUP_COLUMNS:
            groups[group] = _ONPAGE_IMPORTANCE_GROUP_COLUMNS[group]
            continue
        if group == "similarity":
            family_keys = spec.signal_families.similarity_keys
        elif group == "textrazor":
            family_keys = spec.signal_families.textrazor_keys
        elif group == "metadata_lengths":
            groups[group] = ("title_length", "description_length")
            continue
        else:
            family_keys = _RANKING_IMPORTANCE_FAMILY_KEYS[group]

        columns: list[str] = []
        for family_key in family_keys:
            family = spec.signal_family(family_key)
            columns.extend(family.signal_columns)

        deduped: list[str] = []
        seen: set[str] = set()
        for column in columns:
            if column in seen:
                continue
            seen.add(column)
            deduped.append(column)
        groups[group] = tuple(deduped)
    return groups


def load_ranking_importance_panel(
    run_dir: Path,
    *,
    rank_depth: str | None = None,
    spec: AnalysisSpec | None = None,
) -> tuple[pl.DataFrame, str, dict[str, str], AnalysisSpec]:
    """Load the merged panel used for full-model relative importance."""

    analysis_spec = spec or load_analysis_spec()
    depth_key = rank_depth or analysis_spec.primary_rank_depth
    panel_result = load_analysis_panel(run_dir, spec=analysis_spec)
    source_frames = build_family_source_frames(
        run_dir,
        analysis_mart=panel_result.analysis_mart,
        spec=analysis_spec,
    )
    factor_columns = ranking_importance_factor_columns(analysis_spec)
    panel = _merge_ranking_importance_frames(source_frames, factor_columns)
    max_rank = analysis_spec.rank_depth_limit(depth_key)
    filtered = filter_panel_by_max_rank(panel, max_rank=max_rank)
    limitations = build_limitations_for_rank_depth(analysis_spec, depth_key)
    return filtered, depth_key, limitations, analysis_spec


def summarize_ranking_relative_importance(
    panel: pl.DataFrame,
    *,
    spec: AnalysisSpec | None = None,
    cv_folds: int = 5,
    cv_repeats: int = 5,
    bootstraps: int = 500,
    shapley_permutations: int = 2000,
    domain_cv_repeats: int = 10,
    random_state: int = 0,
    min_complete_rows: int | None = None,
) -> dict[str, Any]:
    """Summarize grouped and metric-level relative importance for ranking predictors."""

    analysis_spec = spec or load_analysis_spec()
    factor_columns = ranking_importance_factor_columns(analysis_spec)
    prepared = _prepare_ranking_importance_context(
        panel,
        factor_columns,
        min_complete_rows=min_complete_rows,
    )
    if prepared is None:
        return {
            "status": "skipped",
            "skipped_reason": "no_usable_rows",
            "row_count": panel.height,
            "keyword_count": int(panel["target_keyword_id"].n_unique()) if not panel.is_empty() else 0,
            "cv_folds": cv_folds,
            "cv_repeats": cv_repeats,
            "bootstraps": bootstraps,
            "excluded_predictors": [],
            "groups": [],
        }

    model_data = prepared["model_data"]
    selected_columns = prepared["selected_columns"]
    keyword_count = prepared["keyword_count"]
    control_columns = prepared["control_columns"]

    full_r2 = _fit_importance_r_squared(
        model_data,
        selected_columns,
        keyword_count=keyword_count,
        control_columns=control_columns,
        print_design=True,
    )
    if full_r2 is None:
        return {
            "status": "skipped",
            "skipped_reason": "full_model_not_fitted",
            "row_count": prepared["row_count"],
            "keyword_count": keyword_count,
            "cv_folds": cv_folds,
            "cv_repeats": cv_repeats,
            "bootstraps": bootstraps,
            "excluded_predictors": prepared.get("excluded_predictors", []),
            "groups": [],
        }

    shapley_statistics = _permutation_shapley_statistics(
        model_data,
        factor_columns,
        selected_columns=selected_columns,
        keyword_count=keyword_count,
        control_columns=control_columns,
        permutations=shapley_permutations,
        random_state=random_state,
    )
    shapley_values = shapley_statistics["values"]
    shapley_total = sum(shapley_values.values())

    oos_panel = _prepare_oos_importance_frame(panel, factor_columns)
    oos_result = _compute_grouped_oof_importance(
        oos_panel,
        factor_columns,
        cv_folds=cv_folds,
        cv_repeats=cv_repeats,
        random_state=random_state,
    )
    oos_bootstrap = _bootstrap_oos_delta_ci(
        oos_result,
        bootstraps=bootstraps,
        random_state=random_state + 1,
        sample_column="target_keyword_id",
    )
    domain_holdout = _domain_holdout_oof_importance(
        oos_panel,
        factor_columns,
        random_state=random_state + 2,
        cv_repeats=domain_cv_repeats,
    )
    domain_bootstrap = _bootstrap_oos_delta_ci(
        domain_holdout,
        bootstraps=bootstraps,
        random_state=random_state + 4,
        sample_column="domain",
    )
    metadata_only = _metadata_only_oof_importance(
        oos_panel,
        factor_columns,
        cv_folds=cv_folds,
        cv_repeats=cv_repeats,
        random_state=random_state + 3,
    )

    groups: list[dict[str, Any]] = []
    for group in RANKING_IMPORTANCE_GROUP_ORDER:
        in_sample_columns = tuple(
            column for column in factor_columns[group] if column in selected_columns
        )
        without_columns = _columns_without_group(
            selected_columns,
            factor_columns[group],
        )
        without_r2 = _fit_importance_r_squared(
            model_data,
            without_columns,
            keyword_count=keyword_count,
            control_columns=control_columns,
        )
        partial_r2 = (
            _partial_r_squared(full_r2, without_r2)
            if in_sample_columns and without_r2 is not None
            else None
        )
        shapley_share = (
            float(shapley_values[group] / shapley_total)
            if shapley_total != 0
            else 0.0
        )
        metric_rows = _metric_relative_importance_rows(
            model_data,
            group=group,
            group_columns=factor_columns[group],
            selected_columns=selected_columns,
            keyword_count=keyword_count,
            control_columns=control_columns,
            full_r2=full_r2,
        )
        oos_group = (oos_result or {}).get("groups", {}).get(group, {})
        oos_ci = (oos_bootstrap or {}).get(group, {})
        domain_group = (domain_holdout or {}).get("groups", {}).get(group, {})
        domain_ci = (domain_bootstrap or {}).get(group, {})
        oos_columns = tuple(column for column in (oos_panel.attrs.get("predictor_columns", ()) if oos_panel is not None else ()) if column in factor_columns[group])
        domain_rows = (domain_holdout or {}).get("domain_rows")
        domain_count = (domain_holdout or {}).get("domain_count")
        keyword_ci = oos_ci.get("delta_r2")
        keyword_interval = (
            (keyword_ci.get("lower"), keyword_ci.get("upper"))
            if isinstance(keyword_ci, dict)
            else None
        )
        tested = bool(oos_columns) and oos_group.get("delta_r2") is not None
        domain_interval = (
            (domain_ci.get("lower"), domain_ci.get("upper"))
            if isinstance(domain_ci, dict)
            else None
        )
        groups.append(
            {
                "factor": group,
                "full_model_partial_r2": partial_r2,
                "shapley_share": shapley_share if in_sample_columns else None,
                "in_sample_predictor_count": len(in_sample_columns),
                "in_sample_predictor_columns": list(in_sample_columns),
                "in_sample_rows": prepared["row_count"] if in_sample_columns else None,
                "in_sample_keywords": keyword_count if in_sample_columns else None,
                "out_of_sample_full_r2": oos_group.get("full_r2"),
                "out_of_sample_reduced_r2": oos_group.get("reduced_r2"),
                "out_of_sample_delta_r2": oos_group.get("delta_r2"),
                "out_of_sample_delta_r2_ci": oos_ci.get("delta_r2"),
                "out_of_sample_ndcg": oos_group.get("ndcg_full"),
                "out_of_sample_ndcg_delta": oos_group.get("ndcg_delta"),
                "out_of_sample_ndcg_delta_ci": oos_ci.get("ndcg_delta"),
                "domain_holdout_delta_r2": domain_group.get("delta_r2"),
                "domain_holdout_delta_r2_ci": domain_ci.get("delta_r2"),
                "domain_holdout_ndcg_delta": domain_group.get("ndcg_delta"),
                "domain_holdout_ndcg_delta_ci": domain_ci.get("ndcg_delta"),
                "oos_predictor_columns": list(oos_columns),
                "oos_predictor_count": len(oos_columns),
                "oos_rows": oos_group.get("row_count"),
                "oos_keywords": oos_group.get("group_count"),
                "repeat_mean_delta_r2": oos_group.get("repeat_mean_delta_r2"),
                "repeat_sd_delta_r2": oos_group.get("repeat_sd_delta_r2"),
                "repeat_min_delta_r2": oos_group.get("repeat_min_delta_r2"),
                "repeat_max_delta_r2": oos_group.get("repeat_max_delta_r2"),
                "domain_rows": domain_rows,
                "domain_count": domain_count,
                "domain_rows_with_extraction_failure": (domain_holdout or {}).get(
                    "domain_rows_with_extraction_failure"
                ),
                "domains_per_fold": (domain_holdout or {}).get("domains_per_fold"),
                "domain_repeat_deltas": [
                    result.get("groups", {}).get(group, {}).get("delta_r2")
                    for result in (domain_holdout or {}).get("repeat_results", [])
                ],
                "evidence_status": _evidence_status(
                    keyword_interval,
                    domain_group.get("delta_r2"),
                    domain_ci=domain_interval,
                    keyword_delta=oos_group.get("delta_r2"),
                    tested=tested,
                ),
                "metrics": metric_rows,
            }
        )

    return {
        "status": "computed",
        "row_count": prepared["row_count"],
        "keyword_count": keyword_count,
        "oos_row_count": None if oos_panel is None else int(len(oos_panel)),
        "oos_keyword_count": None if oos_panel is None else int(oos_panel["target_keyword_id"].nunique()),
        "cv_folds": cv_folds,
        "cv_repeats": cv_repeats,
        "domain_cv_repeats": domain_cv_repeats,
        "bootstraps": bootstraps,
        "shapley_method": "permutation",
        "shapley_permutations": shapley_permutations,
        "shapley_mcse": shapley_statistics["mcse"],
        "shapley_convergence_difference": shapley_statistics["convergence_difference"],
        "predictor_columns": list(selected_columns),
        "excluded_predictors": prepared.get("excluded_predictors", []),
        "full_model_r_squared": full_r2,
        "out_of_sample_full_r2": None if oos_result is None else oos_result.get("full_r2"),
        "out_of_sample_ndcg": None if oos_result is None else oos_result.get("ndcg_full"),
        "metadata_only_oos_r_squared": None if metadata_only is None else metadata_only.get("full_r2"),
        "metadata_only_oos_ndcg": None if metadata_only is None else metadata_only.get("ndcg_full"),
        "warnings": ["cv_repeats=1 is exploratory; repeat uncertainty is not estimable."] if cv_repeats == 1 else [],
        "oos_note": (
            "OOS uses repeated keyword GroupKFold with fold-local Ridge "
            "(log1p counts, standardize, NZV/duplicate drop, median impute), "
            "repeat-level summaries, and keyword/repeat-bootstrap CIs for the OOS delta. "
            "In-sample partial R² / Shapley stay on the complete-case OLS path."
        ),
        "groups": groups,
        "explanatory_groups": [
            {
                key: group[key]
                for key in (
                    "factor",
                    "full_model_partial_r2",
                    "shapley_share",
                    "in_sample_predictor_count",
                    "in_sample_predictor_columns",
                    "in_sample_rows",
                    "in_sample_keywords",
                )
            }
            for group in groups
        ],
        "keyword_oos_groups": [
            {
                key: group[key]
                for key in (
                    "factor",
                    "out_of_sample_full_r2",
                    "out_of_sample_reduced_r2",
                    "out_of_sample_delta_r2",
                    "out_of_sample_delta_r2_ci",
                    "out_of_sample_ndcg_delta",
                    "out_of_sample_ndcg_delta_ci",
                    "oos_predictor_count",
                    "oos_predictor_columns",
                    "oos_rows",
                    "oos_keywords",
                    "repeat_mean_delta_r2",
                    "repeat_sd_delta_r2",
                    "repeat_min_delta_r2",
                    "repeat_max_delta_r2",
                    "evidence_status",
                )
            }
            for group in groups
        ],
        "domain_oos_groups": [
            {
                key: group[key]
                for key in (
                    "factor",
                    "domain_holdout_delta_r2",
                    "domain_holdout_delta_r2_ci",
                    "domain_holdout_ndcg_delta",
                    "domain_holdout_ndcg_delta_ci",
                    "domain_rows",
                    "domain_count",
                    "domain_rows_with_extraction_failure",
                    "domains_per_fold",
                    "domain_repeat_deltas",
                )
            }
            for group in groups
        ],
    }


def _merge_ranking_importance_frames(
    source_frames: dict[str, pl.DataFrame],
    factor_columns: Mapping[str, Sequence[str]],
) -> pl.DataFrame:
    merged = source_frames["analysis_mart"]
    all_columns = {column for columns in factor_columns.values() for column in columns}
    for mart_name in ("textrazor_page_metrics", "backlinks_analysis", "onpage_features"):
        frame = source_frames[mart_name]
        if frame.is_empty():
            continue
        new_columns = [
            column
            for column in frame.columns
            if column in all_columns and column not in merged.columns
        ]
        if not new_columns:
            continue
        merged = merged.join(
            frame.select([*_RANKING_IMPORTANCE_JOIN_KEYS, *new_columns]),
            on=list(_RANKING_IMPORTANCE_JOIN_KEYS),
            how="left",
        )
    return merged


def _prepare_ranking_importance_context(
    panel: pl.DataFrame,
    factor_columns: Mapping[str, Sequence[str]],
    *,
    min_complete_rows: int | None = None,
) -> dict[str, Any] | None:
    requested_columns = [
        column for columns in factor_columns.values() for column in columns
    ]
    available_columns = _available_predictor_columns(panel, requested_columns)
    if not available_columns:
        return None

    excluded_predictors = [
        {
            "column": column,
            "reason": "excessive_missingness",
        }
        for column in available_columns
        if panel[column].null_count() / max(panel.height, 1)
        > IMPORTANCE_MAX_MISSING_FRACTION
    ]
    candidate_columns = tuple(
        dict.fromkeys(
            [
                *factor_columns["similarity"],
                *factor_columns["textrazor"],
                *CURATED_IMPORTANCE_COLUMNS,
            ]
        )
    )
    selected_columns = tuple(
        column
        for column in candidate_columns
        if column in available_columns
        and panel[column].null_count() / max(panel.height, 1)
        <= IMPORTANCE_MAX_MISSING_FRACTION
    )
    control_candidates = tuple(
        column
        for column in REGRESSION_CONTROL_COLUMNS
        if column in panel.columns
        and panel[column].null_count() / max(panel.height, 1)
        <= IMPORTANCE_MAX_MISSING_FRACTION
    )
    if not selected_columns:
        return None

    required = ["target_keyword_id", *REGRESSION_REQUIRED_COLUMNS, *selected_columns, *control_candidates]
    model_data = panel.select([column for column in required if column in panel.columns]).to_pandas()
    model_data = model_data.loc[
        model_data["target_keyword_id"].notna()
        & model_data["serp_rank"].notna()
        & np.isfinite(model_data["serp_rank"].astype(float))
        & (model_data["serp_rank"].astype(float) > 0)
    ].copy()
    if len(model_data) < 3:
        return None

    model_data["outcome"] = -np.log(model_data["serp_rank"].astype(float))
    imputation_columns = [*selected_columns, *control_candidates]
    nuisance_columns: list[str] = []
    for column in imputation_columns:
        values = pd.to_numeric(model_data[column], errors="coerce")
        missing = values.isna()
        if missing.any():
            indicator = f"{column}__missing"
            model_data[indicator] = missing.astype(float)
            nuisance_columns.append(indicator)
        median = values.median()
        model_data[column] = values.fillna(0.0 if pd.isna(median) else float(median))

    varying_columns = [
        column
        for column in selected_columns
        if (
            model_data.groupby("target_keyword_id")[column]
            .nunique(dropna=True)
            .gt(1)
            .sum()
            >= IMPORTANCE_MIN_VARYING_KEYWORDS
        )
    ]
    for left_index, left in enumerate(varying_columns):
        if left not in varying_columns:
            continue
        for right in varying_columns[left_index + 1 :]:
            if right not in varying_columns:
                continue
            if abs(model_data[left].corr(model_data[right])) >= IMPORTANCE_CORRELATION_THRESHOLD:
                varying_columns.remove(right)
                excluded_predictors.append(
                    {"column": right, "reason": "high_correlation"}
                )
    selected_columns = tuple(varying_columns)
    if not selected_columns:
        return None

    control_columns = tuple(
        column
        for column in control_candidates
        if (
            model_data.groupby("target_keyword_id")[column]
            .nunique(dropna=True)
            .gt(1)
            .sum()
            >= IMPORTANCE_MIN_VARYING_KEYWORDS
        )
    )
    fe_columns = [*selected_columns, *control_columns, *nuisance_columns]
    model_data["outcome_fe"] = model_data["outcome"] - model_data.groupby(
        "target_keyword_id"
    )["outcome"].transform("mean")
    for column in fe_columns:
        model_data[f"{column}_fe"] = model_data[column] - model_data.groupby(
            "target_keyword_id"
        )[column].transform("mean")

    accepted_controls: list[str] = []
    accepted_nuisance_columns: list[str] = []
    base_fe_columns: list[str] = []
    base_rank = 0
    for column in [*control_columns, *nuisance_columns]:
        fe_column = f"{column}_fe"
        if fe_column not in model_data.columns:
            continue
        candidate_rank = np.linalg.matrix_rank(
            model_data[[*base_fe_columns, fe_column]].to_numpy(dtype=float)
        )
        if candidate_rank == base_rank:
            continue
        base_fe_columns.append(fe_column)
        base_rank = candidate_rank
        if column in control_columns:
            accepted_controls.append(column)
        else:
            accepted_nuisance_columns.append(column)
    control_columns = tuple(accepted_controls)
    nuisance_columns = accepted_nuisance_columns
    accepted_columns: list[str] = []
    current_rank = base_rank
    for column in selected_columns:
        candidate = model_data[[*base_fe_columns, *[f"{item}_fe" for item in [*accepted_columns, column]]]].to_numpy(dtype=float)
        candidate_rank = np.linalg.matrix_rank(candidate)
        if candidate_rank == current_rank:
            excluded_predictors.append({"column": column, "reason": "collinear"})
            continue
        accepted_columns.append(column)
        current_rank = candidate_rank
    selected_columns = tuple(accepted_columns)
    if not selected_columns:
        return None
    model_data.attrs["within_keyword_fe"] = True
    model_data.attrs["nuisance_columns"] = tuple(nuisance_columns)

    keyword_count = int(model_data["target_keyword_id"].nunique())
    return {
        "model_data": model_data,
        "candidate_columns": candidate_columns,
        "selected_columns": selected_columns,
        "excluded_predictors": excluded_predictors,
        "keyword_count": keyword_count,
        "control_columns": control_columns,
        "row_count": len(model_data),
    }


def _available_predictor_columns(
    panel: pl.DataFrame,
    columns: Sequence[str],
) -> tuple[str, ...]:
    selected: list[str] = []
    for column in columns:
        if column not in panel.columns:
            continue
        if int(panel[column].is_not_null().sum()) == 0:
            continue
        selected.append(column)
    return tuple(selected)


def _columns_without_group(
    selected_columns: Sequence[str],
    group_columns: Sequence[str],
) -> tuple[str, ...]:
    group_set = set(group_columns)
    return tuple(column for column in selected_columns if column not in group_set)


def _partial_r_squared(full_r2: float, reduced_r2: float) -> float | None:
    """Unique variance share: (R²_full - R²_reduced) / (1 - R²_reduced)."""

    if reduced_r2 >= 1.0:
        return None
    denominator = 1.0 - reduced_r2
    if denominator <= 0.0:
        return None
    return float((full_r2 - reduced_r2) / denominator)


def _evidence_status(
    keyword_ci: tuple[float | None, float | None] | None,
    domain_delta: float | None,
    *,
    domain_ci: tuple[float | None, float | None] | None = None,
    keyword_delta: float | None = None,
    tested: bool,
) -> str:
    if not tested:
        return "Not tested"
    if keyword_delta is not None and keyword_delta <= 0.0:
        return "Redundant/no value"
    if keyword_ci is None or keyword_ci[0] is None or keyword_ci[1] is None:
        return "Uncertain"
    if keyword_ci[0] <= 0.0 <= keyword_ci[1]:
        return "Uncertain"
    if domain_delta is None:
        return "Uncertain"
    if domain_ci is not None and domain_ci[1] is not None and domain_ci[1] < 0.0:
        return "Harmful to portability"
    if domain_delta < 0.0:
        return "Dataset-specific"
    if domain_ci is not None and domain_ci[0] is not None and domain_ci[0] > 0.0:
        return "Portable"
    return "Keyword-supported"



def _fit_importance_r_squared(
    model_data: Any,
    score_columns: Sequence[str],
    *,
    keyword_count: int,
    control_columns: Sequence[str],
    include_keyword_fixed_effects: bool = True,
    print_design: bool = False,
) -> float | None:
    try:
        if model_data.attrs.get("within_keyword_fe"):
            nuisance_columns = tuple(model_data.attrs.get("nuisance_columns", ()))
            terms = [
                f"{column}_fe"
                for column in [*score_columns, *control_columns, *nuisance_columns]
                if f"{column}_fe" in model_data.columns
            ]
            feature_formula = (
                "outcome_fe ~ 0 + " + " + ".join(terms)
                if terms
                else "outcome_fe ~ 1"
            )
        elif include_keyword_fixed_effects and keyword_count >= 2:
            baseline_formula = _public_baseline_formula(keyword_count, control_columns)
            feature_formula = _multivariate_feature_formula(
                score_columns,
                keyword_count,
                control_columns,
            )
        else:
            feature_formula = _oos_feature_formula(score_columns, control_columns)

        model = smf.ols(feature_formula, data=model_data)
        if print_design:
            design_rank = np.linalg.matrix_rank(model.exog)
            print("Complete rows:", len(model_data))
            print("Signals:", len(score_columns))
            print("Keywords:", model_data["target_keyword_id"].nunique())
            print("Controls:", len(control_columns))
            print("Design columns:", model.exog.shape[1])
            print("Design rank:", design_rank)
            print("Residual df:", model.exog.shape[0] - design_rank)
        feature_result = model.fit()
        if print_design:
            print("R-squared:", feature_result.rsquared)
            print("Adjusted R-squared:", feature_result.rsquared_adj)
            print("Condition number:", feature_result.condition_number)
            print("Parameters:", feature_result.params)
            print("Standard errors:", feature_result.bse)
        if feature_result.df_resid <= 0:
            return None
        return float(feature_result.rsquared)
    except (np.linalg.LinAlgError, ValueError):
        return None


def _oos_baseline_formula(control_columns: Sequence[str]) -> str:
    controls = " + ".join(control_columns)
    if controls:
        return f"outcome ~ {controls}"
    return "outcome ~ 1"


def _oos_feature_formula(
    score_columns: Sequence[str],
    control_columns: Sequence[str],
) -> str:
    terms = " + ".join([*score_columns, *control_columns])
    return f"outcome ~ {terms}"


def _permutation_shapley_statistics(
    model_data: Any,
    factor_columns: Mapping[str, Sequence[str]],
    *,
    selected_columns: Sequence[str],
    keyword_count: int,
    control_columns: Sequence[str],
    permutations: int,
    random_state: int,
) -> dict[str, Any]:
    groups = RANKING_IMPORTANCE_GROUP_ORDER
    shapley = {group: 0.0 for group in groups}
    contributions = {group: [] for group in groups}
    selected_set = set(selected_columns)
    rng = np.random.default_rng(random_state)
    for _ in range(max(1, permutations)):
        order = list(groups)
        rng.shuffle(order)
        previous = _fit_importance_r_squared(
            model_data,
            (),
            keyword_count=keyword_count,
            control_columns=control_columns,
        )
        coalition: list[str] = []
        for group in order:
            if not any(column in selected_set for column in factor_columns[group]):
                continue
            coalition.append(group)
            columns = tuple(
                column
                for candidate in coalition
                for column in factor_columns[candidate]
                if column in selected_set
            )
            current = _fit_importance_r_squared(
                model_data,
                columns,
                keyword_count=keyword_count,
                control_columns=control_columns,
            )
            if previous is not None and current is not None:
                contribution = current - previous
                shapley[group] += contribution
                contributions[group].append(float(contribution))
            previous = current
    values = {group: value / max(1, permutations) for group, value in shapley.items()}
    half = max(1, permutations) // 2
    mcse: dict[str, float | None] = {}
    convergence: dict[str, float | None] = {}
    for group in groups:
        values_for_group = np.asarray(contributions[group], dtype=float)
        mcse[group] = (
            float(np.std(values_for_group, ddof=1) / np.sqrt(len(values_for_group)))
            if len(values_for_group) > 1
            else None
        )
        first = values_for_group[:half]
        second = values_for_group[half:]
        convergence[group] = (
            float(np.mean(first) - np.mean(second))
            if len(first) and len(second)
            else None
        )
    return {
        "values": values,
        "mcse": mcse,
        "convergence_difference": convergence,
    }


def _permutation_shapley_values(
    model_data: Any,
    factor_columns: Mapping[str, Sequence[str]],
    *,
    selected_columns: Sequence[str],
    keyword_count: int,
    control_columns: Sequence[str],
    permutations: int,
    random_state: int,
) -> dict[str, float]:
    """Return permutation-Shapley values while keeping the legacy helper surface."""

    return _permutation_shapley_statistics(
        model_data,
        factor_columns,
        selected_columns=selected_columns,
        keyword_count=keyword_count,
        control_columns=control_columns,
        permutations=permutations,
        random_state=random_state,
    )["values"]


def _prepare_oos_importance_frame(
    panel: pl.DataFrame,
    factor_columns: Mapping[str, Sequence[str]],
) -> pd.DataFrame | None:
    """Build an OOS frame that keeps null predictors for fold-local preprocessing."""

    requested = [column for columns in factor_columns.values() for column in columns]
    available = _available_predictor_columns(panel, requested)
    if not available:
        return None
    controls = [
        column
        for column in REGRESSION_CONTROL_COLUMNS
        if column in panel.columns and column not in available
    ]
    predictors = tuple([*available, *controls])
    required = ["target_keyword_id", "serp_rank", *predictors]
    if "url" in panel.columns:
        required.append("url")
    present = [column for column in required if column in panel.columns]
    frame = panel.select(present).drop_nulls(["target_keyword_id", "serp_rank"])
    if frame.height < 3:
        return None
    model_data = frame.to_pandas().copy()
    model_data["outcome"] = -np.log(model_data["serp_rank"].astype(float))
    if "url" in model_data.columns:
        model_data["domain"] = model_data["url"].map(_extract_domain)
    for column in predictors:
        if column in model_data.columns and model_data[column].dtype == bool:
            model_data[column] = model_data[column].astype(float)
    model_data.attrs["predictor_columns"] = predictors
    return model_data


def _extract_domain(url: object) -> str | None:
    if url is None or (isinstance(url, float) and np.isnan(url)):
        return None
    return get_fld(str(url).strip(), fix_protocol=True, fail_silently=True)


def _balanced_group_folds(
    groups: Sequence[object],
    *,
    n_splits: int,
    rng: np.random.Generator,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Approximate equal keyword counts per fold (e.g. 5/5/5/5/4)."""

    unique_groups = np.array(sorted(set(groups), key=str), dtype=object)
    if unique_groups.size < max(n_splits, 2):
        return []
    order = rng.permutation(unique_groups.size)
    shuffled = unique_groups[order]
    folds = [np.asarray(part, dtype=object) for part in np.array_split(shuffled, n_splits)]
    group_array = np.asarray(list(groups), dtype=object)
    splits: list[tuple[np.ndarray, np.ndarray]] = []
    for fold_groups in folds:
        test_mask = np.isin(group_array, fold_groups)
        train_idx = np.flatnonzero(~test_mask)
        test_idx = np.flatnonzero(test_mask)
        if train_idx.size == 0 or test_idx.size == 0:
            continue
        splits.append((train_idx, test_idx))
    return splits


def _pooled_r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    if y_true.size < 2:
        return None
    ss_res = float(np.sum(np.square(y_true - y_pred)))
    ss_tot = float(np.sum(np.square(y_true - np.mean(y_true))))
    if ss_tot <= 0:
        return None
    return 1.0 - ss_res / ss_tot


def _is_count_like(series: pd.Series, column: str) -> bool:
    name = column.lower()
    if name.endswith("_count") or name.endswith("_ms") or name.endswith("_size"):
        return True
    if pd.api.types.is_integer_dtype(series):
        return True
    return False


def _preprocess_fold_matrices(
    train: pd.DataFrame,
    test: pd.DataFrame,
    columns: Sequence[str],
) -> tuple[np.ndarray, np.ndarray, list[str]] | None:
    usable = [column for column in columns if column in train.columns]
    if not usable:
        return None

    train_x = train.loc[:, usable].copy()
    test_x = test.loc[:, usable].copy()

    # Near-zero variance on training fold.
    keep: list[str] = []
    for column in usable:
        values = pd.to_numeric(train_x[column], errors="coerce")
        if values.notna().sum() == 0:
            continue
        if float(values.std(skipna=True) or 0.0) <= 1e-12:
            continue
        keep.append(column)
    if not keep:
        return None
    train_x = train_x.loc[:, keep]
    test_x = test_x.loc[:, keep]

    for column in keep:
        train_col = pd.to_numeric(train_x[column], errors="coerce")
        test_col = pd.to_numeric(test_x[column], errors="coerce")
        if _is_count_like(train_col, column):
            train_col = np.log1p(train_col.clip(lower=0))
            test_col = np.log1p(test_col.clip(lower=0))
        median = float(train_col.median()) if train_col.notna().any() else 0.0
        train_x[column] = train_col.fillna(median)
        test_x[column] = test_col.fillna(median)

    # Drop exact duplicate training columns.
    deduped = train_x.T.drop_duplicates().T
    keep = list(deduped.columns)
    train_x = train_x.loc[:, keep]
    test_x = test_x.loc[:, keep]

    scaler = StandardScaler()
    train_matrix = scaler.fit_transform(train_x.to_numpy(dtype=float))
    test_matrix = scaler.transform(test_x.to_numpy(dtype=float))
    return train_matrix, test_matrix, keep


def _fit_ridge_predict(
    train: pd.DataFrame,
    train_y: np.ndarray,
    test: pd.DataFrame,
    columns: Sequence[str],
    train_groups: np.ndarray,
) -> np.ndarray | None:
    if len(train) < 3 or not columns:
        return None
    unique_groups = np.unique(train_groups)
    inner_splits = min(3, int(unique_groups.size))
    alphas = np.logspace(-2, 3, 8)
    try:
        if inner_splits >= 2:
            best_alpha = float(alphas[0])
            best_score = -np.inf
            splitter = GroupKFold(n_splits=inner_splits)
            for alpha in alphas:
                fold_scores: list[float] = []
                for inner_train, inner_valid in splitter.split(
                    train, train_y, groups=train_groups
                ):
                    prepared = _preprocess_fold_matrices(
                        train.iloc[inner_train],
                        train.iloc[inner_valid],
                        columns,
                    )
                    if prepared is None:
                        continue
                    inner_train_x, inner_valid_x, _ = prepared
                    model = Ridge(alpha=float(alpha))
                    model.fit(inner_train_x, train_y[inner_train])
                    pred = model.predict(inner_valid_x)
                    fold_scores.append(
                        -float(np.mean(np.square(train_y[inner_valid] - pred)))
                    )
                if not fold_scores:
                    continue
                mean_score = float(np.mean(fold_scores))
                if mean_score > best_score:
                    best_score = mean_score
                    best_alpha = float(alpha)
            if not np.isfinite(best_score):
                return None
            model = Ridge(alpha=best_alpha)
        else:
            model = Ridge(alpha=1.0)
        prepared = _preprocess_fold_matrices(train, test, columns)
        if prepared is None:
            return None
        train_x, test_x, _ = prepared
        model.fit(train_x, train_y)
        return np.asarray(model.predict(test_x), dtype=float)
    except (ValueError, np.linalg.LinAlgError):
        return None


def _keyword_ndcg(
    frame: pd.DataFrame,
    predictions: np.ndarray,
    *,
    k: int = 10,
    group_column: str = "target_keyword_id",
) -> float | None:
    if frame.empty or predictions.size != len(frame) or group_column not in frame.columns:
        return None
    work = frame.copy()
    work["prediction"] = predictions
    scores: list[float] = []
    for _, group in work.groupby(group_column, sort=False):
        if len(group) < 2:
            continue
        relevance = (group["serp_rank"].max() + 1 - group["serp_rank"]).to_numpy(dtype=float)
        order = np.argsort(-group["prediction"].to_numpy(dtype=float))
        ranked = relevance[order]
        cutoff = min(k, ranked.size)
        discounts = 1.0 / np.log2(np.arange(2, cutoff + 2))
        dcg = float(np.sum((np.power(2.0, ranked[:cutoff]) - 1.0) * discounts))
        ideal = np.sort(relevance)[::-1]
        idcg = float(np.sum((np.power(2.0, ideal[:cutoff]) - 1.0) * discounts))
        if idcg <= 0:
            continue
        scores.append(dcg / idcg)
    if not scores:
        return None
    return float(np.mean(scores))


def _compute_grouped_oof_importance(
    model_data: pd.DataFrame | None,
    factor_columns: Mapping[str, Sequence[str]],
    *,
    cv_folds: int = 5,
    cv_repeats: int = 3,
    random_state: int = 0,
    group_column: str = "target_keyword_id",
) -> dict[str, Any] | None:
    if model_data is None or model_data.empty:
        return None
    predictor_columns = tuple(model_data.attrs.get("predictor_columns") or ())
    if not predictor_columns:
        predictor_columns = tuple(
            column
            for columns in factor_columns.values()
            for column in columns
            if column in model_data.columns
        )
    if not predictor_columns or group_column not in model_data.columns:
        return None

    y = model_data["outcome"].to_numpy(dtype=float)
    groups = model_data[group_column].to_numpy()
    n_rows = len(model_data)
    full_pred_sum = np.zeros(n_rows, dtype=float)
    full_pred_count = np.zeros(n_rows, dtype=float)
    leave_pred_sum = {
        group: np.zeros(n_rows, dtype=float) for group in RANKING_IMPORTANCE_GROUP_ORDER
    }
    leave_pred_count = {
        group: np.zeros(n_rows, dtype=float) for group in RANKING_IMPORTANCE_GROUP_ORDER
    }

    repeat_results: list[dict[str, Any]] = []
    rng = np.random.default_rng(random_state)
    for repeat in range(max(1, cv_repeats)):
        repeat_full_sum = np.zeros(n_rows, dtype=float)
        repeat_full_count = np.zeros(n_rows, dtype=float)
        repeat_leave_sum = {
            group: np.zeros(n_rows, dtype=float)
            for group in RANKING_IMPORTANCE_GROUP_ORDER
        }
        repeat_leave_count = {
            group: np.zeros(n_rows, dtype=float)
            for group in RANKING_IMPORTANCE_GROUP_ORDER
        }
        repeat_rng = np.random.default_rng(int(rng.integers(0, 2**31 - 1)))
        splits = _balanced_group_folds(groups, n_splits=cv_folds, rng=repeat_rng)
        for train_idx, test_idx in splits:
            train = model_data.iloc[train_idx]
            test = model_data.iloc[test_idx]
            train_y = y[train_idx]
            train_groups = groups[train_idx]

            preds = _fit_ridge_predict(
                train,
                train_y,
                test,
                predictor_columns,
                train_groups,
            )
            if preds is None:
                continue
            full_pred_sum[test_idx] += preds
            full_pred_count[test_idx] += 1.0
            repeat_full_sum[test_idx] += preds
            repeat_full_count[test_idx] += 1.0

            for group in RANKING_IMPORTANCE_GROUP_ORDER:
                without = tuple(
                    column
                    for column in predictor_columns
                    if column not in factor_columns[group]
                )
                leave_preds = _fit_ridge_predict(
                    train,
                    train_y,
                    test,
                    without,
                    train_groups,
                )
                if leave_preds is None:
                    continue
                leave_pred_sum[group][test_idx] += leave_preds
                leave_pred_count[group][test_idx] += 1.0
                repeat_leave_sum[group][test_idx] += leave_preds
                repeat_leave_count[group][test_idx] += 1.0

        repeat_result = _summarize_oof_predictions(
            model_data,
            y,
            repeat_full_sum,
            repeat_full_count,
            repeat_leave_sum,
            repeat_leave_count,
            factor_columns,
        )
        if repeat_result is not None:
            repeat_result["repeat"] = repeat
            repeat_results.append(repeat_result)

    covered = full_pred_count > 0
    if not np.any(covered):
        return None
    full_pred = np.divide(
        full_pred_sum,
        np.maximum(full_pred_count, 1.0),
    )
    y_covered = y[covered]
    full_r2 = _pooled_r_squared(y_covered, full_pred[covered])
    ndcg_full = _keyword_ndcg(model_data.loc[covered], full_pred[covered])

    group_results: dict[str, dict[str, Any]] = {}
    for group in RANKING_IMPORTANCE_GROUP_ORDER:
        leave_covered = leave_pred_count[group] > 0
        mask = covered & leave_covered
        if not np.any(mask):
            group_results[group] = {
                "full_r2": full_r2,
                "reduced_r2": None,
                "delta_r2": None,
                "ndcg_full": ndcg_full,
                "ndcg_reduced": None,
                "ndcg_delta": None,
                **_repeat_summary([], "delta_r2"),
                **_repeat_summary([], "ndcg_delta"),
            }
            continue
        leave_pred = np.divide(
            leave_pred_sum[group],
            np.maximum(leave_pred_count[group], 1.0),
        )
        reduced_r2 = _pooled_r_squared(y[mask], leave_pred[mask])
        ndcg_reduced = _keyword_ndcg(model_data.loc[mask], leave_pred[mask])
        # Recompute full R² on the same mask for an apples-to-apples delta.
        full_on_mask = _pooled_r_squared(y[mask], full_pred[mask])
        ndcg_full_on_mask = _keyword_ndcg(model_data.loc[mask], full_pred[mask])
        delta = (
            None
            if full_on_mask is None or reduced_r2 is None
            else float(full_on_mask - reduced_r2)
        )
        ndcg_delta = (
            None
            if ndcg_full_on_mask is None or ndcg_reduced is None
            else float(ndcg_full_on_mask - ndcg_reduced)
        )
        group_results[group] = {
            "full_r2": full_on_mask,
            "reduced_r2": reduced_r2,
            "delta_r2": delta,
            "ndcg_full": ndcg_full_on_mask,
            "ndcg_reduced": ndcg_reduced,
            "ndcg_delta": ndcg_delta,
            "oof_predictions": pd.DataFrame(
                {
                    "target_keyword_id": model_data.loc[mask, "target_keyword_id"].to_numpy(),
                    "serp_rank": model_data.loc[mask, "serp_rank"].to_numpy(),
                    "outcome": y[mask],
                    "full_prediction": full_pred[mask],
                    "reduced_prediction": leave_pred[mask],
                    **({"domain": model_data.loc[mask, "domain"].to_numpy()} if "domain" in model_data else {}),
                }
            ),
        }

        repeat_deltas = [
            result["groups"].get(group, {}).get("delta_r2")
            for result in repeat_results
            if result["groups"].get(group, {}).get("delta_r2") is not None
        ]
        repeat_ndcg_deltas = [
            result["groups"].get(group, {}).get("ndcg_delta")
            for result in repeat_results
            if result["groups"].get(group, {}).get("ndcg_delta") is not None
        ]
        group_results[group].update(
            _repeat_summary(repeat_deltas, "delta_r2"),
            **_repeat_summary(repeat_ndcg_deltas, "ndcg_delta"),
        )

    return {
        "full_r2": full_r2,
        "ndcg_full": ndcg_full,
        "row_count": int(np.count_nonzero(covered)),
        "group_count": int(model_data.loc[covered, group_column].nunique()),
        "repeat_results": repeat_results,
        "groups": group_results,
    }


def _summarize_oof_predictions(
    model_data: pd.DataFrame,
    y: np.ndarray,
    full_pred_sum: np.ndarray,
    full_pred_count: np.ndarray,
    leave_pred_sum: Mapping[str, np.ndarray],
    leave_pred_count: Mapping[str, np.ndarray],
    factor_columns: Mapping[str, Sequence[str]],
) -> dict[str, Any] | None:
    covered = full_pred_count > 0
    if not np.any(covered):
        return None
    full_pred = np.divide(full_pred_sum, np.maximum(full_pred_count, 1.0))
    group_results: dict[str, dict[str, Any]] = {}
    for group in RANKING_IMPORTANCE_GROUP_ORDER:
        mask = covered & (leave_pred_count[group] > 0)
        if not np.any(mask):
            group_results[group] = {"delta_r2": None, "ndcg_delta": None}
            continue
        reduced_pred = np.divide(
            leave_pred_sum[group], np.maximum(leave_pred_count[group], 1.0)
        )
        full_r2 = _pooled_r_squared(y[mask], full_pred[mask])
        reduced_r2 = _pooled_r_squared(y[mask], reduced_pred[mask])
        full_ndcg = _keyword_ndcg(model_data.loc[mask], full_pred[mask])
        reduced_ndcg = _keyword_ndcg(model_data.loc[mask], reduced_pred[mask])
        group_results[group] = {
            "delta_r2": None if full_r2 is None or reduced_r2 is None else full_r2 - reduced_r2,
            "ndcg_delta": None if full_ndcg is None or reduced_ndcg is None else full_ndcg - reduced_ndcg,
            "oof_predictions": pd.DataFrame(
                {
                    "target_keyword_id": model_data.loc[mask, "target_keyword_id"].to_numpy(),
                    "serp_rank": model_data.loc[mask, "serp_rank"].to_numpy(),
                    "outcome": y[mask],
                    "full_prediction": full_pred[mask],
                    "reduced_prediction": reduced_pred[mask],
                    **({"domain": model_data.loc[mask, "domain"].to_numpy()} if "domain" in model_data else {}),
                }
            ),
        }
    return {
        "full_r2": _pooled_r_squared(y[covered], full_pred[covered]),
        "ndcg_full": _keyword_ndcg(model_data.loc[covered], full_pred[covered]),
        "groups": group_results,
    }


def _repeat_summary(values: Sequence[float], metric: str) -> dict[str, float | None]:
    if not values:
        return {
            f"repeat_mean_{metric}": None,
            f"repeat_sd_{metric}": None,
            f"repeat_min_{metric}": None,
            f"repeat_max_{metric}": None,
        }
    array = np.asarray(values, dtype=float)
    return {
        f"repeat_mean_{metric}": float(np.mean(array)),
        f"repeat_sd_{metric}": float(np.std(array, ddof=0)),
        f"repeat_min_{metric}": float(np.min(array)),
        f"repeat_max_{metric}": float(np.max(array)),
    }


def _bootstrap_oos_delta_ci(
    oof_result: Mapping[str, Any] | None,
    *,
    bootstraps: int,
    random_state: int,
    sample_column: str = "target_keyword_id",
    alpha: float = 0.05,
) -> dict[str, dict[str, dict[str, float | None]]]:
    empty_interval = {
        "point": None,
        "lower": None,
        "upper": None,
        "level": 1.0 - alpha,
    }
    empty = {
        group: {"delta_r2": dict(empty_interval), "ndcg_delta": dict(empty_interval)}
        for group in RANKING_IMPORTANCE_GROUP_ORDER
    }
    if oof_result is None or bootstraps < 1:
        return empty

    rng = np.random.default_rng(random_state)
    intervals: dict[str, dict[str, dict[str, float | None]]] = {}
    lower_q = alpha / 2.0
    upper_q = 1.0 - alpha / 2.0
    for group in RANKING_IMPORTANCE_GROUP_ORDER:
        repeat_frames = [
            result.get("groups", {}).get(group, {}).get("oof_predictions")
            for result in oof_result.get("repeat_results", [])
        ]
        repeat_frames = [frame for frame in repeat_frames if isinstance(frame, pd.DataFrame) and not frame.empty]
        frame = oof_result.get("groups", {}).get(group, {}).get("oof_predictions")
        if not repeat_frames and isinstance(frame, pd.DataFrame) and not frame.empty:
            repeat_frames = [frame]
        if not repeat_frames:
            intervals[group] = empty[group]
            continue
        if any(sample_column not in candidate.columns for candidate in repeat_frames):
            intervals[group] = empty[group]
            continue
        r2_deltas: list[float] = []
        ndcg_deltas: list[float] = []
        for _ in range(bootstraps):
            frame = repeat_frames[int(rng.integers(0, len(repeat_frames)))]
            units = frame[sample_column].dropna().unique().tolist()
            if len(units) < 2:
                continue
            drawn = rng.choice(units, size=len(units), replace=True)
            sampled_parts = []
            for copy_index, unit in enumerate(drawn):
                part = frame[frame[sample_column] == unit].copy()
                if sample_column == "target_keyword_id":
                    part["_bootstrap_keyword_copy_id"] = copy_index
                sampled_parts.append(part)
            sampled = pd.concat(sampled_parts, ignore_index=True)
            full_r2 = _pooled_r_squared(
                sampled["outcome"].to_numpy(dtype=float),
                sampled["full_prediction"].to_numpy(dtype=float),
            )
            reduced_r2 = _pooled_r_squared(
                sampled["outcome"].to_numpy(dtype=float),
                sampled["reduced_prediction"].to_numpy(dtype=float),
            )
            if full_r2 is not None and reduced_r2 is not None:
                r2_deltas.append(float(full_r2 - reduced_r2))
            ndcg_full = _keyword_ndcg(
                sampled,
                sampled["full_prediction"].to_numpy(dtype=float),
                group_column=("_bootstrap_keyword_copy_id" if sample_column == "target_keyword_id" else "target_keyword_id"),
            )
            ndcg_reduced = _keyword_ndcg(
                sampled,
                sampled["reduced_prediction"].to_numpy(dtype=float),
                group_column=("_bootstrap_keyword_copy_id" if sample_column == "target_keyword_id" else "target_keyword_id"),
            )
            if ndcg_full is not None and ndcg_reduced is not None:
                ndcg_deltas.append(float(ndcg_full - ndcg_reduced))
        intervals[group] = {
            metric: (
                {
                    "point": float(np.mean(values)),
                    "lower": float(np.quantile(values, lower_q)),
                    "upper": float(np.quantile(values, upper_q)),
                    "level": 1.0 - alpha,
                }
                if values
                else dict(empty_interval)
            )
            for metric, values in (("delta_r2", r2_deltas), ("ndcg_delta", ndcg_deltas))
        }
    return intervals


def _domain_holdout_oof_importance(
    model_data: pd.DataFrame | None,
    factor_columns: Mapping[str, Sequence[str]],
    *,
    random_state: int,
    cv_repeats: int,
) -> dict[str, Any] | None:
    if model_data is None or "domain" not in model_data.columns:
        return None
    valid_domains = model_data["domain"].dropna()
    domain_count = int(valid_domains.nunique())
    if domain_count < 4:
        return None
    valid_model_data = model_data.dropna(subset=["domain"])
    cv_folds = min(5, domain_count)
    result = _compute_grouped_oof_importance(
        valid_model_data,
        factor_columns,
        cv_folds=cv_folds,
        cv_repeats=cv_repeats,
        random_state=random_state,
        group_column="domain",
    )
    if result is None:
        return None
    result.update(
        {
            "domain_rows": int(len(valid_model_data)),
            "domain_count": domain_count,
            "domain_rows_with_extraction_failure": int(model_data["domain"].isna().sum()),
            "domains_per_fold": [
                int(len(fold))
                for fold in np.array_split(sorted(valid_domains.unique()), cv_folds)
            ],
        }
    )
    return result


def _metadata_only_oof_importance(
    model_data: pd.DataFrame | None,
    factor_columns: Mapping[str, Sequence[str]],
    *,
    cv_folds: int,
    cv_repeats: int,
    random_state: int,
) -> dict[str, Any] | None:
    if model_data is None:
        return None
    columns = tuple(
        column
        for column in (*factor_columns["metadata_lengths"], *REGRESSION_CONTROL_COLUMNS)
        if column in model_data.columns
    )
    if not columns:
        return None
    metadata_data = model_data.copy()
    metadata_data.attrs["predictor_columns"] = columns
    empty_groups = {group: () for group in RANKING_IMPORTANCE_GROUP_ORDER}
    empty_groups["metadata_lengths"] = factor_columns["metadata_lengths"]
    return _compute_grouped_oof_importance(
        metadata_data,
        empty_groups,
        cv_folds=cv_folds,
        cv_repeats=cv_repeats,
        random_state=random_state,
    )


def _metric_relative_importance_rows(
    model_data: Any,
    *,
    group: str,
    group_columns: Sequence[str],
    selected_columns: Sequence[str],
    keyword_count: int,
    control_columns: Sequence[str],
    full_r2: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column in group_columns:
        if column not in selected_columns:
            continue
        without_columns = tuple(
            selected_column
            for selected_column in selected_columns
            if selected_column != column
        )
        without_r2 = _fit_importance_r_squared(
            model_data,
            without_columns,
            keyword_count=keyword_count,
            control_columns=control_columns,
        )
        partial_r2 = (
            _partial_r_squared(full_r2, without_r2)
            if without_r2 is not None
            else None
        )
        rows.append(
            {
                "factor": column,
                "column": column,
                "full_model_partial_r2": partial_r2,
                "shapley_share": None,
                "out_of_sample_delta_r2": None,
                "clustered_ci": None,
            }
        )
    return rows
