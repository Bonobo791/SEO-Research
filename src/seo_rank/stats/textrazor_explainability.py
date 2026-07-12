"""Ranking explainability summaries for similarity and TextRazor metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.formula.api as smf

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
    "technical",
    "content",
)

_RANKING_IMPORTANCE_FAMILY_KEYS: dict[str, tuple[str, ...]] = {
    "similarity": (),
    "textrazor": (),
    "backlinks": ("backlinks_counts",),
    "technical": ("onpage_core_web_vitals", "onpage_technical_checks"),
    "content": ("onpage_content_quality",),
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
        if group == "similarity":
            family_keys = spec.signal_families.similarity_keys
        elif group == "textrazor":
            family_keys = spec.signal_families.textrazor_keys
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
    bootstraps: int = 500,
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
            "bootstraps": bootstraps,
            "excluded_predictors": [],
            "groups": [],
        }

    model_data = prepared["model_data"]
    selected_columns = prepared["selected_columns"]
    keyword_count = prepared["keyword_count"]
    control_columns = prepared["control_columns"]
    rng = np.random.default_rng(random_state)

    full_r2 = _fit_importance_r_squared(
        model_data,
        selected_columns,
        keyword_count=keyword_count,
        control_columns=control_columns,
    )
    if full_r2 is None:
        return {
            "status": "skipped",
            "skipped_reason": "full_model_not_fitted",
            "row_count": prepared["row_count"],
            "keyword_count": keyword_count,
            "cv_folds": cv_folds,
            "bootstraps": bootstraps,
            "excluded_predictors": prepared.get("excluded_predictors", []),
            "groups": [],
        }

    coalition_cache = _build_coalition_r_squared_cache(
        model_data,
        factor_columns,
        selected_columns=selected_columns,
        keyword_count=keyword_count,
        control_columns=control_columns,
    )
    shapley_values = _shapley_r_squared_values(
        RANKING_IMPORTANCE_GROUP_ORDER,
        coalition_cache,
    )
    shapley_total = sum(shapley_values.values())
    oos_deltas = _keyword_grouped_cv_delta_r2(
        model_data,
        factor_columns,
        selected_columns=selected_columns,
        control_columns=control_columns,
        cv_folds=cv_folds,
        rng=rng,
    )
    bootstrap_cis = _bootstrap_group_partial_r2_ci(
        model_data,
        factor_columns,
        selected_columns=selected_columns,
        control_columns=control_columns,
        bootstraps=bootstraps,
        rng=rng,
    )

    groups: list[dict[str, Any]] = []
    for group in RANKING_IMPORTANCE_GROUP_ORDER:
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
            if without_r2 is not None
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
        ci = bootstrap_cis.get(group) or {}
        if isinstance(ci, dict) and partial_r2 is not None:
            ci = {**ci, "point": partial_r2}
        groups.append(
            {
                "factor": group,
                "full_model_partial_r2": partial_r2,
                "shapley_share": shapley_share,
                "out_of_sample_delta_r2": oos_deltas.get(group),
                "clustered_ci": ci,
                "metrics": metric_rows,
            }
        )

    return {
        "status": "computed",
        "row_count": prepared["row_count"],
        "keyword_count": keyword_count,
        "cv_folds": cv_folds,
        "bootstraps": bootstraps,
        "predictor_columns": list(selected_columns),
        "excluded_predictors": prepared.get("excluded_predictors", []),
        "full_model_r_squared": full_r2,
        "oos_note": (
            "Out-of-sample delta R² uses keyword-grouped CV and omits keyword "
            "fixed effects when predicting held-out keywords."
        ),
        "groups": groups,
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

    target_rows = _resolve_min_complete_rows(panel.height, min_complete_rows)
    selected_columns, excluded_predictors = _drop_sparse_importance_predictors(
        panel,
        available_columns,
        min_complete_rows=target_rows,
    )
    if not selected_columns:
        return None

    required = [
        "target_keyword_id",
        *REGRESSION_REQUIRED_COLUMNS,
        *[
            column
            for column in REGRESSION_CONTROL_COLUMNS
            if column in panel.columns
        ],
        *selected_columns,
    ]
    present = [column for column in required if column in panel.columns]
    model_frame = panel.select(present).drop_nulls(present)
    if model_frame.height < 3:
        return None

    model_data = model_frame.to_pandas().copy()
    model_data["outcome"] = -np.log(model_data["serp_rank"].astype(float))
    for column in selected_columns:
        if column in model_data.columns and model_data[column].dtype == bool:
            model_data[column] = model_data[column].astype(float)

    keyword_count = int(model_data["target_keyword_id"].nunique())
    control_columns = tuple(
        column
        for column in REGRESSION_CONTROL_COLUMNS
        if column in model_data.columns and not model_data[column].isna().any()
    )
    return {
        "model_data": model_data,
        "selected_columns": selected_columns,
        "excluded_predictors": excluded_predictors,
        "keyword_count": keyword_count,
        "control_columns": control_columns,
        "row_count": model_frame.height,
    }


def _resolve_min_complete_rows(panel_height: int, min_complete_rows: int | None) -> int:
    if min_complete_rows is not None:
        return max(3, int(min_complete_rows))
    # Keep enough rows for keyword-FE OLS without requiring a perfect join across
    # sparse onpage/backlinks fields. Analysis-only; never mutates parquet.
    return max(3, min(panel_height, max(30, panel_height // 4)))


def _drop_sparse_importance_predictors(
    panel: pl.DataFrame,
    columns: Sequence[str],
    *,
    min_complete_rows: int,
) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    """Drop sparsest predictors until complete-case rows meet the floor.

    Operates on the in-memory RI panel only — source marts are untouched.
    """

    selected = list(columns)
    excluded: list[dict[str, str]] = []

    def _complete_count(cols: Sequence[str]) -> int:
        if not cols:
            return panel.height
        return panel.select(list(cols)).drop_nulls(list(cols)).height

    while selected and _complete_count(selected) < min_complete_rows:
        null_counts = [
            (column, int(panel[column].null_count()))
            for column in selected
        ]
        null_counts.sort(key=lambda item: (-item[1], item[0]))
        worst_column, _ = null_counts[0]
        if int(panel[worst_column].null_count()) == 0:
            # No sparse columns left; cannot reach the floor by dropping.
            break
        selected.remove(worst_column)
        excluded.append(
            {
                "column": worst_column,
                "reason": "sparse_complete_case",
            }
        )

    if _complete_count(selected) < 3:
        return (), excluded
    return tuple(selected), excluded


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



def _fit_importance_r_squared(
    model_data: Any,
    score_columns: Sequence[str],
    *,
    keyword_count: int,
    control_columns: Sequence[str],
    include_keyword_fixed_effects: bool = True,
) -> float | None:
    try:
        if include_keyword_fixed_effects and keyword_count >= 2:
            baseline_formula = _public_baseline_formula(keyword_count, control_columns)
            feature_formula = _multivariate_feature_formula(
                score_columns,
                keyword_count,
                control_columns,
            )
        else:
            baseline_formula = _oos_baseline_formula(control_columns)
            feature_formula = _oos_feature_formula(score_columns, control_columns)
        feature_result = smf.ols(feature_formula, data=model_data).fit()
        if feature_result.df_resid <= 0:
            return None
        if feature_result.nobs <= feature_result.model.exog.shape[1]:
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


def _build_coalition_r_squared_cache(
    model_data: Any,
    factor_columns: Mapping[str, Sequence[str]],
    *,
    selected_columns: Sequence[str],
    keyword_count: int,
    control_columns: Sequence[str],
) -> dict[frozenset[str], float | None]:
    from itertools import combinations

    cache: dict[frozenset[str], float | None] = {}
    groups = RANKING_IMPORTANCE_GROUP_ORDER
    for size in range(len(groups) + 1):
        for subset in combinations(groups, size):
            coalition = frozenset(subset)
            coalition_columns = _columns_for_groups(
                factor_columns,
                selected_columns,
                subset,
            )
            cache[coalition] = _fit_importance_r_squared(
                model_data,
                coalition_columns,
                keyword_count=keyword_count,
                control_columns=control_columns,
            )
    return cache


def _columns_for_groups(
    factor_columns: Mapping[str, Sequence[str]],
    selected_columns: Sequence[str],
    groups: Sequence[str],
) -> tuple[str, ...]:
    selected_set = set(selected_columns)
    columns: list[str] = []
    for group in groups:
        for column in factor_columns[group]:
            if column in selected_set:
                columns.append(column)
    return tuple(columns)


def _shapley_r_squared_values(
    groups: Sequence[str],
    coalition_cache: Mapping[frozenset[str], float | None],
) -> dict[str, float]:
    from itertools import combinations
    from math import factorial

    player_count = len(groups)
    shapley = {group: 0.0 for group in groups}
    for player in groups:
        others = [group for group in groups if group != player]
        for coalition_size in range(len(others) + 1):
            for subset in combinations(others, coalition_size):
                coalition = frozenset(subset)
                with_player = frozenset(set(subset) | {player})
                without_value = coalition_cache.get(coalition)
                with_value = coalition_cache.get(with_player)
                if without_value is None or with_value is None:
                    continue
                weight = (
                    factorial(coalition_size)
                    * factorial(player_count - coalition_size - 1)
                    / factorial(player_count)
                )
                shapley[player] += weight * (with_value - without_value)
    return shapley


def _keyword_grouped_cv_delta_r2(
    model_data: Any,
    factor_columns: Mapping[str, Sequence[str]],
    *,
    selected_columns: Sequence[str],
    control_columns: Sequence[str],
    cv_folds: int,
    rng: np.random.Generator,
) -> dict[str, float | None]:
    keywords = sorted(model_data["target_keyword_id"].unique())
    if len(keywords) < max(cv_folds, 2):
        return {group: None for group in RANKING_IMPORTANCE_GROUP_ORDER}

    shuffled = list(keywords)
    rng.shuffle(shuffled)
    fold_size = max(1, len(shuffled) // cv_folds)
    group_deltas: dict[str, list[float]] = {
        group: [] for group in RANKING_IMPORTANCE_GROUP_ORDER
    }

    for fold_index in range(cv_folds):
        start = fold_index * fold_size
        end = len(shuffled) if fold_index == cv_folds - 1 else (fold_index + 1) * fold_size
        test_keywords = set(shuffled[start:end])
        if not test_keywords:
            continue
        train_mask = ~model_data["target_keyword_id"].isin(test_keywords)
        test_mask = model_data["target_keyword_id"].isin(test_keywords)
        train = model_data.loc[train_mask]
        test = model_data.loc[test_mask]
        if train.empty or test.empty:
            continue

        full_r2 = _eval_oos_r_squared(
            train,
            test,
            selected_columns,
            control_columns=control_columns,
        )
        if full_r2 is None:
            continue
        for group in RANKING_IMPORTANCE_GROUP_ORDER:
            without_columns = _columns_without_group(
                selected_columns,
                factor_columns[group],
            )
            without_r2 = _eval_oos_r_squared(
                train,
                test,
                without_columns,
                control_columns=control_columns,
            )
            if without_r2 is None:
                continue
            # Out-of-sample column is advertised as ΔR², not partial R².
            group_deltas[group].append(float(full_r2 - without_r2))

    return {
        group: float(np.mean(deltas)) if deltas else None
        for group, deltas in group_deltas.items()
    }


def _eval_oos_r_squared(
    train: Any,
    test: Any,
    score_columns: Sequence[str],
    *,
    control_columns: Sequence[str],
) -> float | None:
    try:
        formula = _oos_feature_formula(score_columns, control_columns)
        result = smf.ols(formula, data=train).fit()
        if result.df_resid <= 0:
            return None
        predictions = result.predict(test)
        outcome = -np.log(test["serp_rank"].astype(float))
        residuals = outcome - predictions
        ss_res = float(np.sum(np.square(residuals)))
        ss_tot = float(np.sum(np.square(outcome - outcome.mean())))
        if ss_tot <= 0:
            return None
        return 1.0 - ss_res / ss_tot
    except (np.linalg.LinAlgError, ValueError, TypeError):
        return None


def _bootstrap_group_partial_r2_ci(
    model_data: Any,
    factor_columns: Mapping[str, Sequence[str]],
    *,
    selected_columns: Sequence[str],
    control_columns: Sequence[str],
    bootstraps: int,
    rng: np.random.Generator,
    alpha: float = 0.05,
) -> dict[str, dict[str, float | None]]:
    keywords = model_data["target_keyword_id"].unique().tolist()
    if not keywords:
        return {
            group: {"point": None, "lower": None, "upper": None, "level": 1.0 - alpha}
            for group in RANKING_IMPORTANCE_GROUP_ORDER
        }

    samples: dict[str, list[float]] = {
        group: [] for group in RANKING_IMPORTANCE_GROUP_ORDER
    }
    for _ in range(bootstraps):
        drawn = rng.choice(keywords, size=len(keywords), replace=True)
        boot_frames = [model_data[model_data["target_keyword_id"] == keyword] for keyword in drawn]
        boot_data = pd.concat(boot_frames, ignore_index=True)
        keyword_count = int(boot_data["target_keyword_id"].nunique())
        full_r2 = _fit_importance_r_squared(
            boot_data,
            selected_columns,
            keyword_count=keyword_count,
            control_columns=control_columns,
        )
        if full_r2 is None:
            continue
        for group in RANKING_IMPORTANCE_GROUP_ORDER:
            without_columns = _columns_without_group(
                selected_columns,
                factor_columns[group],
            )
            without_r2 = _fit_importance_r_squared(
                boot_data,
                without_columns,
                keyword_count=keyword_count,
                control_columns=control_columns,
            )
            if without_r2 is None:
                continue
            partial = _partial_r_squared(full_r2, without_r2)
            if partial is not None:
                samples[group].append(float(partial))

    intervals: dict[str, dict[str, float | None]] = {}
    lower_q = alpha / 2.0
    upper_q = 1.0 - alpha / 2.0
    for group in RANKING_IMPORTANCE_GROUP_ORDER:
        values = samples[group]
        if not values:
            intervals[group] = {
                "point": None,
                "lower": None,
                "upper": None,
                "level": 1.0 - alpha,
            }
            continue
        intervals[group] = {
            "point": float(np.mean(values)),
            "lower": float(np.quantile(values, lower_q)),
            "upper": float(np.quantile(values, upper_q)),
            "level": 1.0 - alpha,
        }
    return intervals


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
