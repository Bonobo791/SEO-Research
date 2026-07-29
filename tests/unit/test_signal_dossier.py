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


import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from seo_rank.stats.signal_dossier import (
    DOSSIER_CANDIDATE_COLUMNS,
    CHAR_DENSITY_COLUMN,
    build_signal_factor_report,
    derive_char_density,
    incremental_ols_ladder,
    leave_one_keyword_out,
    load_dossier_panel,
    negative_control_permutation,
    ndcg_at_k_for_signals,
    partial_correlation_block,
    subset_retests,
    keyword_holdout_split,
    time_split_overlap,
)


def _analysis_mart_rows(*, n_keywords: int = 5, n_ranks: int = 4) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, n_keywords + 1):
        target_keyword_id = f"kw-{keyword_index}"
        for serp_rank in range(1, n_ranks + 1):
            page_text_length = 200 + serp_rank * 50 + keyword_index
            signal = float(n_ranks + 1 - serp_rank) + keyword_index * 0.01
            rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": f"keyword {keyword_index}",
                    "keyword_order": keyword_index,
                    "source_response_id": f"resp-{keyword_index}",
                    "serp_item_id": f"serp-{keyword_index}-{serp_rank}",
                    "page_id": f"page-{keyword_index}-{serp_rank}",
                    "response_id": f"page-resp-{keyword_index}-{serp_rank}",
                    "canonical_url_hash": f"url-{keyword_index}-{serp_rank}",
                    "url": f"https://example.com/{keyword_index}/{serp_rank}",
                    "serp_rank": serp_rank,
                    "title": f"title-{keyword_index}-{serp_rank}",
                    "description": f"description-{keyword_index}-{serp_rank}",
                    "page_text_length": page_text_length,
                    "referring_domains_count": 10 + serp_rank,
                    "deprecated_html_tags": serp_rank % 2 == 0,
                    "meta_keywords_to_content_consistency": 0.1 + serp_rank * 0.05,
                    "time_to_first_byte_ms": 100 + serp_rank,
                    "site_scale": keyword_index * 0.1 + serp_rank * 0.01,
                    "authority_proxy": ((keyword_index * 5 + serp_rank * 13) % 11) * 0.01,
                    "bge_raw_score": signal,
                    "bge_normalized_score": signal,
                    "gemini_doc_retrieval_raw_score": signal - 0.1,
                    "gemini_doc_retrieval_normalized_score": signal - 0.1,
                    "gemini_semantic_similarity_raw_score": signal - 0.2,
                    "gemini_semantic_similarity_normalized_score": signal - 0.2,
                    "schema_version": "analysis_mart.v8",
                }
            )
    return rows


def _textrazor_metrics_rows(*, n_keywords: int = 5, n_ranks: int = 4) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, n_keywords + 1):
        for serp_rank in range(1, n_ranks + 1):
            page_text_length = 200 + serp_rank * 50 + keyword_index
            word_count = max(10, page_text_length // 10)
            unique_count = int(n_ranks + 1 - serp_rank) + keyword_index
            mention_count = unique_count + 1
            rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": f"kw-{keyword_index}",
                    "target_keyword": f"keyword {keyword_index}",
                    "response_id": f"page-resp-{keyword_index}-{serp_rank}",
                    "canonical_url_hash": f"url-{keyword_index}-{serp_rank}",
                    "url": f"https://example.com/{keyword_index}/{serp_rank}",
                    "page_metrics_row_id": f"metrics-{keyword_index}-{serp_rank}",
                    "textrazor_entity_confidence_score": float(n_ranks + 1 - serp_rank),
                    "textrazor_entity_relevance_score": float(n_ranks + 1 - serp_rank) * 0.1,
                    "textrazor_entailment_score": float(n_ranks + 1 - serp_rank) * 0.05,
                    "textrazor_relation_count": int(serp_rank + 1),
                    "textrazor_property_count": int(serp_rank),
                    "textrazor_word_count": word_count,
                    "textrazor_entity_mention_count": mention_count,
                    "textrazor_unique_entity_count": unique_count,
                    "textrazor_unique_entity_density_per_1k_words": unique_count * 1000.0 / word_count,
                    "textrazor_entity_mention_density_per_1k_words": mention_count * 1000.0 / word_count,
                    "schema_version": "curated.v1",
                }
            )
    return rows


def _write_dossier_run(tmp_path: Path, *, n_keywords: int = 5, n_ranks: int = 4) -> Path:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)
    (run_dir / "parquet" / "textrazor_page_metrics").mkdir(parents=True)
    pl.DataFrame(_analysis_mart_rows(n_keywords=n_keywords, n_ranks=n_ranks)).write_parquet(
        run_dir / "parquet" / "analysis_mart" / "part-0.parquet"
    )
    pl.DataFrame(_textrazor_metrics_rows(n_keywords=n_keywords, n_ranks=n_ranks)).write_parquet(
        run_dir / "parquet" / "textrazor_page_metrics" / "part-0.parquet"
    )
    return run_dir


def test_derive_char_density_from_unique_count_and_page_text_length() -> None:
    frame = pl.DataFrame(
        {
            "textrazor_unique_entity_count": [2, 4, None],
            "page_text_length": [1000, 0, 500],
        }
    )
    derived = derive_char_density(frame)
    values = derived[CHAR_DENSITY_COLUMN].to_list()
    assert values[0] == pytest.approx(2.0)
    assert values[1] is None
    assert values[2] is None


def test_load_dossier_panel_joins_registry_columns_and_derives_char_density(
    tmp_path: Path,
) -> None:
    run_dir = _write_dossier_run(tmp_path)
    panel, rank_depth, limitations, _ = load_dossier_panel(run_dir, rank_depth="top_20")

    assert rank_depth == "top_20"
    assert CHAR_DENSITY_COLUMN in panel.columns
    for column in DOSSIER_CANDIDATE_COLUMNS:
        assert column in panel.columns
    assert panel.height == 20
    assert panel[CHAR_DENSITY_COLUMN].drop_nulls().len() == panel.height
    assert "observational_only" in limitations or any(
        "observational" in value.lower() for value in limitations.values()
    )


def test_build_signal_factor_report_json_envelope(tmp_path: Path) -> None:
    run_dir = _write_dossier_run(tmp_path)
    panel, rank_depth, limitations, spec = load_dossier_panel(run_dir, rank_depth="top_20")
    report = build_signal_factor_report(
        panel,
        run_id=run_dir.name,
        rank_depth=rank_depth,
        limitations=limitations,
        spec=spec,
    )

    assert report["status"] == "exploratory"
    assert report["run_id"] == "run-1"
    assert report["rank_depth"] == "top_20"
    assert "candidates" in report
    assert "density" in report
    assert "limitations" in report
    assert "no_causal_claims" in report["limitations"] or any(
        "causal" in str(value).lower() for value in report["limitations"].values()
    )
    density = report["density"]
    assert CHAR_DENSITY_COLUMN in density["columns"]
    assert "word_vs_char_denominator" in density["notes"]
    json.dumps(report)


def test_ndcg_at_k_higher_for_rank_aligned_signal(tmp_path: Path) -> None:
    run_dir = _write_dossier_run(tmp_path)
    panel, _, _, _ = load_dossier_panel(run_dir, rank_depth="top_20")
    ndcg = ndcg_at_k_for_signals(panel, columns=("textrazor_unique_entity_count",), k=3)
    entry = ndcg["signals"]["textrazor_unique_entity_count"]
    assert entry["macro_mean"] is not None
    assert entry["macro_mean"] > 0.7


def test_incremental_ladder_length_proxy_collapses_after_length_step() -> None:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 6):
        for serp_rank in range(1, 5):
            # Length scrambled vs rank so length step does not absorb rank signal.
            length = 100 * (((serp_rank * 3) + keyword_index) % 5 + 1)
            unique = 5 - serp_rank
            rows.append(
                {
                    "target_keyword_id": f"kw-{keyword_index}",
                    "serp_rank": serp_rank,
                    "page_text_length": length,
                    "site_scale": 0.1 * keyword_index,
                    "authority_proxy": 0.2 * keyword_index,
                    # Weak BGE (keyword-only) so density can retain rank signal after BGE.
                    "bge_normalized_score": 0.05 * keyword_index,
                    "textrazor_unique_entity_count": length,
                    "textrazor_unique_entity_density_per_1k_words": float(unique),
                }
            )
    panel = pl.DataFrame(rows)
    ladder = incremental_ols_ladder(
        panel,
        candidates=(
            "textrazor_unique_entity_count",
            "textrazor_unique_entity_density_per_1k_words",
        ),
    )
    count_rungs = ladder["candidates"]["textrazor_unique_entity_count"]["rungs"]
    density_rungs = ladder["candidates"]["textrazor_unique_entity_density_per_1k_words"]["rungs"]
    count_after_bge = count_rungs["plus_candidate"]["delta_adj_r2_vs_previous"]
    density_after_bge = density_rungs["plus_candidate"]["delta_adj_r2_vs_previous"]
    assert count_after_bge is not None
    assert density_after_bge is not None
    assert density_after_bge > count_after_bge
    assert ladder["candidates"]["textrazor_unique_entity_count"]["proxy_expectation"] == (
        "raw_count"
    )
    assert ladder["candidates"]["textrazor_unique_entity_density_per_1k_words"][
        "proxy_expectation"
    ] == "word_density"


def test_partial_correlation_drops_for_pure_bge_proxy() -> None:
    rows: list[dict[str, object]] = []
    rng = np.random.default_rng(0)
    for keyword_index in range(1, 8):
        for serp_rank in range(1, 5):
            bge = float(5 - serp_rank) + rng.normal(0, 0.01)
            rows.append(
                {
                    "target_keyword_id": f"kw-{keyword_index}",
                    "serp_rank": serp_rank,
                    "page_text_length": 200 + serp_rank,
                    "bge_normalized_score": bge,
                    "textrazor_entity_relevance_score": bge,
                    "textrazor_unique_entity_count": float(5 - serp_rank),
                }
            )
    panel = pl.DataFrame(rows)
    block = partial_correlation_block(
        panel,
        candidates=(
            "textrazor_entity_relevance_score",
            "textrazor_unique_entity_count",
        ),
    )
    proxy_rho = abs(block["candidates"]["textrazor_entity_relevance_score"]["pooled_partial_rho"])
    signal_rho = abs(block["candidates"]["textrazor_unique_entity_count"]["pooled_partial_rho"])
    assert proxy_rho < 0.2
    assert signal_rho > proxy_rho


def test_subset_retests_include_length_similarity_and_deprecated_tag() -> None:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 6):
        for serp_rank in range(1, 5):
            rows.append(
                {
                    "target_keyword_id": f"kw-{keyword_index}",
                    "serp_rank": serp_rank,
                    "page_text_length": 200 + (serp_rank % 2) * 100,
                    "bge_normalized_score": float(5 - serp_rank),
                    "deprecated_html_tags": serp_rank % 2 == 0,
                    "textrazor_unique_entity_count": float(5 - serp_rank),
                }
            )
    panel = pl.DataFrame(rows)
    subsets = subset_retests(panel, candidates=("textrazor_unique_entity_count",))
    assert "same_length" in subsets
    assert "same_similarity" in subsets
    assert "deprecated_html_tags" in subsets


def test_leave_one_keyword_out_surfaces_max_influence_keyword() -> None:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 6):
        for serp_rank in range(1, 5):
            unique = float(serp_rank) if keyword_index == 1 else float(5 - serp_rank)
            rows.append(
                {
                    "target_keyword_id": f"kw-{keyword_index}",
                    "serp_rank": serp_rank,
                    "page_text_length": 200 + serp_rank,
                    "site_scale": 0.1,
                    "authority_proxy": 0.2,
                    "bge_normalized_score": float(5 - serp_rank),
                    "textrazor_unique_entity_count": unique,
                }
            )
    panel = pl.DataFrame(rows)
    loko = leave_one_keyword_out(panel, candidates=("textrazor_unique_entity_count",))
    assert loko["max_influence_keyword_id"] == "kw-1"


def test_negative_control_permutation_near_null() -> None:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 6):
        for serp_rank in range(1, 5):
            rows.append(
                {
                    "target_keyword_id": f"kw-{keyword_index}",
                    "serp_rank": serp_rank,
                    "textrazor_unique_entity_count": float(5 - serp_rank),
                }
            )
    panel = pl.DataFrame(rows)
    controls = negative_control_permutation(
        panel,
        candidates=("textrazor_unique_entity_count",),
        n_permutations=20,
        seed=7,
    )
    entry = controls["candidates"]["textrazor_unique_entity_count"]
    assert abs(entry["permuted_median_spearman"]) < 0.25
    assert abs(entry["observed_median_spearman"]) > abs(entry["permuted_median_spearman"])


def test_keyword_holdout_split_reproducible() -> None:
    keywords = [f"kw-{i}" for i in range(1, 11)]
    split_a = keyword_holdout_split(keywords, holdout_fraction=0.2, seed=42)
    split_b = keyword_holdout_split(keywords, holdout_fraction=0.2, seed=42)
    assert split_a == split_b
    assert len(split_a["holdout"]) == 2
    assert set(split_a["train"]).isdisjoint(split_a["holdout"])


def test_time_split_overlap_skips_without_shared_keywords() -> None:
    panel_a = pl.DataFrame(
        {
            "target_keyword_id": ["kw-1", "kw-2"],
            "serp_rank": [1, 1],
            "textrazor_unique_entity_count": [3.0, 2.0],
        }
    )
    panel_b = pl.DataFrame(
        {
            "target_keyword_id": ["kw-9", "kw-8"],
            "serp_rank": [1, 1],
            "textrazor_unique_entity_count": [3.0, 2.0],
        }
    )
    result = time_split_overlap(panel_a, panel_b, candidates=("textrazor_unique_entity_count",))
    assert result["status"] == "skipped"
    assert "overlap" in result["skip_reason"].lower()
