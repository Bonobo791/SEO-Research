import polars as pl

from seo_rank.data.marts import build_analysis_lazyframe


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
            "gemini_doc_retrieval_raw_score": 1.0,
            "gemini_doc_retrieval_normalized_score": 1.0,
            "gemini_semantic_similarity_raw_score": 0.75,
            "gemini_semantic_similarity_normalized_score": 0.75,
            "schema_version": "analysis_mart.v1",
        }
    ]
