from __future__ import annotations

import pandas as pd
import pytest

from seo_rank.stats.scale import (
    LOG_LENGTH_Z_COLUMN,
    SIMILARITY_Z_COLUMN,
    global_zscore,
    within_keyword_sd_rms,
    within_keyword_zscore,
)


def test_within_keyword_zscore_centers_and_scales_each_keyword() -> None:
    frame = pd.DataFrame(
        {
            "target_keyword_id": ["a", "a", "a", "b", "b"],
            "score": [1.0, 2.0, 3.0, 10.0, 14.0],
        }
    )

    scaled, dropped = within_keyword_zscore(
        frame,
        "score",
        out_column=SIMILARITY_Z_COLUMN,
    )

    assert dropped == 0
    assert scaled.loc[scaled["target_keyword_id"] == "a", SIMILARITY_Z_COLUMN].tolist() == pytest.approx(
        [-1.0, 0.0, 1.0]
    )
    assert scaled.loc[scaled["target_keyword_id"] == "b", SIMILARITY_Z_COLUMN].tolist() == pytest.approx(
        [-0.7071067811865475, 0.7071067811865475]
    )


def test_within_keyword_zscore_drops_zero_variance_keywords() -> None:
    frame = pd.DataFrame(
        {
            "target_keyword_id": ["flat", "flat", "vary", "vary"],
            "score": [5.0, 5.0, 1.0, 3.0],
        }
    )

    scaled, dropped = within_keyword_zscore(frame, "score", out_column=SIMILARITY_Z_COLUMN)

    assert dropped == 2
    assert scaled["target_keyword_id"].tolist() == ["vary", "vary"]
    assert scaled[SIMILARITY_Z_COLUMN].tolist() == pytest.approx([-0.7071067811865475, 0.7071067811865475])


def test_global_zscore_standardizes_series() -> None:
    series = pd.Series([1.0, 3.0, 5.0])

    scaled = global_zscore(series, out_column=LOG_LENGTH_Z_COLUMN)

    assert scaled.tolist() == pytest.approx([-1.0, 0.0, 1.0])


def test_within_keyword_sd_rms_returns_pooled_within_keyword_spread() -> None:
    frame = pd.DataFrame(
        {
            "target_keyword_id": ["a", "a", "b", "b"],
            "score": [0.0, 0.02, 0.0, 0.04],
        }
    )

    assert within_keyword_sd_rms(frame, "score") == pytest.approx(0.022360679774997897)
