from __future__ import annotations

import polars as pl

from seo_rank.stats.spearman import summarize_spearman_families
from seo_rank.stats.spec import load_analysis_spec


def _family_dispatch_frame(
    *,
    family_key: str,
    score_column: str,
    keyword_count: int,
) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, keyword_count + 1):
        keyword_id = f"{family_key}-kw-{keyword_index}"
        keyword = f"{family_key} keyword {keyword_index}"
        for serp_rank in range(1, 4):
            rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": keyword_id,
                    "target_keyword": keyword,
                    "serp_rank": serp_rank,
                    "page_text_length": 100 + serp_rank,
                    "referring_domains_count": 100 + serp_rank,
                    score_column: float(4 - serp_rank),
                }
            )
    return pl.DataFrame(rows)


def test_summarize_spearman_families_scopes_bh_within_each_family() -> None:
    spec = load_analysis_spec()
    family_frames = {
        "analysis_mart": _family_dispatch_frame(
            family_key="bge",
            score_column="bge_normalized_score",
            keyword_count=10,
        ),
        "textrazor_page_metrics": _family_dispatch_frame(
            family_key="textrazor_topic_score",
            score_column="textrazor_topic_score",
            keyword_count=9,
        ),
    }

    summary = summarize_spearman_families(
        family_frames,
        registry=spec.signal_families,
    )

    assert summary["families"]["bge"]["bh_q_values"] == [0.0] * 10
    assert summary["families"]["textrazor_topic_score"]["bh_skipped_reason"] == "underpowered"
