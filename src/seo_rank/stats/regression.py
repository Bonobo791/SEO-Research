"""Phase 5 pooled regression helpers."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import polars as pl
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.regression.linear_model import RegressionResultsWrapper
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups


SIMILARITY_SCORE_COLUMNS = {
    "bge": "bge_normalized_score",
    "gemini_doc_retrieval": "gemini_doc_retrieval_normalized_score",
    "gemini_semantic_similarity": "gemini_semantic_similarity_normalized_score",
}
BASELINE_FORMULA = "outcome ~ np.log(page_text_length + 1) + C(target_keyword_id)"
REGRESSION_REQUIRED_COLUMNS = ("serp_rank", "page_text_length")


def summarize_regression_backends(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
) -> dict[str, object]:
    """Summarize the pooled regression path for each configured backend."""

    return {
        "backends": {
            backend: summarize_backend_regression(analysis_mart, backend=backend)
            for backend in backend_order
        }
    }


def summarize_backend_regression(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
) -> dict[str, object]:
    """Fit the baseline and univariate pooled models for one backend."""

    score_column = _score_column_for_backend(backend)
    model_frame = _prepare_regression_frame(analysis_mart, score_column)
    if model_frame.is_empty():
        return _skipped_backend_summary(backend=backend, score_column=score_column)

    model_data = model_frame.to_pandas().copy()
    model_data["outcome"] = -np.log(model_data["serp_rank"].astype(float))

    baseline_result = smf.ols(BASELINE_FORMULA, data=model_data).fit()
    feature_formula = (
        f"outcome ~ {score_column} + np.log(page_text_length + 1) + C(target_keyword_id)"
    )
    feature_result = smf.ols(feature_formula, data=model_data).fit()
    clustered_result = feature_result.get_robustcov_results(
        cov_type="cluster",
        groups=model_data["target_keyword_id"],
    )

    coefficient = _parameter_value(clustered_result, score_column)
    clustered_standard_error = _parameter_standard_error(clustered_result, score_column)
    clustered_confidence_interval = _parameter_confidence_interval(
        clustered_result, score_column
    )
    similarity_sd = float(model_data[score_column].std(ddof=1))
    median_rank = float(np.median(model_data["serp_rank"].astype(float)))

    return {
        "backend": backend,
        "score_column": score_column,
        "row_count": int(len(model_data)),
        "keyword_count": int(model_data["target_keyword_id"].nunique()),
        "baseline_model": {
            "formula": BASELINE_FORMULA,
            "adjusted_r_squared": float(baseline_result.rsquared_adj),
            "aic": float(baseline_result.aic),
        },
        "feature_model": {
            "formula": feature_formula,
            "coefficient": coefficient,
            "clustered_standard_error": clustered_standard_error,
            "clustered_confidence_interval": clustered_confidence_interval,
            "p_value": _parameter_p_value(clustered_result, score_column),
            "adjusted_r_squared": float(feature_result.rsquared_adj),
            "aic": float(feature_result.aic),
            "covariance": {
                "type": "cluster",
                "clusters": ["target_keyword_id"],
            },
        },
        "descriptive_fit_delta": {
            "adjusted_r_squared": float(feature_result.rsquared_adj - baseline_result.rsquared_adj),
            "aic": float(feature_result.aic - baseline_result.aic),
        },
        "effect_size": {
            "formula": "median_rank * (exp(-(coefficient * similarity_sd)) - 1)",
            "similarity_sd": similarity_sd,
            "median_rank": median_rank,
            "delta_log_rank_per_1sd": float(coefficient * similarity_sd),
            "approximate_delta_rank_per_1sd": float(
                median_rank * (np.exp(-(coefficient * similarity_sd)) - 1.0)
            ),
        },
        "sensitivity": {
            "two_way_cluster": _two_way_cluster_sensitivity(
                feature_result=feature_result,
                model_data=model_data,
                parameter=score_column,
            )
        },
    }


def _score_column_for_backend(backend: str) -> str:
    try:
        return SIMILARITY_SCORE_COLUMNS[backend]
    except KeyError as exc:
        raise ValueError(f"unsupported backend {backend}") from exc


def _prepare_regression_frame(
    analysis_mart: pl.DataFrame,
    score_column: str,
) -> pl.DataFrame:
    return analysis_mart.filter(pl.col(score_column).is_not_null()).drop_nulls(
        [score_column, *REGRESSION_REQUIRED_COLUMNS]
    )


def _skipped_backend_summary(
    *,
    backend: str,
    score_column: str,
) -> dict[str, object]:
    return {
        "backend": backend,
        "score_column": score_column,
        "status": "skipped",
        "skipped_reason": "no_usable_rows",
        "row_count": 0,
        "keyword_count": 0,
    }


def _parameter_index(result: RegressionResultsWrapper, parameter: str) -> int:
    return list(result.model.exog_names).index(parameter)


def _parameter_value(result: RegressionResultsWrapper, parameter: str) -> float:
    index = _parameter_index(result, parameter)
    return float(np.asarray(result.params)[index])


def _parameter_standard_error(result: RegressionResultsWrapper, parameter: str) -> float:
    index = _parameter_index(result, parameter)
    return float(np.asarray(result.bse)[index])


def _parameter_confidence_interval(
    result: RegressionResultsWrapper,
    parameter: str,
) -> list[float]:
    index = _parameter_index(result, parameter)
    interval = result.conf_int(alpha=0.05)[index]
    return [float(interval[0]), float(interval[1])]


def _parameter_p_value(result: RegressionResultsWrapper, parameter: str) -> float:
    index = _parameter_index(result, parameter)
    return float(np.asarray(result.pvalues)[index])


def _two_way_cluster_sensitivity(
    *,
    feature_result: RegressionResultsWrapper,
    model_data,
    parameter: str,
) -> dict[str, object]:
    repeated_url_count = int(model_data["canonical_url_hash"].duplicated().sum())
    if repeated_url_count == 0:
        return {
            "status": "skipped",
            "reason": "no_repeated_urls",
            "clusters": ["target_keyword_id", "canonical_url_hash"],
        }

    keyword_codes = model_data["target_keyword_id"].astype("category").cat.codes.to_numpy()
    url_codes = model_data["canonical_url_hash"].astype("category").cat.codes.to_numpy()
    covariance, _, _ = cov_cluster_2groups(feature_result, keyword_codes, url_codes)
    parameter_index = _parameter_index(feature_result, parameter)
    standard_error = float(np.sqrt(covariance[parameter_index, parameter_index]))
    coefficient = _parameter_value(feature_result, parameter)
    degrees_of_freedom = max(
        1,
        min(
            int(model_data["target_keyword_id"].nunique()),
            int(model_data["canonical_url_hash"].nunique()),
        )
        - 1,
    )
    critical_value = float(stats.t.ppf(0.975, degrees_of_freedom))
    return {
        "status": "computed",
        "clusters": ["target_keyword_id", "canonical_url_hash"],
        "coefficient": coefficient,
        "standard_error": standard_error,
        "confidence_interval": [
            float(coefficient - (critical_value * standard_error)),
            float(coefficient + (critical_value * standard_error)),
        ],
    }
