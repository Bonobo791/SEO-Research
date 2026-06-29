"""Live Gemini embedding helpers for page-level similarity scoring."""

import math
from collections.abc import Sequence

from seo_rank.similarity import fixture_bge_reranker_score

Vector = tuple[float, ...]
GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
GEMINI_EMBEDDING_DIMENSIONALITY = 3072


class GeminiEmbeddingError(RuntimeError):
    """Raised when live Gemini embeddings cannot be produced."""


def prepare_query(query: str) -> str:
    return f"task: search result | query: {query}"


def prepare_document(content: str, *, title: str | None = None) -> str:
    resolved_title = title or "none"
    return f"title: {resolved_title} | text: {content}"


def prepare_semantic_input(text: str) -> str:
    return f"task: sentence similarity | query: {text}"


def compute_gemini_page_similarity_scores(
    keyword: str,
    pages: Sequence[dict[str, str]],
    *,
    api_key: str,
    embed_content=None,
) -> list[dict[str, object]]:
    if embed_content is None:
        embed_content = default_embed_content

    retrieval_query_vector = to_vector(
        embed_content(
            prepare_query(keyword),
            api_key=api_key,
            model=GEMINI_EMBEDDING_MODEL,
            output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
        )
    )
    semantic_query_vector = to_vector(
        embed_content(
            prepare_semantic_input(keyword),
            api_key=api_key,
            model=GEMINI_EMBEDDING_MODEL,
            output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
        )
    )

    scores: list[dict[str, object]] = []
    for page in pages:
        url = page.get("url")
        text = page.get("text")
        if not isinstance(url, str) or not isinstance(text, str):
            continue
        title = page.get("title")
        if not isinstance(title, str):
            title = None

        retrieval_document_vector = to_vector(
            embed_content(
                prepare_document(text, title=title),
                api_key=api_key,
                model=GEMINI_EMBEDDING_MODEL,
                output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
            )
        )
        semantic_page_vector = to_vector(
            embed_content(
                prepare_semantic_input(text),
                api_key=api_key,
                model=GEMINI_EMBEDDING_MODEL,
                output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
            )
        )

        gemini_doc_retrieval = round(
            cosine_similarity(retrieval_query_vector, retrieval_document_vector),
            6,
        )
        gemini_semantic_similarity = round(
            cosine_similarity(semantic_query_vector, semantic_page_vector),
            6,
        )
        bge_score = round(fixture_bge_reranker_score(keyword, text), 6)
        scores.append(
            {
                "url": url,
                "page_similarity": {
                    "bge": {"raw_score": bge_score, "normalized_score": bge_score},
                    "gemini_doc_retrieval": {
                        "raw_score": gemini_doc_retrieval,
                        "normalized_score": gemini_doc_retrieval,
                    },
                    "gemini_semantic_similarity": {
                        "raw_score": gemini_semantic_similarity,
                        "normalized_score": gemini_semantic_similarity,
                    },
                },
            }
        )
    return scores


def default_embed_content(
    content: str,
    *,
    api_key: str,
    model: str,
    output_dimensionality: int,
) -> Sequence[float]:
    try:
        from google import genai
        from google.genai.types import EmbedContentConfig
    except ImportError as error:
        raise GeminiEmbeddingError(
            "Live Gemini scoring requires the optional dependency "
            "'google-genai'. Install with: pip install -e '.[similarity,dev]'"
        ) from error

    client = genai.Client(api_key=api_key)
    response = client.models.embed_content(
        model=model,
        contents=content,
        config=EmbedContentConfig(output_dimensionality=output_dimensionality),
    )
    embeddings = getattr(response, "embeddings", None)
    if not embeddings:
        raise GeminiEmbeddingError("Gemini embedding response did not include vectors")
    values = getattr(embeddings[0], "values", None)
    if not isinstance(values, Sequence):
        raise GeminiEmbeddingError("Gemini embedding response contained invalid values")
    return values


def to_vector(values: Sequence[float]) -> Vector:
    return tuple(float(value) for value in values)


def cosine_similarity(left: Vector, right: Vector) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right))
    return dot / (left_norm * right_norm)
