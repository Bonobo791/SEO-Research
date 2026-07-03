"""Phase 5 Spearman inference helpers."""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence

import numpy as np
import polars as pl
from scipy.stats import spearmanr

from seo_rank.stats.bh import adjust_p_values
from seo_rank.stats.families import SignalFamily, SignalFamilyRegistry, source_mart_for_family
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
    summary = _summarize_signal_spearman(
        panel,
        score_column=score_column,
        family_key=backend,
    )
    logger.info(
        "spearman backend=%s keyword_count=%d median_rho=%.4f bh=%s",
        backend,
        summary["keyword_count"],
        summary["median_rho"],
        "applied" if "bh_q_values" in summary else "skipped",
    )
    return summary | {"backend": backend}


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


def summarize_spearman_families(
    source_frames: dict[str, pl.DataFrame],
    *,
    registry: SignalFamilyRegistry,
) -> dict[str, object]:
    """Summarize Spearman tests for every family in the registry."""

    return {
        "families": {
            family.key: summarize_spearman_family(
                source_frames,
                family=family,
            )
            for family in registry.families
        }
    }


def summarize_spearman_family(
    source_frames: dict[str, pl.DataFrame],
    *,
    family: SignalFamily,
) -> dict[str, object]:
    """Summarize Spearman tests for one signal family."""

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
    family_tests: list[dict[str, object]] = []
    for signal_column in family.signal_columns:
        summary = _summarize_signal_spearman(
            source_frame,
            score_column=signal_column,
            family_key=family.key,
        )
        signal_summaries[signal_column] = summary
        for test in summary.get("keyword_tests", []):
            family_tests.append(
                {
                    **test,
                    "signal_column": signal_column,
                }
            )

    if not family_tests:
        return {
            "family": family.key,
            "kind": family.kind,
            "source_mart": source_mart,
            "signal_columns": list(family.signal_columns),
            "status": "skipped",
            "skipped_reason": "no_usable_rows",
            "signals": signal_summaries,
            "backends": signal_summaries,
        }

    rho_values = [float(test["rho"]) for test in family_tests]
    summary: dict[str, object] = {
        "family": family.key,
        "kind": family.kind,
        "source_mart": source_mart,
        "signal_columns": list(family.signal_columns),
        "keyword_count": len(family_tests),
        "keyword_tests": family_tests,
        "median_rho": float(np.median(rho_values)) if rho_values else 0.0,
        "rho_iqr": float(np.subtract(*np.percentile(rho_values, [75, 25])))
        if rho_values
        else 0.0,
        "fraction_same_sign": _fraction_same_sign(rho_values),
        "signals": signal_summaries,
        "backends": signal_summaries,
    }
    if len(family_tests) >= 10:
        q_values = adjust_p_values([float(test["p_value"]) for test in family_tests])
        for test, q_value in zip(summary["keyword_tests"], q_values, strict=True):
            test["bh_q_value"] = q_value
        summary["bh_q_values"] = q_values
    else:
        summary["bh_skipped_reason"] = "underpowered"
    return summary


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
        scores_constant = _is_constant_sequence(scores)
        ranks_constant = _is_constant_sequence(ranks)
        if scores_constant or ranks_constant:
            rho = 0.0
            p_value = 1.0
        else:
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


def _summarize_signal_spearman(
    panel: pl.DataFrame,
    *,
    score_column: str,
    family_key: str | None = None,
) -> dict[str, object]:
    if score_column not in panel.columns:
        summary: dict[str, object] = {
            "score_column": score_column,
            "keyword_count": 0,
            "keyword_tests": [],
            "median_rho": 0.0,
            "rho_iqr": 0.0,
            "fraction_same_sign": 0.0,
            "status": "skipped",
            "skipped_reason": "missing_signal_column",
        }
        if family_key is not None:
            summary["family"] = family_key
        return summary
    backend_panel = panel.filter(pl.col(score_column).is_not_null())
    keyword_tests = compute_keyword_spearman_tests(
        backend_panel,
        score_column=score_column,
    )
    rho_values = [float(test["rho"]) for test in keyword_tests]
    summary: dict[str, object] = {
        "score_column": score_column,
        "keyword_count": len(keyword_tests),
        "keyword_tests": keyword_tests,
        "median_rho": float(np.median(rho_values)) if rho_values else 0.0,
        "rho_iqr": float(np.subtract(*np.percentile(rho_values, [75, 25])))
        if rho_values
        else 0.0,
        "fraction_same_sign": _fraction_same_sign(rho_values),
        "status": "computed",
    }
    if family_key is not None:
        summary["family"] = family_key
    if len(keyword_tests) >= 10:
        q_values = adjust_p_values([float(test["p_value"]) for test in keyword_tests])
        for test, q_value in zip(keyword_tests, q_values, strict=True):
            test["bh_q_value"] = q_value
        summary["bh_q_values"] = q_values
    else:
        summary["bh_skipped_reason"] = "underpowered"
        summary["status"] = "skipped"
    return summary


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


def _is_constant_sequence(values: Sequence[object]) -> bool:
    if len(values) <= 1:
        return True
    first = values[0]
    return all(value == first for value in values[1:])
