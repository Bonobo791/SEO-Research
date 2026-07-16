"""Live Gemini embedding helpers for page-level similarity scoring."""

import hashlib
import logging
import math
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Callable

from seo_rank.dataforseo import cache_identity_url
from seo_rank.similarity import fixture_bge_reranker_score

Vector = tuple[float, ...]
GEMINI_EMBEDDING_MODEL = "gemini-embedding-2"
GEMINI_EMBEDDING_DIMENSIONALITY = 3072
LOGGER = logging.getLogger("seo_rank.gemini_embeddings")


class GeminiEmbeddingError(RuntimeError):
    """Raised when live Gemini embeddings cannot be produced."""


GeminiEmbeddingIdentity = tuple[str, str, str, str, str, int]


@dataclass(frozen=True)
class GeminiEmbeddingRequest:
    role: str
    content: str
    target_keyword: str | None = None
    url: str | None = None

    def identity(self) -> GeminiEmbeddingIdentity:
        return gemini_embedding_identity(
            role=self.role,
            target_keyword=self.target_keyword,
            url=self.url,
            input_sha256=hashlib.sha256(self.content.encode("utf-8")).hexdigest(),
            model=GEMINI_EMBEDDING_MODEL,
            output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
        )

    def metadata(self) -> dict[str, object | None]:
        return {
            "role": self.role,
            "target_keyword": self.target_keyword,
            "url": self.url,
            "input_sha256": self.identity()[3],
            "model": GEMINI_EMBEDDING_MODEL,
            "output_dimensionality": GEMINI_EMBEDDING_DIMENSIONALITY,
        }


def gemini_embedding_identity(
    *,
    role: str,
    target_keyword: str | None,
    url: str | None,
    input_sha256: str,
    model: str,
    output_dimensionality: int,
) -> GeminiEmbeddingIdentity:
    return (
        role,
        (target_keyword or "").casefold().strip(),
        cache_identity_url(url) if url else "",
        input_sha256,
        model,
        output_dimensionality,
    )


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
    embed_response=None,
    on_page_progress=None,
    stored_responses: MutableMapping[
        GeminiEmbeddingIdentity, Mapping[str, object]
    ] | None = None,
    on_embedding_response=None,
) -> list[dict[str, object]]:
    if embed_response is None:
        embed_response = default_embed_response
    if stored_responses is None:
        stored_responses = {}

    if on_page_progress is not None:
        on_page_progress(0, len(pages), "", "query vectors")

    retrieval_query_vector, _ = _resolve_embedding(
        GeminiEmbeddingRequest(
            role="retrieval_query",
            content=prepare_query(keyword),
            target_keyword=keyword,
        ),
        api_key=api_key,
        embed_response=embed_response,
        stored_responses=stored_responses,
        on_embedding_response=on_embedding_response,
    )
    semantic_query_vector, _ = _resolve_embedding(
        GeminiEmbeddingRequest(
            role="semantic_query",
            content=prepare_semantic_input(keyword),
            target_keyword=keyword,
        ),
        api_key=api_key,
        embed_response=embed_response,
        stored_responses=stored_responses,
        on_embedding_response=on_embedding_response,
    )

    scores: list[dict[str, object]] = []
    page_total = len(pages)
    for page_index, page in enumerate(pages, start=1):
        url = page.get("url")
        text = page.get("text")
        if not isinstance(url, str) or not isinstance(text, str):
            continue
        title = page.get("title")
        if not isinstance(title, str):
            title = None

        retrieval_document_input = prepare_document(text, title=title)
        retrieval_document_vector, document_cache_hit = _resolve_embedding(
            GeminiEmbeddingRequest(
                role="retrieval_document",
                content=retrieval_document_input,
                url=url,
            ),
            api_key=api_key,
            embed_response=embed_response,
            stored_responses=stored_responses,
            on_embedding_response=on_embedding_response,
        )
        if on_page_progress is not None:
            on_page_progress(
                page_index,
                page_total,
                url,
                "doc retrieval stored" if document_cache_hit else "doc retrieval embed",
            )
        semantic_page_input = prepare_semantic_input(text)
        semantic_page_vector, semantic_cache_hit = _resolve_embedding(
            GeminiEmbeddingRequest(
                role="semantic_page",
                content=semantic_page_input,
                url=url,
            ),
            api_key=api_key,
            embed_response=embed_response,
            stored_responses=stored_responses,
            on_embedding_response=on_embedding_response,
        )
        if on_page_progress is not None:
            on_page_progress(
                page_index,
                page_total,
                url,
                "semantic stored" if semantic_cache_hit else "semantic embed",
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


def _resolve_embedding(
    request: GeminiEmbeddingRequest,
    *,
    api_key: str,
    embed_response,
    stored_responses: MutableMapping[
        GeminiEmbeddingIdentity, Mapping[str, object]
    ],
    on_embedding_response,
) -> tuple[Vector, bool]:
    identity = request.identity()
    payload = stored_responses.get(identity)
    cache_hit = payload is not None
    if payload is None:
        response = embed_response(
            request.content,
            api_key=api_key,
            model=GEMINI_EMBEDDING_MODEL,
            output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
        )
        payload = embedding_response_payload(response)
        stored_responses[identity] = payload
        if on_embedding_response is not None:
            on_embedding_response(request, payload)
    return to_vector(embedding_values_from_payload(payload)), cache_hit


def embedding_response_payload(response: object) -> dict[str, object]:
    if isinstance(response, Mapping):
        return dict(response)
    to_json_dict = getattr(response, "to_json_dict", None)
    if not callable(to_json_dict):
        raise GeminiEmbeddingError("Gemini embedding response is not serializable")
    payload = to_json_dict()
    if not isinstance(payload, Mapping):
        raise GeminiEmbeddingError("Gemini embedding response is not a JSON object")
    return dict(payload)


def embedding_values_from_payload(payload: Mapping[str, object]) -> Sequence[float]:
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings:
        raise GeminiEmbeddingError("Gemini embedding response did not include vectors")
    embedding = embeddings[0]
    if not isinstance(embedding, Mapping):
        raise GeminiEmbeddingError("Gemini embedding response contained invalid values")
    values = embedding.get("values")
    if not isinstance(values, list):
        raise GeminiEmbeddingError("Gemini embedding response contained invalid values")
    return values


def _embedding_values_from_response(response: object) -> Sequence[float]:
    embeddings = getattr(response, "embeddings", None)
    if not embeddings:
        raise GeminiEmbeddingError("Gemini embedding response did not include vectors")
    values = getattr(embeddings[0], "values", None)
    if values is None:
        raise GeminiEmbeddingError("Gemini embedding response contained invalid values")
    return values


def default_embed_response(
    content: str,
    *,
    api_key: str,
    model: str,
    output_dimensionality: int,
) -> object:
    try:
        from google import genai
        from google.genai.types import EmbedContentConfig
    except ImportError as error:
        raise GeminiEmbeddingError(
            "Live Gemini scoring requires the optional dependency "
            "'google-genai'. Install with: pip install -e '.[similarity,dev]'"
        ) from error

    client = genai.Client(vertexai=False, api_key=api_key)
    return client.models.embed_content(
        model=model,
        contents=content,
        config=EmbedContentConfig(output_dimensionality=output_dimensionality),
    )


def default_embed_content(
    content: str,
    *,
    api_key: str,
    model: str,
    output_dimensionality: int,
) -> Sequence[float]:
    response = default_embed_response(
        content,
        api_key=api_key,
        model=model,
        output_dimensionality=output_dimensionality,
    )
    return _embedding_values_from_response(response)


def build_live_embed_content(api_key: str) -> Callable[..., Sequence[float]]:
    from google import genai
    from google.genai.types import EmbedContentConfig

    client = genai.Client(vertexai=False, api_key=api_key)

    def embed_content(
        content: str,
        *,
        api_key: str,
        model: str,
        output_dimensionality: int,
    ) -> Sequence[float]:
        if api_key != client.models._api_client.api_key:
            raise ValueError("embed_content called with an unexpected api key")
        response = client.models.embed_content(
            model=model,
            contents=content,
            config=EmbedContentConfig(output_dimensionality=output_dimensionality),
        )
        return _embedding_values_from_response(response)

    return embed_content


def to_vector(values: Sequence[float]) -> Vector:
    return tuple(float(value) for value in values)


def cosine_similarity(left: Vector, right: Vector) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right))
    return dot / (left_norm * right_norm)
