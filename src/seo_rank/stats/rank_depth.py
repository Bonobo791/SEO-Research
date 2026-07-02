"""Rank-depth filtering helpers for Phase 5 confirmatory slices."""

from __future__ import annotations

import logging

import polars as pl


logger = logging.getLogger(__name__)


def filter_panel_by_max_rank(panel: pl.DataFrame, *, max_rank: int) -> pl.DataFrame:
    """Keep SERP rows with rank between 1 and max_rank inclusive."""

    filtered = panel.filter(pl.col("serp_rank").is_between(1, max_rank, closed="both"))
    logger.debug(
        "filter_panel_by_max_rank max_rank=%d rows=%d -> %d",
        max_rank,
        panel.height,
        filtered.height,
    )
    return filtered
