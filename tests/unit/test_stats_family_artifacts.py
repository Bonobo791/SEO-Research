from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from seo_rank.stats.artifacts import run_phase5_stats
from seo_rank.stats.spec import load_analysis_spec


def _combined_analysis_mart_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 11):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        keyword_offset = keyword_index * 0.01
        for serp_rank in range(1, 4):
            signal = float(4 - serp_rank) + keyword_offset
            rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
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
                    "page_text_length": 120 + (keyword_index * 3) + serp_rank,
                    "bge_raw_score": signal,
                    "bge_normalized_score": signal,
                    "gemini_doc_retrieval_raw_score": signal - 0.1,
                    "gemini_doc_retrieval_normalized_score": signal - 0.1,
                    "gemini_semantic_similarity_raw_score": signal - 0.2,
                    "gemini_semantic_similarity_normalized_score": signal - 0.2,
                    "schema_version": "analysis_mart.v1",
                }
            )
    return pl.DataFrame(rows)


def _combined_textrazor_frame() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for keyword_index in range(1, 11):
        target_keyword_id = f"kw-{keyword_index}"
        target_keyword = f"keyword {keyword_index}"
        keyword_offset = keyword_index * 0.01
        for serp_rank in range(1, 4):
            signal = float(4 - serp_rank) + keyword_offset
            rows.append(
                {
                    "run_id": "run-1",
                    "target_keyword_id": target_keyword_id,
                    "target_keyword": target_keyword,
                    "response_id": f"page-resp-{keyword_index}-{serp_rank}",
                    "canonical_url_hash": f"url-{keyword_index}-{serp_rank}",
                    "url": f"https://example.com/{keyword_index}/{serp_rank}",
                    "page_metrics_row_id": f"metrics-{keyword_index}-{serp_rank}",
                    "textrazor_entity_confidence_score": signal + 0.5,
                    "textrazor_entity_relevance_score": signal + 0.4,
                    "textrazor_topic_score": signal + 0.3,
                    "textrazor_category_score": signal + 0.2,
                    "textrazor_classifier_score": signal + 0.1,
                    "textrazor_entailment_score": signal + 0.05,
                    "textrazor_entailment_prior": signal - 0.05,
                    "textrazor_entailment_context": signal - 0.1,
                    "textrazor_word_count": 20 + serp_rank,
                    "textrazor_grammar_count": 2 + serp_rank,
                    "textrazor_sense_count": 1 + serp_rank,
                    "textrazor_spelling_count": 1,
                    "textrazor_relation_count": None,
                    "textrazor_property_count": None,
                    "textrazor_noun_phrase_count": None,
                    "schema_version": "curated.v1",
                }
            )
    return pl.DataFrame(rows)


def test_run_phase5_stats_emits_combined_family_tree_and_keeps_similarity_compatibility(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)
    (run_dir / "parquet" / "textrazor_page_metrics").mkdir(parents=True)

    _combined_analysis_mart_frame().write_parquet(
        run_dir / "parquet" / "analysis_mart" / "part-0.parquet"
    )
    _combined_textrazor_frame().write_parquet(
        run_dir / "parquet" / "textrazor_page_metrics" / "part-0.parquet"
    )

    result = run_phase5_stats(run_dir)

    summary = json.loads((run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8"))
    diagnostics = json.loads(
        (run_dir / "stats" / "stats_diagnostics.json").read_text(encoding="utf-8")
    )
    report = (run_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")
    spec = load_analysis_spec()

    assert result.hard_fail is False
    assert summary["metadata"]["signal_family_order"] == list(spec.signal_family_keys)
    assert summary["spearman"]["backends"]["bge"]["backend"] == "bge"
    assert summary["regression"]["backends"]["bge"]["backend"] == "bge"
    assert summary["plackett_luce"]["backends"]["bge"]["backend"] == "bge"
    assert list(summary["rank_depths"]["top_20"]["families"]) == list(spec.signal_family_keys)

    topic_family = summary["rank_depths"]["top_20"]["families"]["textrazor_topic_score"]
    sparse_family = summary["rank_depths"]["top_20"]["families"][
        "textrazor_relation_property_noun_phrase"
    ]

    assert topic_family["spearman"]["signals"]["textrazor_topic_score"]["status"] == "computed"
    assert topic_family["regression"]["signals"]["textrazor_topic_score"]["status"] == "computed"
    assert topic_family["diagnostics"]["signals"]["textrazor_topic_score"]["status"] == "computed"
    assert topic_family["plackett_luce"]["signals"]["textrazor_topic_score"]["status"] in {
        "computed",
        "unstable",
    }
    assert sparse_family["spearman"]["status"] == "skipped"
    assert sparse_family["regression"]["status"] == "skipped"
    assert sparse_family["diagnostics"]["status"] == "skipped"
    assert sparse_family["plackett_luce"]["status"] == "skipped"

    assert diagnostics["metadata"]["signal_family_order"] == list(spec.signal_family_keys)
    assert diagnostics["rank_depths"]["top_20"]["families"]["textrazor_topic_score"]["diagnostics"][
        "signals"
    ]["textrazor_topic_score"]["status"] == "computed"
    assert "### Families" in report
    assert "#### Family: textrazor_topic_score" in report
    assert "#### Family: textrazor_relation_property_noun_phrase" in report


def test_run_phase5_stats_marks_textrazor_family_blocks_skipped_on_hard_fail(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "parquet" / "analysis_mart").mkdir(parents=True)
    (run_dir / "parquet" / "textrazor_page_metrics").mkdir(parents=True)

    hard_fail_frame = _combined_analysis_mart_frame().with_columns(
        pl.lit(1, dtype=pl.Int64).alias("serp_rank")
    )
    hard_fail_frame.write_parquet(run_dir / "parquet" / "analysis_mart" / "part-0.parquet")
    _combined_textrazor_frame().write_parquet(
        run_dir / "parquet" / "textrazor_page_metrics" / "part-0.parquet"
    )

    result = run_phase5_stats(run_dir)

    summary = json.loads((run_dir / "stats" / "stats_summary.json").read_text(encoding="utf-8"))
    report = (run_dir / "stats" / "stats_report.md").read_text(encoding="utf-8")

    assert result.hard_fail is True
    assert summary["hard_fail"] is True
    assert summary["rank_depths"]["top_20"]["families"]["textrazor_topic_score"]["spearman"][
        "status"
    ] == "skipped"
    assert summary["rank_depths"]["top_20"]["families"]["textrazor_topic_score"]["regression"][
        "status"
    ] == "skipped"
    assert "Confirmatory inference skipped because hard-fail guardrails did not pass." in report
    assert "#### Family: textrazor_topic_score" in report
