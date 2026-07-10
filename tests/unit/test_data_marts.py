import polars as pl

from seo_rank.data.marts import ANALYSIS_SCHEMA_VERSION, build_analysis_lazyframe


def test_build_analysis_lazyframe_lives_in_marts_module() -> None:
    feature_frames = {
        "keyword_serp": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "keyword_order": 1,
                    "source_response_id": "resp-keywords",
                    "serp_item_id": "serp-1",
                    "canonical_url_hash": "url-1",
                    "url": "https://example.com/technical-seo/1",
                    "serp_rank": 1,
                    "title": "Example",
                    "description": "Example description",
                    "schema_version": "feature_marts.v1",
                }
            ]
        ).lazy(),
        "page_features": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "page_id": "page-1",
                    "response_id": "resp-page",
                    "canonical_url_hash": "url-1",
                    "url": "https://example.com/technical-seo/1",
                    "title": "Example",
                    "page_text_length": 120,
                    "bge_raw_score": 0.98,
                    "bge_normalized_score": 0.98,
                    "gemini_doc_retrieval_raw_score": 1.0,
                    "gemini_doc_retrieval_normalized_score": 1.0,
                    "gemini_semantic_similarity_raw_score": 0.75,
                    "gemini_semantic_similarity_normalized_score": 0.75,
                    "schema_version": "feature_marts.v1",
                }
            ]
        ).lazy(),
    }

    analysis_frame = build_analysis_lazyframe(feature_frames)

    assert isinstance(analysis_frame, pl.LazyFrame)
    assert analysis_frame.collect().to_dicts() == [
        {
            "run_id": "run-1",
            "target_keyword_id": "kw-1",
            "target_keyword": "technical seo",
            "keyword_order": 1,
            "source_response_id": "resp-keywords",
            "serp_item_id": "serp-1",
            "page_id": "page-1",
            "response_id": "resp-page",
            "canonical_url_hash": "url-1",
            "url": "https://example.com/technical-seo/1",
            "serp_rank": 1,
            "title": "Example",
            "description": "Example description",
            "page_text_length": 120,
            "bge_raw_score": 0.98,
            "bge_normalized_score": 0.98,
            "bge_rank": 1,
            "bge_pct": 0.0,
            "bge_z": None,
            "gemini_doc_retrieval_raw_score": 1.0,
            "gemini_doc_retrieval_normalized_score": 1.0,
            "gemini_doc_retrieval_rank": 1,
            "gemini_doc_retrieval_pct": 0.0,
            "gemini_doc_retrieval_z": None,
            "gemini_semantic_similarity_raw_score": 0.75,
            "gemini_semantic_similarity_normalized_score": 0.75,
            "gemini_semantic_similarity_rank": 1,
            "gemini_semantic_similarity_pct": 0.0,
            "gemini_semantic_similarity_z": None,
                "deprecated_html_tags": None,
                "meta_keywords_to_content_consistency": None,
                "time_to_first_byte_ms": None,
                "site_scale": None,
                "schema_version": ANALYSIS_SCHEMA_VERSION,
        }
    ]


def test_build_analysis_lazyframe_joins_meta_keyword_control() -> None:
    feature_frames = {
        "keyword_serp": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "keyword_order": 1,
                    "source_response_id": "resp-keywords",
                    "serp_item_id": "serp-1",
                    "canonical_url_hash": "url-1",
                    "url": "https://example.com/technical-seo/1",
                    "serp_rank": 1,
                    "title": "Example",
                    "description": "Example description",
                    "schema_version": "feature_marts.v1",
                }
            ]
        ).lazy(),
        "page_features": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "page_id": "page-1",
                    "response_id": "resp-page",
                    "canonical_url_hash": "url-1",
                    "url": "https://example.com/technical-seo/1",
                    "title": "Example",
                    "page_text_length": 120,
                    "bge_raw_score": 0.98,
                    "bge_normalized_score": 0.98,
                    "gemini_doc_retrieval_raw_score": 1.0,
                    "gemini_doc_retrieval_normalized_score": 1.0,
                    "gemini_semantic_similarity_raw_score": 0.75,
                    "gemini_semantic_similarity_normalized_score": 0.75,
                    "schema_version": "feature_marts.v1",
                }
            ]
        ).lazy(),
        "onpage_signals": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "canonical_url_hash": "url-1",
                    "url": "https://example.com/technical-seo/1",
                    "deprecated_html_tags": False,
                    "meta_keywords_to_content_consistency": 0.25,
                    "time_to_first_byte_ms": 180,
                }
            ]
        ).lazy(),
    }

    result = build_analysis_lazyframe(feature_frames).collect()

    assert result["deprecated_html_tags"].to_list() == [False]
    assert result["meta_keywords_to_content_consistency"].to_list() == [0.25]
    assert result.schema["meta_keywords_to_content_consistency"] == pl.Float64
    assert result["time_to_first_byte_ms"].to_list() == [180]
    assert result.schema["time_to_first_byte_ms"] == pl.Int64


def test_build_analysis_lazyframe_joins_site_scale_from_domain_features() -> None:
    feature_frames = {
        "keyword_serp": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "keyword_order": 1,
                    "source_response_id": "resp-keywords",
                    "serp_item_id": "serp-1",
                    "canonical_url_hash": "url-1",
                    "url": "https://example.com/technical-seo/1",
                    "serp_rank": 1,
                    "title": "Example",
                    "description": "Example description",
                    "schema_version": "feature_marts.v1",
                }
            ]
        ).lazy(),
        "page_features": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "page_id": "page-1",
                    "response_id": "resp-page",
                    "canonical_url_hash": "url-1",
                    "url": "https://example.com/technical-seo/1",
                    "title": "Example",
                    "page_text_length": 120,
                    "bge_raw_score": 0.98,
                    "bge_normalized_score": 0.98,
                    "gemini_doc_retrieval_raw_score": 1.0,
                    "gemini_doc_retrieval_normalized_score": 1.0,
                    "gemini_semantic_similarity_raw_score": 0.75,
                    "gemini_semantic_similarity_normalized_score": 0.75,
                    "schema_version": "feature_marts.v1",
                }
            ]
        ).lazy(),
        "domain_features": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "domain": "example.com",
                    "site_scale": 1.25,
                }
            ]
        ).lazy(),
    }

    result = build_analysis_lazyframe(feature_frames).collect()

    assert result["site_scale"].to_list() == [1.25]
    assert result.schema["site_scale"] == pl.Float64


def test_build_analysis_lazyframe_ranks_within_keyword() -> None:
    feature_frames = {
        "keyword_serp": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "keyword_order": 1,
                    "source_response_id": "resp-keywords",
                    "serp_item_id": f"serp-{i}",
                    "canonical_url_hash": f"url-{i}",
                    "url": f"https://example.com/{i}",
                    "serp_rank": i,
                    "title": f"Page {i}",
                    "description": f"Description {i}",
                    "schema_version": "feature_marts.v1",
                }
                for i in range(1, 4)
            ]
        ).lazy(),
        "page_features": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "page_id": f"page-{i}",
                    "response_id": f"resp-page-{i}",
                    "canonical_url_hash": f"url-{i}",
                    "url": f"https://example.com/{i}",
                    "title": f"Page {i}",
                    "page_text_length": 100 * i,
                    "bge_raw_score": score,
                    "bge_normalized_score": score,
                    "gemini_doc_retrieval_raw_score": score,
                    "gemini_doc_retrieval_normalized_score": score,
                    "gemini_semantic_similarity_raw_score": score,
                    "gemini_semantic_similarity_normalized_score": score,
                    "schema_version": "feature_marts.v1",
                }
                for i, score in [(1, 0.9), (2, 0.7), (3, 0.5)]
            ],
            schema_overrides={"page_text_length": pl.UInt32},
        ).lazy(),
    }

    result = build_analysis_lazyframe(feature_frames).collect()

    ranks = result["bge_rank"].to_list()
    pcts = result["bge_pct"].to_list()
    zscores = result["bge_z"].to_list()

    assert ranks == [1, 2, 3]
    assert pcts == [0.0, 0.5, 1.0]
    assert zscores[0] is not None
    assert zscores[1] is not None
    assert zscores[2] is not None

    mean_z = sum(z for z in zscores if z is not None) / 3
    assert abs(mean_z) < 0.01

    for suffix in (
        "bge",
        "gemini_doc_retrieval",
        "gemini_semantic_similarity",
    ):
        assert f"{suffix}_rank" in result.columns
        assert f"{suffix}_pct" in result.columns
        assert f"{suffix}_z" in result.columns


def test_build_analysis_lazyframe_schema_version_is_v7() -> None:
    feature_frames = {
        "keyword_serp": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "keyword_order": 1,
                    "source_response_id": "resp-keywords",
                    "serp_item_id": "serp-1",
                    "canonical_url_hash": "url-1",
                    "url": "https://example.com/1",
                    "serp_rank": 1,
                    "title": "Page",
                    "description": "Desc",
                    "schema_version": "feature_marts.v1",
                }
            ]
        ).lazy(),
        "page_features": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "page_id": "page-1",
                    "response_id": "resp-page-1",
                    "canonical_url_hash": "url-1",
                    "url": "https://example.com/1",
                    "title": "Page",
                    "page_text_length": 100,
                    "bge_raw_score": 0.9,
                    "bge_normalized_score": 0.9,
                    "gemini_doc_retrieval_raw_score": 0.8,
                    "gemini_doc_retrieval_normalized_score": 0.8,
                    "gemini_semantic_similarity_raw_score": 0.7,
                    "gemini_semantic_similarity_normalized_score": 0.7,
                    "schema_version": "feature_marts.v1",
                }
            ],
            schema_overrides={"page_text_length": pl.UInt32},
        ).lazy(),
    }

    result = build_analysis_lazyframe(feature_frames).collect()
    assert result["schema_version"][0] == "analysis_mart.v7"


def test_build_analysis_lazyframe_tied_scores_rank_by_serp_rank() -> None:
    """Tied scores must rank deterministically by serp_rank, not physical row order."""
    feature_frames = {
        "keyword_serp": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "keyword_order": 1,
                    "source_response_id": "resp-keywords",
                    "serp_item_id": f"serp-{i}",
                    "canonical_url_hash": f"url-{i}",
                    "url": f"https://example.com/{i}",
                    "serp_rank": serp_rank,
                    "title": f"Page {i}",
                    "description": f"Description {i}",
                    "schema_version": "feature_marts.v1",
                }
                for i, serp_rank in [(1, 3), (2, 1), (3, 2)]
            ]
        ).lazy(),
        "page_features": pl.DataFrame(
            [
                {
                    "run_id": "run-1",
                    "target_keyword_id": "kw-1",
                    "target_keyword": "technical seo",
                    "page_id": f"page-{i}",
                    "response_id": f"resp-page-{i}",
                    "canonical_url_hash": f"url-{i}",
                    "url": f"https://example.com/{i}",
                    "title": f"Page {i}",
                    "page_text_length": 100,
                    "bge_raw_score": 0.8,
                    "bge_normalized_score": 0.8,
                    "gemini_doc_retrieval_raw_score": 0.8,
                    "gemini_doc_retrieval_normalized_score": 0.8,
                    "gemini_semantic_similarity_raw_score": 0.8,
                    "gemini_semantic_similarity_normalized_score": 0.8,
                    "schema_version": "feature_marts.v1",
                }
                for i in range(1, 4)
            ],
            schema_overrides={"page_text_length": pl.UInt32},
        ).lazy(),
    }

    result = build_analysis_lazyframe(feature_frames).collect()

    ranks = result["bge_rank"].to_list()
    serp_ranks = result["serp_rank"].to_list()

    assert ranks == [1, 2, 3]
    assert serp_ranks == [1, 2, 3]
