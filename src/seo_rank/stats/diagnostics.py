"""Phase 5 diagnostics helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import polars as pl
from scipy import stats
from statsmodels.stats.diagnostic import het_breuschpagan, linear_reset

from seo_rank.stats.regression import (
    BackendRegressionFit,
    _regression_skip_reason,
    fit_regression_backends,
    fit_backend_regression,
)

SMALL_SAMPLE_SHAPIRO_CUTOFF = 50
RESET_P_VALUE_THRESHOLD = 0.05
BREUSCH_PAGAN_P_VALUE_THRESHOLD = 0.05
STUDENTIZED_RESIDUAL_THRESHOLD = 3.0


def summarize_diagnostics_backends(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
) -> dict[str, object]:
    """Summarize pooled OLS diagnostics for every configured backend."""

    fits = fit_regression_backends(analysis_mart, backend_order)
    return summarize_diagnostics_backends_from_fits(
        analysis_mart,
        backend_order,
        fits=fits,
    )


def summarize_diagnostics_backends_from_fits(
    analysis_mart: pl.DataFrame,
    backend_order: Sequence[str],
    *,
    fits: dict[str, BackendRegressionFit | None],
) -> dict[str, object]:
    """Summarize pooled OLS diagnostics from precomputed backend fits."""

    return {
        "backend_order": list(backend_order),
        "backends": {
            backend: _summarize_backend_diagnostics_result(
                analysis_mart,
                backend=backend,
                fit=fits.get(backend),
            )
            for backend in backend_order
        },
    }


def summarize_backend_diagnostics(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
) -> dict[str, object]:
    """Summarize pooled diagnostics for one backend."""

    fit = fit_backend_regression(analysis_mart, backend=backend)
    return _summarize_backend_diagnostics_result(
        analysis_mart,
        backend=backend,
        fit=fit,
    )


def _summarize_backend_diagnostics_result(
    analysis_mart: pl.DataFrame,
    *,
    backend: str,
    fit: BackendRegressionFit | None,
) -> dict[str, object]:
    if fit is None:
        score_column = _score_column_for_backend(backend)
        model_frame = analysis_mart.filter(pl.col(score_column).is_not_null()).drop_nulls(
            [score_column, "serp_rank", "page_text_length"]
        )
        skipped_reason = _regression_skip_reason(model_frame)
        return _skipped_backend_summary(
            backend=backend,
            score_column=score_column,
            skipped_reason=skipped_reason,
            row_count=model_frame.height,
            keyword_count=model_frame["target_keyword_id"].n_unique()
            if not model_frame.is_empty()
            else 0,
        )
    return summarize_backend_diagnostics_from_fit(fit)


def summarize_backend_diagnostics_from_fit(
    fit: BackendRegressionFit,
) -> dict[str, object]:
    """Summarize pooled diagnostics from a prepared backend regression fit."""

    residuals = np.asarray(fit.feature_result.resid, dtype=float)
    fitted = np.asarray(fit.feature_result.fittedvalues, dtype=float)
    nobs = int(fit.feature_result.nobs)
    parameter_count = len(fit.feature_result.model.exog_names)
    influence = fit.feature_result.get_influence()

    cooks_d = np.asarray(influence.cooks_distance[0], dtype=float)
    leverage = np.asarray(influence.hat_matrix_diag, dtype=float)
    studentized = np.asarray(influence.resid_studentized_external, dtype=float)
    dffits = np.asarray(influence.dffits[0], dtype=float)
    dfbetas = np.asarray(influence.dfbetas, dtype=float)

    cooks_d_threshold = 4.0 / nobs
    leverage_threshold = (2.0 * parameter_count) / nobs
    dffits_threshold = 2.0 * math.sqrt(parameter_count / nobs)
    dfbeta_threshold = 2.0 / math.sqrt(nobs)

    row_flags = (
        (cooks_d > cooks_d_threshold)
        | (leverage > leverage_threshold)
        | (np.abs(studentized) > STUDENTIZED_RESIDUAL_THRESHOLD)
        | (np.abs(dffits) > dffits_threshold)
        | (np.abs(dfbetas).max(axis=1) > dfbeta_threshold)
    )
    influential_rows = [
        _row_influence_summary(
            fit=fit,
            row_index=row_index,
            cooks_d=float(cooks_d[row_index]),
            leverage=float(leverage[row_index]),
            studentized_residual=float(studentized[row_index]),
            dffits=float(dffits[row_index]),
            dfbetas=dfbetas[row_index],
            cooks_d_threshold=cooks_d_threshold,
            leverage_threshold=leverage_threshold,
            dffits_threshold=dffits_threshold,
            dfbeta_threshold=dfbeta_threshold,
        )
        for row_index in np.flatnonzero(row_flags)
    ]

    reset_result = linear_reset(
        fit.feature_result,
        power=2,
        use_f=True,
        cov_type="nonrobust",
    )
    breusch_pagan = het_breuschpagan(
        residuals,
        fit.feature_result.model.exog,
        robust=True,
    )
    shapiro = _shapiro_summary(residuals)

    return {
        "backend": fit.backend,
        "score_column": fit.score_column,
        "status": "computed",
        "row_count": nobs,
        "keyword_count": int(fit.model_data["target_keyword_id"].nunique()),
        "model_formula": fit.feature_result.model.formula,
        "baseline_formula": fit.baseline_result.model.formula,
        "residuals_vs_fitted": _residuals_vs_fitted_summary(residuals, fitted),
        "reset": {
            "status": "computed",
            "statistic": _finite_float(reset_result.statistic),
            "p_value": _finite_float(reset_result.pvalue),
            "df_denom": _finite_float(getattr(reset_result, "df_denom", None)),
            "flagged": _finite_float(reset_result.pvalue) is not None
            and _finite_float(reset_result.pvalue) < RESET_P_VALUE_THRESHOLD,
        },
        "breusch_pagan": _breusch_pagan_summary(
            breusch_pagan,
            flagged=_breusch_pagan_flagged(breusch_pagan),
        ),
        "influence": {
            "status": "computed",
            "row_count": nobs,
            "nobs": nobs,
            "parameter_count": parameter_count,
            "cook_d_threshold": cooks_d_threshold,
            "leverage_threshold": leverage_threshold,
            "studentized_residual_threshold": STUDENTIZED_RESIDUAL_THRESHOLD,
            "dffits_threshold": dffits_threshold,
            "dfbeta_threshold": dfbeta_threshold,
            "cook_d_count": int(np.sum(cooks_d > cooks_d_threshold)),
            "leverage_count": int(np.sum(leverage > leverage_threshold)),
            "studentized_residual_count": int(
                np.sum(np.abs(studentized) > STUDENTIZED_RESIDUAL_THRESHOLD)
            ),
            "dffits_count": int(np.sum(np.abs(dffits) > dffits_threshold)),
            "dfbeta_count": int(np.sum(np.abs(dfbetas).max(axis=1) > dfbeta_threshold)),
            "influential_count": int(len(influential_rows)),
            "influential_rate": float(len(influential_rows) / nobs),
            "rows": influential_rows,
        },
    } | ({"shapiro": shapiro} if shapiro is not None else {})


def _residuals_vs_fitted_summary(
    residuals: np.ndarray,
    fitted: np.ndarray,
) -> dict[str, object]:
    pearson = stats.pearsonr(fitted, residuals)
    spearman = stats.spearmanr(fitted, residuals)
    return {
        "status": "computed",
        "pearson_r": _finite_float(pearson.statistic),
        "pearson_p_value": _finite_float(pearson.pvalue),
        "spearman_r": _finite_float(spearman.statistic),
        "spearman_p_value": _finite_float(spearman.pvalue),
        "residual_mean": _finite_float(np.mean(residuals)),
        "residual_sd": _finite_float(np.std(residuals, ddof=1)),
        "fitted_mean": _finite_float(np.mean(fitted)),
        "fitted_sd": _finite_float(np.std(fitted, ddof=1)),
    }


def _breusch_pagan_summary(
    breusch_pagan: tuple[float, float, float, float],
    *,
    flagged: bool,
) -> dict[str, object]:
    lm_statistic, lm_p_value, f_statistic, f_p_value = breusch_pagan
    return {
        "status": "computed",
        "lm_statistic": _finite_float(lm_statistic),
        "lm_p_value": _finite_float(lm_p_value),
        "f_statistic": _finite_float(f_statistic),
        "f_p_value": _finite_float(f_p_value),
        "flagged": flagged,
        "recommended_se_type": "HC3" if flagged else "clustered",
    }


def _breusch_pagan_flagged(breusch_pagan: tuple[float, float, float, float]) -> bool:
    lm_statistic, lm_p_value, f_statistic, f_p_value = breusch_pagan
    del lm_statistic, f_statistic
    return any(
        p_value is not None and p_value < BREUSCH_PAGAN_P_VALUE_THRESHOLD
        for p_value in (_finite_float(lm_p_value), _finite_float(f_p_value))
    )


def _row_influence_summary(
    *,
    fit: BackendRegressionFit,
    row_index: int,
    cooks_d: float,
    leverage: float,
    studentized_residual: float,
    dffits: float,
    dfbetas: np.ndarray,
    cooks_d_threshold: float,
    leverage_threshold: float,
    dffits_threshold: float,
    dfbeta_threshold: float,
) -> dict[str, object]:
    row = fit.model_data.iloc[row_index]
    parameter_names = list(fit.feature_result.model.exog_names)
    dfbeta_series = [
        {
            "parameter": parameter_name,
            "value": _finite_float(dfbeta_value),
            "flagged": abs(float(dfbeta_value)) > dfbeta_threshold,
        }
        for parameter_name, dfbeta_value in zip(parameter_names, dfbetas, strict=True)
    ]
    return {
        "row_index": int(row_index),
        "target_keyword_id": _json_value(row.get("target_keyword_id")),
        "canonical_url_hash": _json_value(row.get("canonical_url_hash")),
        "cooks_d": cooks_d,
        "leverage": leverage,
        "studentized_residual": studentized_residual,
        "dffits": dffits,
        "max_abs_dfbeta": _finite_float(np.max(np.abs(dfbetas))),
        "dfbetas": dfbeta_series,
        "flags": {
            "cooks_d": cooks_d > cooks_d_threshold,
            "leverage": leverage > leverage_threshold,
            "studentized_residual": abs(studentized_residual) > STUDENTIZED_RESIDUAL_THRESHOLD,
            "dffits": abs(dffits) > dffits_threshold,
            "dfbeta": bool(np.max(np.abs(dfbetas)) > dfbeta_threshold),
        },
    }


def _shapiro_summary(residuals: np.ndarray) -> dict[str, object] | None:
    if residuals.size >= SMALL_SAMPLE_SHAPIRO_CUTOFF:
        return {
            "status": "skipped",
            "skipped_reason": "nobs_gte_50",
            "nobs_cutoff": SMALL_SAMPLE_SHAPIRO_CUTOFF,
        }
    statistic, p_value = stats.shapiro(residuals)
    return {
        "status": "informational",
        "statistic": _finite_float(statistic),
        "p_value": _finite_float(p_value),
        "nobs_cutoff": SMALL_SAMPLE_SHAPIRO_CUTOFF,
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


def _score_column_for_backend(backend: str) -> str:
    from seo_rank.stats.regression import SIMILARITY_SCORE_COLUMNS

    try:
        return SIMILARITY_SCORE_COLUMNS[backend]
    except KeyError as exc:
        raise ValueError(f"unsupported backend {backend}") from exc


def _finite_float(value: object) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (np.floating, float, int, np.integer)):
        return _finite_float(value)
    return value.item() if hasattr(value, "item") else value
