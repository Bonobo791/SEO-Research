import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path("/var/home/user/PycharmProjects/SEO-Research/analysis/gemini_nwh_similarity.py")


def load_module():
    spec = importlib.util.spec_from_file_location("gemini_nwh_similarity", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compute_semantic_similarity_scores_orders_blocks_by_score() -> None:
    module = load_module()

    vectors = {
        "task: search result | query: best northwest houston realtors": (1.0, 0.0),
        "task: sentence similarity | query: best northwest houston realtors": (1.0, 0.0),
        "title: Alpha | text: Alpha block": (1.0, 0.0),
        "task: sentence similarity | query: Alpha block": (1.0, 0.0),
        "title: Beta | text: Beta block": (0.0, 1.0),
        "task: sentence similarity | query: Beta block": (0.0, 1.0),
    }

    def fake_embed_content(content, *, api_key, model, output_dimensionality):
        assert api_key == "gemini-secret"
        assert model == module.GEMINI_EMBEDDING_MODEL
        assert output_dimensionality == module.GEMINI_EMBEDDING_DIMENSIONALITY
        return vectors[content]

    class FakeReranker:
        def compute_score(self, pairs):
            assert pairs == [
                ["best northwest houston realtors", "Alpha block"],
                ["best northwest houston realtors", "Beta block"],
            ]
            return [0.91, 0.12]

    scores = module.compute_semantic_similarity_scores(
        "best northwest houston realtors",
        [
            {"label": "Alpha", "text": "Alpha block"},
            {"label": "Beta", "text": "Beta block"},
        ],
        api_key="gemini-secret",
        embed_content=fake_embed_content,
        reranker=FakeReranker(),
    )

    assert scores == [
        {
            "label": "Alpha",
            "page_similarity": {
                "bge": {"raw_score": 0.91, "normalized_score": 0.713},
                "gemini_doc_retrieval": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
                "gemini_semantic_similarity": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
            },
        },
        {
            "label": "Beta",
            "page_similarity": {
                "bge": {"raw_score": 0.12, "normalized_score": 0.529964},
                "gemini_doc_retrieval": {
                    "raw_score": 0.0,
                    "normalized_score": 0.0,
                },
                "gemini_semantic_similarity": {
                    "raw_score": 0.0,
                    "normalized_score": 0.0,
                },
            },
        },
    ]


def test_main_reports_bge_and_gemini_document_relevance(monkeypatch, capsys) -> None:
    module = load_module()

    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    monkeypatch.setattr(module, "ensure_project_env_loaded", lambda: None)

    def fake_embed_content(content, *, api_key, model, output_dimensionality):
        assert api_key == "gemini-secret"
        assert model == module.GEMINI_EMBEDDING_MODEL
        assert output_dimensionality == module.GEMINI_EMBEDDING_DIMENSIONALITY
        vectors = {
            "task: search result | query: best northwest houston realtors": (1.0, 0.0),
            "task: sentence similarity | query: best northwest houston realtors": (1.0, 0.0),
            "title: Michele Harmon Team | text: Alpha block": (1.0, 0.0),
            "task: sentence similarity | query: Alpha block": (1.0, 0.0),
        }
        return vectors[content]

    class FakeReranker:
        def compute_score(self, pairs):
            return [0.91]

    monkeypatch.setattr(module, "build_live_embed_content", lambda api_key: fake_embed_content)
    monkeypatch.setattr(module, "load_bge_reranker", lambda: FakeReranker())
    monkeypatch.setattr(
        module,
        "TEXT_BLOCKS",
        [{"label": "Michele Harmon Team", "text": "Alpha block"}],
    )

    assert module.main() == 0

    captured = capsys.readouterr().out
    assert "BGE" in captured
    assert "Gemini document relevance" in captured
    assert '"gemini_doc_retrieval"' in captured


def test_compute_semantic_similarity_scores_falls_back_to_fixture_bge_when_live_dependency_missing(
    monkeypatch,
) -> None:
    module = load_module()

    vectors = {
        "task: search result | query: best northwest houston realtors": (1.0, 0.0),
        "task: sentence similarity | query: best northwest houston realtors": (1.0, 0.0),
        "title: Alpha | text: Best Northwest Houston Realtors for every home": (1.0, 0.0),
        "task: sentence similarity | query: Best Northwest Houston Realtors for every home": (
            1.0,
            0.0,
        ),
    }

    def fake_embed_content(content, *, api_key, model, output_dimensionality):
        assert api_key == "gemini-secret"
        assert model == module.GEMINI_EMBEDDING_MODEL
        assert output_dimensionality == module.GEMINI_EMBEDDING_DIMENSIONALITY
        return vectors[content]

    def raise_bge_error():
        raise module.BgeRerankerError("FlagEmbedding is unavailable")

    monkeypatch.setattr(module, "load_bge_reranker", raise_bge_error)
    scores = module.compute_semantic_similarity_scores(
        "best northwest houston realtors",
        [{"label": "Alpha", "text": "Best Northwest Houston Realtors for every home"}],
        api_key="gemini-secret",
        embed_content=fake_embed_content,
    )

    assert scores == [
        {
            "label": "Alpha",
            "page_similarity": {
                "bge": {"raw_score": 0.98, "normalized_score": 0.727108},
                "gemini_doc_retrieval": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
                "gemini_semantic_similarity": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
            },
        }
    ]


def test_main_reports_gemini_provider_errors(monkeypatch) -> None:
    module = load_module()

    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    monkeypatch.setattr(module, "ensure_project_env_loaded", lambda: None)

    def build_failing_embed_content(api_key):
        assert api_key == "gemini-secret"

        def embed_content(*args, **kwargs):
            raise RuntimeError(
                "403 PERMISSION_DENIED. Gemini API has not been used in project "
                "248433142617 before or it is disabled. Enable it by visiting "
                "https://console.developers.google.com/apis/api/"
                "generativelanguage.googleapis.com/overview?project=248433142617"
            )

        return embed_content

    monkeypatch.setattr(module, "build_live_embed_content", build_failing_embed_content)

    with pytest.raises(SystemExit) as error:
        module.main()

    message = str(error.value)
    assert "Gemini embedding request failed" in message
    assert "generativelanguage.googleapis.com/overview?project=248433142617" in message
