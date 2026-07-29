"""Rank-depth filtering helpers for Phase 5 confirmatory slices."""
# SEO Research — SEO Factors Research Tool
# Copyright (C) 2026 Andrew Philip Weilbacher
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md


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
