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
from seo_rank.stats.families import SignalFamily, SignalFamilyRegistry, source_mart_for_family
from seo_rank.stats.model_inputs import (
    REQUIRED_CONTROL_COLUMNS,
    control_error_summary,
    validate_control_columns,
)
from seo_rank.stats.rank_depth import filter_panel_by_max_rank
from seo_rank.stats.scale import within_keyword_sd_rms
from seo_rank.stats.spec import AnalysisSpec
from statsmodels.regression.linear_model import RegressionResultsWrapper
from statsmodels.stats.sandwich_covariance import cov_cluster_2groups


logger = logging.getLogger(__name__)

SIMILARITY_SCORE_COLUMNS = {
    "bge": "bge_normalized_score",
    "gemini_doc_retrieval": "gemini_doc_retrieval_normalized_score",
    "gemini_semantic_similarity": "gemini_semantic_similarity_normalized_score",
}
REGRESSION_CONTROL_COLUMNS = REQUIRED_CONTROL_COLUMNS
BASELINE_FORMULA = "outcome ~ site_scale + C(target_keyword_id)"
REGRESSION_REQUIRED_COLUMNS = ("serp_rank",)


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
    fitted_control_columns: tuple[str, ...]
    omitted_controls: tuple[dict[str, str], ...]


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


def summarize_regression_families(
    source_frames: dict[str, pl.DataFrame],
    *,
    registry: SignalFamilyRegistry,
) -> dict[str, object]:
    """Summarize the pooled regression path for every family in the registry."""

    return {
        "families": {
            family.key: summarize_regression_family(
                source_frames,
                family=family,
            )
            for family in registry.families
        }
    }


def fit_regression_backends(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
) -> dict[str, BackendRegressionFit | None]:
    """Fit the pooled regression path once per backend."""

    return {
        backend: fit_backend_regression(analysis_mart, backend=backend)
        for backend in backend_order
    }


def summarize_regression_rank_depths(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
    *,
    depth_order: Sequence[str],
    spec: AnalysisSpec,
) -> dict[str, object]:
    """Summarize pooled regression for every confirmatory rank depth."""

    logger.info("summarizing regression rank_depths=%s", list(depth_order))
    depths: dict[str, object] = {}
    for depth_key in depth_order:
        depth_mart = filter_panel_by_max_rank(
            analysis_mart,
            max_rank=spec.rank_depth_limit(depth_key),
        )
        fits = fit_regression_backends(depth_mart, backend_order)
        depths[depth_key] = summarize_regression_backends_from_fits(
            depth_mart,
            backend_order,
            fits=fits,
        )
    return {
        "depth_order": list(depth_order),
        "depths": depths,
    }


def fit_regression_rank_depths(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
    *,
    depth_order: Sequence[str],
    spec: AnalysisSpec,
) -> dict[str, dict[str, BackendRegressionFit | None]]:
    """Fit pooled regression once per backend at each confirmatory rank depth."""

    fits_by_depth: dict[str, dict[str, BackendRegressionFit | None]] = {}
    for depth_key in depth_order:
        depth_mart = filter_panel_by_max_rank(
            analysis_mart,
            max_rank=spec.rank_depth_limit(depth_key),
        )
        fits_by_depth[depth_key] = fit_regression_backends(depth_mart, backend_order)
    return fits_by_depth


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


def summarize_regression_for_score_column(
    analysis_mart: pl.DataFrame,
    *,
    label: str,
    score_column: str,
) -> dict[str, object]:
    """Fit and summarize the pooled regression path for an arbitrary signal column."""

    fit = fit_regression_for_score_column(
        analysis_mart,
        label=label,
        score_column=score_column,
    )
    summary = _summarize_backend_regression_result(
        analysis_mart,
        backend=label,
        fit=fit,
        score_column=score_column,
    )
    if summary.get("status") in {"skipped", "error"}:
        return summary
    summary["status"] = "computed"
    return summary


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


def summarize_regression_family(
    source_frames: dict[str, pl.DataFrame],
    *,
    family: SignalFamily,
) -> dict[str, object]:
    """Summarize the pooled regression path for one signal family."""

    source_mart = source_mart_for_family(family)
    source_frame = source_frames.get(source_mart)
    if source_frame is None or source_frame.is_empty():
        return {
            "family": family.key,
            "kind": family.kind,
            "source_mart": source_mart,
            "signal_columns": list(family.signal_columns),
            "signals": {},
            "backends": {},
            "status": "skipped",
            "skipped_reason": "no_usable_rows",
        }

    signal_summaries: dict[str, dict[str, object]] = {}
    for signal_column in family.signal_columns:
        signal_summaries[signal_column] = summarize_regression_for_score_column(
            source_frame,
            label=family.key,
            score_column=signal_column,
        )
    status = (
        "computed"
        if any(summary.get("status") != "skipped" for summary in signal_summaries.values())
        else "skipped"
    )
    family_summary: dict[str, object] = {
        "family": family.key,
        "kind": family.kind,
        "source_mart": source_mart,
        "signal_columns": list(family.signal_columns),
        "signals": signal_summaries,
        "backends": signal_summaries,
        "status": status,
    }
    if status == "skipped":
        family_summary["skipped_reason"] = "no_usable_rows"
    return family_summary


def _summarize_backend_regression_result(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
    fit: BackendRegressionFit | None,
    score_column: str | None = None,
) -> dict[str, object]:
    if fit is None:
        if score_column is None:
            score_column = _score_column_for_backend(backend)
        model_frame = _prepare_regression_frame(analysis_mart, score_column)
        invalid_controls = (
            validate_control_columns(model_frame.to_pandas())
            if not model_frame.is_empty()
            else ()
        )
        if invalid_controls:
            return control_error_summary(
                backend=backend,
                score_column=score_column,
                invalid_controls=invalid_controls,
                row_count=model_frame.height,
                keyword_count=model_frame["target_keyword_id"].n_unique(),
            )
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
    if _resolve_parameter_name(fit.clustered_result, fit.score_column) is None:
        logger.info(
            "regression backend=%s status=skipped skipped_reason=parameter_not_estimable score_column=%s",
            fit.backend,
            fit.score_column,
        )
        return _skipped_backend_summary(
            backend=fit.backend,
            score_column=fit.score_column,
            skipped_reason="parameter_not_estimable",
            row_count=int(len(fit.model_data)),
            keyword_count=keyword_count,
        )
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
        "status": "computed",
        "row_count": int(len(fit.model_data)),
        "keyword_count": keyword_count,
        "omitted_controls": [dict(control) for control in fit.omitted_controls],
        "baseline_model": {
            "formula": fit.baseline_formula,
            "adjusted_r_squared": float(fit.baseline_result.rsquared_adj),
            "aic": float(fit.baseline_result.aic),
        },
        "feature_model": {
            "formula": fit.feature_formula,
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
    return fit_regression_for_score_column(
        analysis_mart,
        label=backend,
        score_column=_score_column_for_backend(backend),
    )


def fit_regression_for_score_column(
    analysis_mart: pl.DataFrame,
    *,
    label: str,
    score_column: str,
) -> BackendRegressionFit | None:
    logger.debug("fitting regression backend=%s", label)
    model_frame = _prepare_regression_frame(analysis_mart, score_column)
    if model_frame.is_empty():
        logger.debug("regression backend=%s skipped: no usable rows", label)
        return None

    model_data = model_frame.to_pandas().copy()
    keyword_count = int(model_data["target_keyword_id"].nunique())
    if keyword_count < 1:
        logger.debug("regression backend=%s skipped: no keywords", label)
        return None

    fit = _fit_backend_regression_from_model_data(
        model_data,
        label=label,
        score_column=score_column,
    )
    if fit is None:
        logger.debug("regression backend=%s skipped: non-positive residual df", label)
        return None
    return fit


def _score_column_for_backend(backend: str) -> str:
    try:
        return SIMILARITY_SCORE_COLUMNS[backend]
    except KeyError as exc:
        raise ValueError(f"unsupported backend {backend}") from exc


def _fit_backend_regression_from_model_data(
    model_data: pd.DataFrame,
    *,
    label: str,
    score_column: str,
) -> BackendRegressionFit | None:
    model_data = model_data.copy()
    _coerce_regression_predictor(model_data, score_column)
    keyword_count = int(model_data["target_keyword_id"].nunique())
    if keyword_count < 1:
        return None

    invalid_controls = validate_control_columns(model_data, REGRESSION_CONTROL_COLUMNS)
    if invalid_controls:
        logger.info(
            "regression backend=%s status=error invalid_controls=%s",
            label,
            list(invalid_controls),
        )
        return None

    fitted_control_columns, omitted_controls = _select_regression_controls(model_data)

    similarity_within_keyword_sd = within_keyword_sd_rms(model_data, score_column)
    model_data["outcome"] = -np.log(model_data["serp_rank"].astype(float))

    if keyword_count >= 2:
        feature_formula = _public_feature_formula(
            score_column,
            keyword_count,
            fitted_control_columns,
        )
        baseline_formula = _public_baseline_formula(
            keyword_count,
            fitted_control_columns,
        )
        baseline_result = smf.ols(baseline_formula, data=model_data).fit()
        feature_result = smf.ols(feature_formula, data=model_data).fit()
        if feature_result.df_resid <= 0:
            return None
        # df_resid uses matrix rank, but statsmodels' cluster-robust small-sample
        # correction divides by (nobs - raw exog column count). A column-rank-
        # deficient design (e.g. tied predictor values within a keyword group)
        # can leave df_resid > 0 while nobs <= exog.shape[1], causing a
        # ZeroDivisionError inside get_robustcov_results.
        if feature_result.nobs <= feature_result.model.exog.shape[1]:
            return None
        clustered_result = feature_result.get_robustcov_results(
            cov_type="cluster",
            groups=model_data["target_keyword_id"],
        )
    else:
        baseline_formula = _public_baseline_formula(
            keyword_count,
            fitted_control_columns,
        )
        feature_formula = _public_feature_formula(
            score_column,
            keyword_count,
            fitted_control_columns,
        )
        baseline_result = smf.ols(baseline_formula, data=model_data).fit()
        feature_result = smf.ols(feature_formula, data=model_data).fit()
        if feature_result.df_resid <= 0:
            return None
        clustered_result = feature_result.get_robustcov_results(cov_type="HC3")

    return BackendRegressionFit(
        backend=label,
        score_column=score_column,
        baseline_formula=baseline_formula,
        feature_formula=feature_formula,
        model_data=model_data,
        baseline_result=baseline_result,
        feature_result=feature_result,
        clustered_result=clustered_result,
        similarity_within_keyword_sd=similarity_within_keyword_sd,
        fitted_control_columns=fitted_control_columns,
        omitted_controls=omitted_controls,
    )


def _prepare_regression_frame(
    analysis_mart: pl.DataFrame,
    score_column: str,
) -> pl.DataFrame:
    return analysis_mart.filter(pl.col(score_column).is_not_null()).drop_nulls(
        [score_column, *REGRESSION_REQUIRED_COLUMNS, "target_keyword_id"]
    )


def _regression_skip_reason(model_frame: pl.DataFrame) -> str:
    if model_frame.is_empty():
        return "no_usable_rows"
    if model_frame.height < 3:
        return "insufficient_rows"
    return "insufficient_design"


def _select_regression_controls(
    model_data: pd.DataFrame,
) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    fitted_controls: list[str] = []
    omitted_controls: list[dict[str, str]] = []
    for column in REGRESSION_CONTROL_COLUMNS:
        if column not in model_data.columns:
            omitted_controls.append({"column": column, "reason": "missing_column"})
        elif model_data[column].isna().any():
            omitted_controls.append({"column": column, "reason": "missing_values"})
        else:
            fitted_controls.append(column)
    return tuple(fitted_controls), tuple(omitted_controls)


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


def _coerce_regression_predictor(model_data: pd.DataFrame, score_column: str) -> None:
    """Treat boolean predictors as 0/1 floats so patsy keeps the raw column name."""

    if pd.api.types.is_bool_dtype(model_data[score_column]):
        model_data[score_column] = model_data[score_column].astype(float)


def _resolve_parameter_name(
    result: RegressionResultsWrapper,
    parameter: str,
) -> str | None:
    exog_names = list(result.model.exog_names)
    if parameter in exog_names:
        return parameter
    categorical_name = f"{parameter}[T.True]"
    if categorical_name in exog_names:
        return categorical_name
    return None


def _parameter_index(result: RegressionResultsWrapper, parameter: str) -> int:
    resolved = _resolve_parameter_name(result, parameter)
    if resolved is None:
        raise ValueError(f"parameter {parameter!r} not in regression design matrix")
    return list(result.model.exog_names).index(resolved)


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


def _public_baseline_formula(
    keyword_count: int,
    control_columns: Sequence[str] = REGRESSION_CONTROL_COLUMNS,
) -> str:
    controls = _regression_control_formula_terms(control_columns)
    fixed_effect = " + C(target_keyword_id)" if keyword_count >= 2 else ""
    return f"outcome ~ {controls or '1'}{fixed_effect}"


def _public_feature_formula(
    score_column: str,
    keyword_count: int,
    control_columns: Sequence[str] = REGRESSION_CONTROL_COLUMNS,
) -> str:
    controls = _regression_control_formula_terms(control_columns)
    fixed_effect = " + C(target_keyword_id)" if keyword_count >= 2 else ""
    terms = " + ".join(filter(None, [score_column, controls]))
    return f"outcome ~ {terms}{fixed_effect}"


def _regression_control_formula_terms(control_columns: Sequence[str]) -> str:
    return " + ".join(control_columns)
