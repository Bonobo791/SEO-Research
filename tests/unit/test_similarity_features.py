from seo_rank.similarity import (
    compute_page_similarity_features,
    compute_page_similarity_scores,
)


def test_compute_page_similarity_features_aggregates_fixture_embedding_cosines() -> None:
    passages = [
        {
            "url": "https://example.com/a",
            "passage_id": "https://example.com/a#p1",
            "text": "technical seo crawling",
        },
        {
            "url": "https://example.com/a",
            "passage_id": "https://example.com/a#p2",
            "text": "content calendar planning",
        },
        {
            "url": "https://example.com/b",
            "passage_id": "https://example.com/b#p1",
            "text": "index controls canonical tags",
        },
    ]

    features = compute_page_similarity_features("technical seo", passages)

    assert features == [
        {
            "url": "https://example.com/a",
            "passage_count": 2,
            "max_similarity": 1.0,
            "mean_similarity": 0.5,
            "best_passage_id": "https://example.com/a#p1",
        },
        {
            "url": "https://example.com/b",
            "passage_count": 1,
            "max_similarity": 0.707107,
            "mean_similarity": 0.707107,
            "best_passage_id": "https://example.com/b#p1",
        },
    ]


def test_compute_page_similarity_scores_returns_dual_backend_page_scores() -> None:
    pages = [
        {
            "url": "https://example.com/a",
            "text": "Technical SEO and crawling guidance for large sites.",
        },
        {
            "url": "https://example.com/b",
            "text": "Editorial calendar planning and social copy ideas.",
        },
        {
            "url": "https://example.com/c",
            "text": "Index controls and canonical tags for site migrations.",
        },
    ]

    scores = compute_page_similarity_scores("technical seo", pages)

    assert scores == [
        {
            "url": "https://example.com/a",
            "page_similarity": {
                "bge": {"raw_score": 0.98, "normalized_score": 0.98},
                "gemini_doc_retrieval": {"raw_score": 1.0, "normalized_score": 1.0},
                "gemini_semantic_similarity": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
            },
        },
        {
            "url": "https://example.com/b",
            "page_similarity": {
                "bge": {"raw_score": 0.12, "normalized_score": 0.12},
                "gemini_doc_retrieval": {"raw_score": 0.0, "normalized_score": 0.0},
                "gemini_semantic_similarity": {
                    "raw_score": 0.0,
                    "normalized_score": 0.0,
                },
            },
        },
        {
            "url": "https://example.com/c",
            "page_similarity": {
                "bge": {"raw_score": 0.74, "normalized_score": 0.74},
                "gemini_doc_retrieval": {
                    "raw_score": 0.707107,
                    "normalized_score": 0.707107,
                },
                "gemini_semantic_similarity": {
                    "raw_score": 0.6,
                    "normalized_score": 0.6,
                },
            },
        },
    ]
