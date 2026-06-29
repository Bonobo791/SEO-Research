from seo_rank.gemini_embeddings import (
    GEMINI_EMBEDDING_DIMENSIONALITY,
    GEMINI_EMBEDDING_MODEL,
    compute_gemini_page_similarity_scores,
    prepare_document,
    prepare_query,
    prepare_semantic_input,
)


def test_compute_gemini_page_similarity_scores_formats_live_inputs() -> None:
    calls: list[dict[str, object]] = []
    pages = [
        {
            "url": "https://example.com/live",
            "title": "Live Result",
            "text": "Technical SEO helps crawlers find pages.",
        }
    ]
    vectors = {
        prepare_query("technical seo"): (1.0, 0.0),
        prepare_document(
            "Technical SEO helps crawlers find pages.",
            title="Live Result",
        ): (1.0, 0.0),
        prepare_semantic_input("technical seo"): (0.0, 1.0),
        prepare_semantic_input("Technical SEO helps crawlers find pages."): (0.0, 1.0),
    }

    def embed_content(
        content: str,
        *,
        api_key: str,
        model: str,
        output_dimensionality: int,
    ) -> tuple[float, ...]:
        calls.append(
            {
                "content": content,
                "api_key": api_key,
                "model": model,
                "output_dimensionality": output_dimensionality,
            }
        )
        return vectors[content]

    scores = compute_gemini_page_similarity_scores(
        "technical seo",
        pages,
        api_key="gemini-secret",
        embed_content=embed_content,
    )

    assert calls == [
        {
            "content": "task: search result | query: technical seo",
            "api_key": "gemini-secret",
            "model": GEMINI_EMBEDDING_MODEL,
            "output_dimensionality": GEMINI_EMBEDDING_DIMENSIONALITY,
        },
        {
            "content": "task: sentence similarity | query: technical seo",
            "api_key": "gemini-secret",
            "model": GEMINI_EMBEDDING_MODEL,
            "output_dimensionality": GEMINI_EMBEDDING_DIMENSIONALITY,
        },
        {
            "content": "title: Live Result | text: Technical SEO helps crawlers find pages.",
            "api_key": "gemini-secret",
            "model": GEMINI_EMBEDDING_MODEL,
            "output_dimensionality": GEMINI_EMBEDDING_DIMENSIONALITY,
        },
        {
            "content": "task: sentence similarity | query: Technical SEO helps crawlers find pages.",
            "api_key": "gemini-secret",
            "model": GEMINI_EMBEDDING_MODEL,
            "output_dimensionality": GEMINI_EMBEDDING_DIMENSIONALITY,
        },
    ]
    assert scores == [
        {
            "url": "https://example.com/live",
            "page_similarity": {
                "bge": {"raw_score": 0.98, "normalized_score": 0.98},
                "gemini_doc_retrieval": {"raw_score": 1.0, "normalized_score": 1.0},
                "gemini_semantic_similarity": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
            },
        }
    ]
