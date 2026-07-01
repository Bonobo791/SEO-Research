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
        "task: sentence similarity | query: best northwest houston realtors": (1.0, 0.0),
        "task: sentence similarity | query: Alpha block": (1.0, 0.0),
        "task: sentence similarity | query: Beta block": (0.0, 1.0),
    }

    def fake_embed_content(content, *, api_key, model, output_dimensionality):
        assert api_key == "gemini-secret"
        assert model == module.GEMINI_EMBEDDING_MODEL
        assert output_dimensionality == module.GEMINI_EMBEDDING_DIMENSIONALITY
        return vectors[content]

    scores = module.compute_semantic_similarity_scores(
        "best northwest houston realtors",
        [
            {"label": "Alpha", "text": "Alpha block"},
            {"label": "Beta", "text": "Beta block"},
        ],
        api_key="gemini-secret",
        embed_content=fake_embed_content,
    )

    assert scores == [
        {"label": "Alpha", "score": 1.0},
        {"label": "Beta", "score": 0.0},
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
