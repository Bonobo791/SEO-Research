from seo_rank.similarity import compute_page_similarity_features


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
