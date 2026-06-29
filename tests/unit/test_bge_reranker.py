from seo_rank.bge_reranker import (
    BGE_RERANKER_MODEL,
    BgeRerankerError,
    compute_bge_page_similarity_scores,
    load_bge_reranker,
)


def test_load_bge_reranker_requires_gpu() -> None:
    def build_reranker(*args, **kwargs):  # pragma: no cover
        raise AssertionError("reranker should not be built without a GPU")

    try:
        load_bge_reranker(
            build_reranker=build_reranker,
            is_gpu_available=lambda: False,
        )
    except BgeRerankerError as error:
        assert "CUDA GPU" in str(error)
    else:  # pragma: no cover
        raise AssertionError("expected BgeRerankerError")


def test_compute_bge_page_similarity_scores_batches_pairs_and_maps_scores() -> None:
    calls: list[object] = []

    class FakeReranker:
        def compute_score(self, pairs: list[list[str]]) -> list[float]:
            calls.append(pairs)
            return [7.0, -7.0]

    def load_reranker() -> FakeReranker:
        return FakeReranker()

    scores = compute_bge_page_similarity_scores(
        "technical seo",
        [
            {
                "url": "https://example.com/a",
                "text": "Technical SEO helps crawlers find pages.",
            },
            {
                "url": "https://example.com/b",
                "text": "Editorial planning for social campaigns.",
            },
        ],
        load_reranker=load_reranker,
    )

    assert calls == [
        [
            ["technical seo", "Technical SEO helps crawlers find pages."],
            ["technical seo", "Editorial planning for social campaigns."],
        ]
    ]
    assert scores == [
        {
            "url": "https://example.com/a",
            "page_similarity": {
                "bge": {"raw_score": 7.0, "normalized_score": 0.999089}
            },
        },
        {
            "url": "https://example.com/b",
            "page_similarity": {
                "bge": {"raw_score": -7.0, "normalized_score": 0.000911}
            },
        },
    ]


def test_load_bge_reranker_builds_pinned_flagembedding_model() -> None:
    calls: list[dict[str, object]] = []

    def build_reranker(model_name: str, **kwargs):
        calls.append({"model_name": model_name, **kwargs})
        return object()

    load_bge_reranker(
        build_reranker=build_reranker,
        is_gpu_available=lambda: True,
    )

    assert calls == [
        {
            "model_name": BGE_RERANKER_MODEL,
            "use_fp16": True,
            "devices": ["cuda"],
        }
    ]
