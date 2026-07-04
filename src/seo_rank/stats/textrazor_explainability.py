"""TextRazor metric explainability for SERP rank."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import statsmodels.formula.api as smf

from seo_rank.stats.artifacts import build_family_source_frames
from seo_rank.stats.panel import build_limitations_for_rank_depth, load_analysis_panel
from seo_rank.stats.rank_depth import filter_panel_by_max_rank
from seo_rank.stats.regression import (
    BASELINE_FORMULA,
    REGRESSION_REQUIRED_COLUMNS,
    SINGLE_KEYWORD_BASELINE_FORMULA,
    summarize_regression_for_score_column,
    _inference_metadata,
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

TEXTRAZOR_SCORE_COLUMNS: tuple[str, ...] = tuple(
    column for _, column in TEXTRAZOR_RANKING_METRICS
)

OUTCOME_DESCRIPTION = "-log(serp_rank)"


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


def summarize_textrazor_ranking_explainability(
    panel: pl.DataFrame,
    *,
    run_id: str,
    rank_depth: str,
    spec: AnalysisSpec | None = None,
    limitations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Summarize univariate and multivariate adjusted R² for TextRazor metrics."""

    analysis_spec = spec or load_analysis_spec()
    resolved_limitations = limitations or build_limitations_for_rank_depth(
        analysis_spec,
        rank_depth,
    )
    keyword_count = (
        int(panel["target_keyword_id"].n_unique()) if not panel.is_empty() else 0
    )
    univariate = [
        _summarize_univariate_metric(panel, label=label, score_column=column)
        for label, column in TEXTRAZOR_RANKING_METRICS
    ]
    multivariate = _summarize_multivariate_metrics(panel)

    return {
        "run_id": run_id,
        "rank_depth": rank_depth,
        "estimand": {
            "outcome": OUTCOME_DESCRIPTION,
            "baseline_formula": _public_baseline_formula(keyword_count),
        },
        "panel": {
            "rows": panel.height,
            "keywords": keyword_count,
            "metric_coverage": _metric_coverage(panel),
        },
        "univariate": univariate,
        "multivariate": multivariate,
        "limitations": resolved_limitations,
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


def _metric_coverage(panel: pl.DataFrame) -> dict[str, dict[str, int]]:
    total = panel.height
    coverage: dict[str, dict[str, int]] = {}
    for _, column in TEXTRAZOR_RANKING_METRICS:
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


def _summarize_multivariate_metrics(panel: pl.DataFrame) -> dict[str, Any]:
    model_frame = _prepare_multivariate_frame(panel)
    if model_frame.is_empty():
        return {
            "status": "skipped",
            "skipped_reason": "no_usable_rows",
            "row_count": 0,
            "keyword_count": 0,
            "score_columns": list(TEXTRAZOR_SCORE_COLUMNS),
        }
    if model_frame.height < 3:
        return {
            "status": "skipped",
            "skipped_reason": "insufficient_rows",
            "row_count": model_frame.height,
            "keyword_count": int(model_frame["target_keyword_id"].n_unique()),
            "score_columns": list(TEXTRAZOR_SCORE_COLUMNS),
        }

    model_data = model_frame.to_pandas().copy()
    keyword_count = int(model_data["target_keyword_id"].nunique())
    model_data["outcome"] = -np.log(model_data["serp_rank"].astype(float))

    if keyword_count >= 2:
        baseline_formula = BASELINE_FORMULA
        feature_formula = _multivariate_feature_formula(keyword_count)
        baseline_result = smf.ols(baseline_formula, data=model_data).fit()
        feature_result = smf.ols(feature_formula, data=model_data).fit()
        if feature_result.df_resid <= 0:
            return {
                "status": "skipped",
                "skipped_reason": "non_positive_residual_df",
                "row_count": model_frame.height,
                "keyword_count": keyword_count,
                "score_columns": list(TEXTRAZOR_SCORE_COLUMNS),
            }
        clustered_result = feature_result.get_robustcov_results(
            cov_type="cluster",
            groups=model_data["target_keyword_id"],
        )
    else:
        baseline_formula = SINGLE_KEYWORD_BASELINE_FORMULA
        feature_formula = _multivariate_feature_formula(keyword_count)
        baseline_result = smf.ols(baseline_formula, data=model_data).fit()
        feature_result = smf.ols(feature_formula, data=model_data).fit()
        if feature_result.df_resid <= 0:
            return {
                "status": "skipped",
                "skipped_reason": "non_positive_residual_df",
                "row_count": model_frame.height,
                "keyword_count": keyword_count,
                "score_columns": list(TEXTRAZOR_SCORE_COLUMNS),
            }
        clustered_result = feature_result.get_robustcov_results(cov_type="HC3")

    coefficients = {
        column: _parameter_value(clustered_result, column)
        for column in TEXTRAZOR_SCORE_COLUMNS
    }
    p_values = {
        column: _parameter_p_value(clustered_result, column)
        for column in TEXTRAZOR_SCORE_COLUMNS
    }

    return {
        "status": "computed",
        "row_count": model_frame.height,
        "keyword_count": keyword_count,
        "score_columns": list(TEXTRAZOR_SCORE_COLUMNS),
        "baseline_model": {
            "formula": _public_baseline_formula(keyword_count),
            "adjusted_r_squared": float(baseline_result.rsquared_adj),
        },
        "feature_model": {
            "formula": feature_formula,
            "coefficients": coefficients,
            "p_values": p_values,
            "adjusted_r_squared": float(feature_result.rsquared_adj),
            "covariance": _inference_metadata(keyword_count),
        },
        "descriptive_fit_delta": {
            "adjusted_r_squared": float(
                feature_result.rsquared_adj - baseline_result.rsquared_adj
            ),
        },
    }


def _prepare_multivariate_frame(panel: pl.DataFrame) -> pl.DataFrame:
    required = [*TEXTRAZOR_SCORE_COLUMNS, *REGRESSION_REQUIRED_COLUMNS]
    present = [column for column in required if column in panel.columns]
    if len(present) != len(required):
        return pl.DataFrame()
    return panel.drop_nulls(required)


def _multivariate_feature_formula(keyword_count: int) -> str:
    terms = " + ".join(TEXTRAZOR_SCORE_COLUMNS)
    if keyword_count >= 2:
        return f"outcome ~ {terms} + np.log(page_text_length + 1) + C(target_keyword_id)"
    return f"outcome ~ {terms} + np.log(page_text_length + 1)"
