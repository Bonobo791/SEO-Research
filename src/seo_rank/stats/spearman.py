"""Phase 5 Spearman inference helpers."""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence

import numpy as np
import polars as pl
from scipy.stats import spearmanr

from seo_rank.stats.bh import adjust_p_values
from seo_rank.stats.rank_depth import filter_panel_by_max_rank
from seo_rank.stats.spec import AnalysisSpec


logger = logging.getLogger(__name__)

BACKEND_SCORE_COLUMNS = {
    "bge": "bge_normalized_score",
    "gemini_doc_retrieval": "gemini_doc_retrieval_normalized_score",
    "gemini_semantic_similarity": "gemini_semantic_similarity_normalized_score",
}


def summarize_backend_spearman(
    panel: pl.DataFrame,
    *,
    backend: str,
) -> dict[str, object]:
    """Summarize keyword-level Spearman tests for one backend."""

    score_column = BACKEND_SCORE_COLUMNS[backend]
    backend_panel = panel.filter(pl.col(score_column).is_not_null())
    keyword_tests = compute_keyword_spearman_tests(
        backend_panel,
        score_column=score_column,
    )
    rho_values = [float(test["rho"]) for test in keyword_tests]
    summary: dict[str, object] = {
        "backend": backend,
        "score_column": score_column,
        "keyword_count": len(keyword_tests),
        "keyword_tests": keyword_tests,
        "median_rho": float(np.median(rho_values)) if rho_values else 0.0,
        "rho_iqr": float(np.subtract(*np.percentile(rho_values, [75, 25])))
        if rho_values
        else 0.0,
        "fraction_same_sign": _fraction_same_sign(rho_values),
    }
    if len(keyword_tests) >= 10:
        q_values = adjust_p_values([float(test["p_value"]) for test in keyword_tests])
        for test, q_value in zip(keyword_tests, q_values, strict=True):
            test["bh_q_value"] = q_value
        summary["bh_q_values"] = q_values
        bh_status = "applied"
    else:
        summary["bh_skipped_reason"] = "underpowered"
        bh_status = "skipped"
    logger.info(
        "spearman backend=%s keyword_count=%d median_rho=%.4f bh=%s",
        backend,
        len(keyword_tests),
        summary["median_rho"],
        bh_status,
    )
    return summary


def summarize_spearman_backends(
    panel: pl.DataFrame,
    backend_order: Sequence[str],
) -> dict[str, object]:
    """Summarize Spearman tests for every backend in order."""

    logger.info("summarizing spearman backends=%s", list(backend_order))
    return {
        "backend_order": list(backend_order),
        "backends": {
            backend: summarize_backend_spearman(panel, backend=backend)
            for backend in backend_order
        },
    }


def summarize_spearman_rank_depths(
    panel: pl.DataFrame,
    backend_order: Sequence[str],
    *,
    depth_order: Sequence[str],
    spec: AnalysisSpec,
) -> dict[str, object]:
    """Summarize Spearman tests for every confirmatory rank depth."""

    logger.info("summarizing spearman rank_depths=%s", list(depth_order))
    return {
        "depth_order": list(depth_order),
        "depths": {
            depth_key: summarize_spearman_backends(
                filter_panel_by_max_rank(
                    panel,
                    max_rank=spec.rank_depth_limit(depth_key),
                ),
                backend_order,
            )
            for depth_key in depth_order
        },
    }


def compute_keyword_spearman_tests(
    panel: pl.DataFrame,
    *,
    score_column: str,
) -> list[dict[str, object]]:
    """Compute keyword-level Spearman tests for the given score column."""

    tests: list[dict[str, object]] = []
    for keyword_id, keyword_frame in _iter_keyword_frames(panel):
        paired = keyword_frame.select(["target_keyword", "serp_rank", score_column]).drop_nulls(
            ["serp_rank", score_column]
        )
        if paired.height < 2:
            continue
        scores = paired.get_column(score_column).to_list()
        ranks = paired.get_column("serp_rank").to_list()
        rho, p_value = spearmanr(scores, ranks)
        if rho is None or math.isnan(float(rho)):
            rho = 0.0
        if p_value is None or math.isnan(float(p_value)):
            p_value = 1.0
        tests.append(
            {
                "target_keyword_id": keyword_id,
                "target_keyword": paired.get_column("target_keyword")[0],
                "n_rows": paired.height,
                "rho": float(rho),
                "p_value": float(p_value),
            }
        )
    return tests


def _iter_keyword_frames(panel: pl.DataFrame) -> list[tuple[str, pl.DataFrame]]:
    keyword_frames: list[tuple[str, pl.DataFrame]] = []
    if panel.is_empty():
        return keyword_frames
    for keyword_frame in panel.sort("target_keyword_id").partition_by(
        "target_keyword_id",
        maintain_order=True,
    ):
        keyword_id = str(keyword_frame.get_column("target_keyword_id")[0])
        keyword_frames.append((keyword_id, keyword_frame))
    return keyword_frames


def _fraction_same_sign(rho_values: Sequence[float]) -> float:
    if not rho_values:
        return 0.0
    median_sign = _sign(float(np.median(rho_values)))
    if median_sign == 0:
        return float(sum(1 for rho in rho_values if rho == 0.0) / len(rho_values))
    return float(
        sum(1 for rho in rho_values if _sign(rho) == median_sign)
        / len(rho_values)
    )


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0
