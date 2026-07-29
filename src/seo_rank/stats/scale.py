"""Shared predictor scaling for Phase 5 secondary inference paths."""
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

import pandas as pd

SIMILARITY_Z_COLUMN = "similarity_z"
LOG_LENGTH_Z_COLUMN = "log_page_length_z"


def within_keyword_zscore(
    frame: pd.DataFrame,
    column: str,
    *,
    out_column: str = SIMILARITY_Z_COLUMN,
    keyword_column: str = "target_keyword_id",
) -> tuple[pd.DataFrame, int]:
    """Z-score ``column`` within each keyword; drop keywords with zero variance."""

    scaled_parts: list[pd.DataFrame] = []
    dropped_rows = 0

    for _, keyword_frame in frame.groupby(keyword_column, sort=False):
        values = keyword_frame[column].to_numpy(dtype=float)
        if values.size < 2:
            dropped_rows += int(len(keyword_frame))
            continue
        std = float(keyword_frame[column].std(ddof=1))
        if std <= 0.0:
            dropped_rows += int(len(keyword_frame))
            continue
        part = keyword_frame.copy()
        part[out_column] = (part[column] - part[column].mean()) / std
        scaled_parts.append(part)

    if not scaled_parts:
        empty = frame.iloc[0:0].copy()
        empty[out_column] = pd.Series(dtype=float)
        return empty, dropped_rows

    return pd.concat(scaled_parts, ignore_index=True), dropped_rows


def global_zscore(
    series: pd.Series,
    *,
    out_column: str = LOG_LENGTH_Z_COLUMN,
) -> pd.Series:
    """Z-score a series across all rows."""

    std = float(series.std(ddof=1))
    if std <= 0.0:
        return pd.Series(0.0, index=series.index, name=out_column)
    return ((series - series.mean()) / std).rename(out_column)


def within_keyword_sd_rms(frame: pd.DataFrame, column: str, *, keyword_column: str = "target_keyword_id") -> float:
    """Root-mean-square of per-keyword standard deviations (descriptive metadata)."""

    per_keyword_std = (
        frame.groupby(keyword_column, sort=False)[column]
        .std(ddof=1)
        .dropna()
        .to_numpy(dtype=float)
    )
    if per_keyword_std.size == 0:
        return 0.0
    return float((per_keyword_std**2).mean() ** 0.5)
