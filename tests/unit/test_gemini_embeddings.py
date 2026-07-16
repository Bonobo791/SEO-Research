import sys
import types

import pytest

from seo_rank.gemini_embeddings import (
    GEMINI_EMBEDDING_DIMENSIONALITY,
    GEMINI_EMBEDDING_MODEL,
    GeminiEmbeddingError,
    build_live_embed_content,
    default_embed_content,
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

    class FakeEmbeddingResponse:
        def __init__(self, values: tuple[float, ...]) -> None:
            self.values = values

        def to_json_dict(self) -> dict[str, object]:
            return {"embeddings": [{"values": list(self.values)}]}

    def embed_response(
        content: str,
        *,
        api_key: str,
        model: str,
        output_dimensionality: int,
    ) -> FakeEmbeddingResponse:
        calls.append(
            {
                "content": content,
                "api_key": api_key,
                "model": model,
                "output_dimensionality": output_dimensionality,
            }
        )
        return FakeEmbeddingResponse(vectors[content])

    scores = compute_gemini_page_similarity_scores(
        "technical seo",
        pages,
        api_key="gemini-secret",
        embed_response=embed_response,
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


def test_default_embed_content_uses_google_ai_studio_client(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeEmbedding:
        values = [0.25, 0.5, 0.75]

    class FakeEmbedResponse:
        embeddings = [FakeEmbedding()]

    class FakeModels:
        def embed_content(self, *, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config
            return FakeEmbedResponse()

    class FakeClient:
        def __init__(self, *, vertexai: bool, api_key: str) -> None:
            captured["vertexai"] = vertexai
            captured["api_key"] = api_key
            self.models = FakeModels()

    fake_google_module = types.ModuleType("google")
    fake_genai_module = types.ModuleType("google.genai")
    fake_genai_module.Client = FakeClient
    fake_types_module = types.ModuleType("google.genai.types")
    fake_types_module.EmbedContentConfig = lambda **kwargs: kwargs
    fake_google_module.genai = fake_genai_module

    monkeypatch.setitem(sys.modules, "google", fake_google_module)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types_module)

    values = default_embed_content(
        "What is the meaning of life?",
        api_key="gemini-secret",
        model=GEMINI_EMBEDDING_MODEL,
        output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
    )

    assert values == [0.25, 0.5, 0.75]
    assert captured == {
        "vertexai": False,
        "api_key": "gemini-secret",
        "model": GEMINI_EMBEDDING_MODEL,
        "contents": "What is the meaning of life?",
        "config": {"output_dimensionality": GEMINI_EMBEDDING_DIMENSIONALITY},
    }


def test_build_live_embed_content_binds_api_key(monkeypatch) -> None:
    class FakeEmbedding:
        values = [1.0, 2.0, 3.0]

    class FakeEmbedResponse:
        embeddings = [FakeEmbedding()]

    class FakeApiClient:
        api_key = "gemini-secret"

    class FakeModels:
        def __init__(self) -> None:
            self._api_client = FakeApiClient()

        def embed_content(self, *, model, contents, config):
            del model, config
            return FakeEmbedResponse()

    class FakeClient:
        def __init__(self, *, vertexai: bool, api_key: str) -> None:
            assert vertexai is False
            self.models = FakeModels()

    fake_google_module = types.ModuleType("google")
    fake_genai_module = types.ModuleType("google.genai")
    fake_genai_module.Client = FakeClient
    fake_types_module = types.ModuleType("google.genai.types")
    fake_types_module.EmbedContentConfig = lambda **kwargs: kwargs
    fake_google_module.genai = fake_genai_module

    monkeypatch.setitem(sys.modules, "google", fake_google_module)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types_module)

    embed_content = build_live_embed_content("gemini-secret")

    assert embed_content(
        "hello",
        api_key="gemini-secret",
        model=GEMINI_EMBEDDING_MODEL,
        output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
    ) == [1.0, 2.0, 3.0]

    try:
        embed_content(
            "hello",
            api_key="wrong-key",
            model=GEMINI_EMBEDDING_MODEL,
            output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
        )
    except ValueError as error:
        assert str(error) == "embed_content called with an unexpected api key"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected embed_content to reject a mismatched api key")


def test_default_embed_content_rejects_missing_vectors(monkeypatch) -> None:
    class FakeEmbedResponse:
        embeddings = None

    class FakeModels:
        def embed_content(self, *, model, contents, config):
            del model, contents, config
            return FakeEmbedResponse()

    class FakeClient:
        def __init__(self, *, vertexai: bool, api_key: str) -> None:
            del vertexai, api_key
            self.models = FakeModels()

    fake_google_module = types.ModuleType("google")
    fake_genai_module = types.ModuleType("google.genai")
    fake_genai_module.Client = FakeClient
    fake_types_module = types.ModuleType("google.genai.types")
    fake_types_module.EmbedContentConfig = lambda **kwargs: kwargs
    fake_google_module.genai = fake_genai_module

    monkeypatch.setitem(sys.modules, "google", fake_google_module)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types_module)

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        default_embed_content(
            "What is the meaning of life?",
            api_key="gemini-secret",
            model=GEMINI_EMBEDDING_MODEL,
            output_dimensionality=GEMINI_EMBEDDING_DIMENSIONALITY,
        )

    assert "did not include vectors" in str(exc_info.value)
