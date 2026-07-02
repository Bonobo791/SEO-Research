"""Phase 5 pooled regression helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Sequence

import numpy as np
import polars as pl
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from seo_rank.stats.scale import within_keyword_sd_rms
from statsmodels.regression.linear_model import RegressionResultsWrapper
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups


logger = logging.getLogger(__name__)

SIMILARITY_SCORE_COLUMNS = {
    "bge": "bge_normalized_score",
    "gemini_doc_retrieval": "gemini_doc_retrieval_normalized_score",
    "gemini_semantic_similarity": "gemini_semantic_similarity_normalized_score",
}
BASELINE_FORMULA = "outcome ~ np.log(page_text_length + 1) + C(target_keyword_id)"
SINGLE_KEYWORD_BASELINE_FORMULA = "outcome ~ np.log(page_text_length + 1)"
REGRESSION_REQUIRED_COLUMNS = ("serp_rank", "page_text_length")


@dataclass(frozen=True)
class BackendRegressionFit:
    backend: str
    score_column: str
    baseline_formula: str
    feature_formula: str
    model_data: pd.DataFrame
    baseline_result: RegressionResultsWrapper
    feature_result: RegressionResultsWrapper
    clustered_result: RegressionResultsWrapper
    similarity_within_keyword_sd: float


def summarize_regression_backends(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
) -> dict[str, object]:
    """Summarize the pooled regression path for each configured backend."""

    logger.info("summarizing regression backends=%s", list(backend_order))
    fits = fit_regression_backends(analysis_mart, backend_order)
    return summarize_regression_backends_from_fits(
        analysis_mart,
        backend_order,
        fits=fits,
    )


def fit_regression_backends(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
) -> dict[str, BackendRegressionFit | None]:
    """Fit the pooled regression path once per backend."""

    return {
        backend: fit_backend_regression(analysis_mart, backend=backend)
        for backend in backend_order
    }


def summarize_backend_regression(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
) -> dict[str, object]:
    """Fit the baseline and univariate pooled models for one backend."""

    fit = fit_backend_regression(analysis_mart, backend=backend)
    return _summarize_backend_regression_result(
        analysis_mart,
        backend=backend,
        fit=fit,
    )


def summarize_regression_backends_from_fits(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
    *,
    fits: dict[str, BackendRegressionFit | None],
) -> dict[str, object]:
    """Summarize the pooled regression path from precomputed fits."""

    return {
        "backends": {
            backend: _summarize_backend_regression_result(
                analysis_mart,
                backend=backend,
                fit=fits.get(backend),
            )
            for backend in backend_order
        }
    }


def _summarize_backend_regression_result(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
    fit: BackendRegressionFit | None,
) -> dict[str, object]:
    if fit is None:
        score_column = _score_column_for_backend(backend)
        model_frame = _prepare_regression_frame(analysis_mart, score_column)
        skipped_reason = _regression_skip_reason(model_frame)
        row_count = model_frame.height
        keyword_count = (
            model_frame["target_keyword_id"].n_unique() if not model_frame.is_empty() else 0
        )
        logger.info(
            "regression backend=%s status=skipped skipped_reason=%s row_count=%d keyword_count=%d",
            backend,
            skipped_reason,
            row_count,
            keyword_count,
        )
        return _skipped_backend_summary(
            backend=backend,
            score_column=score_column,
            skipped_reason=skipped_reason,
            row_count=row_count,
            keyword_count=keyword_count,
        )

    keyword_count = int(fit.model_data["target_keyword_id"].nunique())
    inference = _inference_metadata(keyword_count)
    similarity_sd = float(fit.similarity_within_keyword_sd)
    coefficient = _parameter_value(
        fit.clustered_result,
        fit.score_column,
    )
    clustered_confidence_interval = _parameter_confidence_interval(
        fit.clustered_result,
        fit.score_column,
    )
    clustered_standard_error = _parameter_standard_error(
        fit.clustered_result,
        fit.score_column,
    )
    median_rank = float(np.median(fit.model_data["serp_rank"].astype(float)))

    logger.info(
        "regression backend=%s status=computed row_count=%d keyword_count=%d",
        fit.backend,
        len(fit.model_data),
        keyword_count,
    )

    return {
        "backend": fit.backend,
        "score_column": fit.score_column,
        "row_count": int(len(fit.model_data)),
        "keyword_count": keyword_count,
        "baseline_model": {
            "formula": _public_baseline_formula(keyword_count),
            "adjusted_r_squared": float(fit.baseline_result.rsquared_adj),
            "aic": float(fit.baseline_result.aic),
        },
        "feature_model": {
            "formula": _public_feature_formula(fit.score_column, keyword_count),
            "coefficient": coefficient,
            "clustered_standard_error": clustered_standard_error,
            "clustered_confidence_interval": clustered_confidence_interval,
            "p_value": _parameter_p_value(fit.clustered_result, fit.score_column),
            "adjusted_r_squared": float(fit.feature_result.rsquared_adj),
            "aic": float(fit.feature_result.aic),
            "covariance": inference,
        },
        "descriptive_fit_delta": {
            "adjusted_r_squared": float(
                fit.feature_result.rsquared_adj - fit.baseline_result.rsquared_adj
            ),
            "aic": float(fit.feature_result.aic - fit.baseline_result.aic),
        },
        "effect_size": {
            "formula": "median_rank * (exp(-(coefficient * similarity_sd)) - 1)",
            "similarity_sd": similarity_sd,
            "median_rank": median_rank,
            "approximate_delta_rank_per_1sd": float(
                median_rank * (np.exp(-(coefficient * similarity_sd)) - 1.0)
            ),
        },
        "sensitivity": {
            "two_way_cluster": _two_way_cluster_sensitivity(
                feature_result=fit.feature_result,
                model_data=fit.model_data,
            )
        },
    }


def fit_backend_regression(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
) -> BackendRegressionFit | None:
    logger.debug("fitting regression backend=%s", backend)
    score_column = _score_column_for_backend(backend)
    model_frame = _prepare_regression_frame(analysis_mart, score_column)
    if model_frame.is_empty():
        logger.debug("regression backend=%s skipped: no usable rows", backend)
        return None

    model_data = model_frame.to_pandas().copy()
    keyword_count = int(model_data["target_keyword_id"].nunique())
    if keyword_count < 1:
        logger.debug("regression backend=%s skipped: no keywords", backend)
        return None

    similarity_within_keyword_sd = within_keyword_sd_rms(model_data, score_column)
    model_data["outcome"] = -np.log(model_data["serp_rank"].astype(float))

    if keyword_count >= 2:
        baseline_formula = BASELINE_FORMULA
        feature_formula = _public_feature_formula(score_column, keyword_count)
        baseline_result = smf.ols(baseline_formula, data=model_data).fit()
        feature_result = smf.ols(feature_formula, data=model_data).fit()
        if feature_result.df_resid <= 0:
            logger.debug("regression backend=%s skipped: non-positive residual df", backend)
            return None
        clustered_result = feature_result.get_robustcov_results(
            cov_type="cluster",
            groups=model_data["target_keyword_id"],
        )
    else:
        baseline_formula = SINGLE_KEYWORD_BASELINE_FORMULA
        feature_formula = _public_feature_formula(score_column, keyword_count)
        baseline_result = smf.ols(baseline_formula, data=model_data).fit()
        feature_result = smf.ols(feature_formula, data=model_data).fit()
        if feature_result.df_resid <= 0:
            logger.debug("regression backend=%s skipped: non-positive residual df", backend)
            return None
        clustered_result = feature_result.get_robustcov_results(cov_type="HC3")

    return BackendRegressionFit(
        backend=backend,
        score_column=score_column,
        baseline_formula=baseline_formula,
        feature_formula=feature_formula,
        model_data=model_data,
        baseline_result=baseline_result,
        feature_result=feature_result,
        clustered_result=clustered_result,
        similarity_within_keyword_sd=similarity_within_keyword_sd,
    )


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


def _regression_skip_reason(model_frame: pl.DataFrame) -> str:
    if model_frame.is_empty():
        return "no_usable_rows"
    if model_frame.height < 3:
        return "insufficient_rows"
    return "no_usable_rows"


def _inference_metadata(keyword_count: int) -> dict[str, object]:
    if keyword_count >= 2:
        return {
            "type": "cluster",
            "clusters": ["target_keyword_id"],
        }
    return {
        "type": "HC3",
        "clusters": [],
    }


def _skipped_backend_summary(
    *,
    backend: str,
    score_column: str,
    skipped_reason: str = "no_usable_rows",
    row_count: int = 0,
    keyword_count: int = 0,
) -> dict[str, object]:
    return {
        "backend": backend,
        "score_column": score_column,
        "status": "skipped",
        "skipped_reason": skipped_reason,
        "row_count": row_count,
        "keyword_count": keyword_count,
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
    score_column = feature_result.model.exog_names[1]
    parameter_index = _parameter_index(feature_result, score_column)
    coefficient = _parameter_value(feature_result, score_column)
    standard_error = float(np.sqrt(max(covariance[parameter_index, parameter_index], 0.0)))
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


def _public_baseline_formula(keyword_count: int) -> str:
    if keyword_count >= 2:
        return BASELINE_FORMULA
    return SINGLE_KEYWORD_BASELINE_FORMULA


def _public_feature_formula(score_column: str, keyword_count: int) -> str:
    if keyword_count >= 2:
        return f"outcome ~ {score_column} + np.log(page_text_length + 1) + C(target_keyword_id)"
    return f"outcome ~ {score_column} + np.log(page_text_length + 1)"
