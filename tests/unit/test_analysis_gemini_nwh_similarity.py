# SEO Research — SEO Factors Research Tool
# Copyright (C) 2026 Andrew Philip Weilbacher
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Commercial licensing: contact@marketingprowess.simplelogin.com — see COMMERCIAL.md
import importlib.util

import logging
from pathlib import Path

import pytest
from seo_rank.gemini_embeddings import build_live_embed_content as shared_build_live_embed_content
from seo_rank.textrazor import fixture_page_metrics_response


SCRIPT = Path("/var/home/user/PycharmProjects/SEO-Research/analysis/gemini_nwh_similarity.py")
KEYWORD = "northwest houston realtors"
EXTENDED_TEXTRAZOR_STUB = {
    "unique_entity_count": 3,
    "entity_mention_count": 5,
    "entity_confidence_mean": 7.5,
    "entity_confidence_max": 8.0,
    "entity_relevance_mean": 0.9,
    "entity_relevance_max": 0.95,
    "word_count": 120,
    "sentence_count": 8,
    "noun_phrase_count": 4,
    "relation_count": 2,
    "property_count": 1,
    "entailment_count": 1,
    "words_with_spelling_suggestions": 0,
    "language": "en",
    "topics": [{"label": "Real estate", "score": 0.88}],
    "categories": [{"label": "Business", "score": 0.75}],
}


def load_module(*, stub_extended_textrazor: bool = True):
    spec = importlib.util.spec_from_file_location("gemini_nwh_similarity", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if stub_extended_textrazor:
        module._textrazor_extended_metrics = (
            lambda label, text, *, textrazor_api_key: dict(EXTENDED_TEXTRAZOR_STUB)
        )
    return module


def _score_row(label: str, page_similarity: dict[str, object]) -> dict[str, object]:
    return {
        "label": label,
        "page_similarity": page_similarity,
        "textrazor_extended": dict(EXTENDED_TEXTRAZOR_STUB),
    }


def test_compute_semantic_similarity_scores_orders_blocks_by_score() -> None:
    module = load_module()

    vectors = {
        "task: search result | query: northwest houston realtors": (1.0, 0.0),
        "task: sentence similarity | query: northwest houston realtors": (1.0, 0.0),
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

    def fake_textrazor_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        return fixture_page_metrics_response(
            url="https://example.com/alpha",
            text="Alpha block",
        )

    class FakeReranker:
        def compute_score(self, pairs):
            assert pairs == [
                [KEYWORD, "Alpha block"],
                [KEYWORD, "Beta block"],
            ]
            return [0.91, 0.12]

    scores = module.compute_semantic_similarity_scores(
        KEYWORD,
        [
            {"label": "Alpha", "text": "Alpha block"},
            {"label": "Beta", "text": "Beta block"},
        ],
        api_key="gemini-secret",
        textrazor_api_key="textrazor-secret",
        textrazor_transport=fake_textrazor_transport,
        embed_content=fake_embed_content,
        reranker=FakeReranker(),
    )

    assert scores == [
        _score_row(
            "Alpha",
            {
                "bge": {"raw_score": 0.91, "normalized_score": 0.713},
                "gemini_doc_retrieval": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
                "gemini_semantic_similarity": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
                "textrazor_entity_confidence_score": {
                    "raw_score": 7.5,
                    "normalized_score": 7.5,
                },
                "textrazor_entity_relevance_score": {
                    "raw_score": 0.92,
                    "normalized_score": 0.92,
                },
            },
        ),
        _score_row(
            "Beta",
            {
                "bge": {"raw_score": 0.12, "normalized_score": 0.529964},
                "gemini_doc_retrieval": {
                    "raw_score": 0.0,
                    "normalized_score": 0.0,
                },
                "gemini_semantic_similarity": {
                    "raw_score": 0.0,
                    "normalized_score": 0.0,
                },
                "textrazor_entity_confidence_score": {
                    "raw_score": 7.5,
                    "normalized_score": 7.5,
                },
                "textrazor_entity_relevance_score": {
                    "raw_score": 0.92,
                    "normalized_score": 0.92,
                },
            },
        ),
    ]


def test_main_reports_bge_and_gemini_document_relevance(monkeypatch, capsys) -> None:
    module = load_module()

    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    monkeypatch.setenv("TEXTRAZOR_API_KEY", "textrazor-secret")
    monkeypatch.setattr(module, "ensure_project_env_loaded", lambda: None)

    def fake_embed_content(content, *, api_key, model, output_dimensionality):
        assert api_key == "gemini-secret"
        assert model == module.GEMINI_EMBEDDING_MODEL
        assert output_dimensionality == module.GEMINI_EMBEDDING_DIMENSIONALITY
        vectors = {
            "task: search result | query: northwest houston realtors": (1.0, 0.0),
            "task: sentence similarity | query: northwest houston realtors": (1.0, 0.0),
            "title: Michele Harmon Team | text: Alpha block": (1.0, 0.0),
            "task: sentence similarity | query: Alpha block": (1.0, 0.0),
        }
        return vectors[content]

    def fake_compute_semantic_similarity_scores(
        keyword,
        blocks,
        *,
        api_key,
        textrazor_api_key,
        embed_content,
        reranker=None,
        textrazor_transport=None,
    ):
        assert keyword == KEYWORD
        assert api_key == "gemini-secret"
        assert textrazor_api_key == "textrazor-secret"
        assert blocks == [{"label": "Michele Harmon Team", "text": "Alpha block"}]
        assert embed_content is fake_embed_content
        return [
            {
                "label": "Michele Harmon Team",
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
                    "textrazor_entity_confidence_score": {
                        "raw_score": 7.5,
                        "normalized_score": 7.5,
                    },
                    "textrazor_entity_relevance_score": {
                        "raw_score": 0.92,
                        "normalized_score": 0.92,
                    },
                },
                "textrazor_extended": dict(EXTENDED_TEXTRAZOR_STUB),
            }
        ]

    monkeypatch.setattr(module, "build_live_embed_content", lambda api_key: fake_embed_content)
    monkeypatch.setattr(module, "compute_semantic_similarity_scores", fake_compute_semantic_similarity_scores)
    monkeypatch.setattr(
        module,
        "TEXT_BLOCKS",
        [{"label": "Michele Harmon Team", "text": "Alpha block"}],
    )

    assert module.main() == 0

    captured = capsys.readouterr().out
    assert "BGE" in captured
    assert "Gemini document relevance" in captured
    assert "TextRazor entity confidence" in captured
    assert "TextRazor entity relevance" in captured
    assert '"gemini_doc_retrieval"' in captured
    assert '"textrazor_entity_confidence_score"' in captured


def test_analysis_script_reuses_shared_live_embed_builder() -> None:
    module = load_module()

    assert module.build_live_embed_content is shared_build_live_embed_content


def test_compute_semantic_similarity_scores_logs_summary(caplog) -> None:
    module = load_module()

    caplog.set_level(logging.INFO, logger="gemini_nwh_similarity")

    vectors = {
        "task: search result | query: northwest houston realtors": (1.0, 0.0),
        "task: sentence similarity | query: northwest houston realtors": (1.0, 0.0),
        "title: Alpha | text: Alpha block": (1.0, 0.0),
        "task: sentence similarity | query: Alpha block": (1.0, 0.0),
    }

    def fake_embed_content(content, *, api_key, model, output_dimensionality):
        return vectors[content]

    def fake_textrazor_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        return fixture_page_metrics_response(
            url="https://example.com/alpha",
            text="Alpha block",
        )

    class FakeReranker:
        def compute_score(self, pairs):
            return [0.91]

    module.compute_semantic_similarity_scores(
        KEYWORD,
        [{"label": "Alpha", "text": "Alpha block"}],
        api_key="gemini-secret",
        textrazor_api_key="textrazor-secret",
        textrazor_transport=fake_textrazor_transport,
        embed_content=fake_embed_content,
        reranker=FakeReranker(),
    )

    messages = [record.getMessage() for record in caplog.records]
    assert any(f"computing semantic similarity keyword={KEYWORD}" in message for message in messages)
    assert any("requesting textrazor metrics label=Alpha" in message for message in messages)
    assert any("scored block label=Alpha" in message for message in messages)


def test_compute_semantic_similarity_scores_uses_live_textrazor_request() -> None:
    module = load_module()

    vectors = {
        "task: search result | query: northwest houston realtors": (1.0, 0.0),
        "task: sentence similarity | query: northwest houston realtors": (1.0, 0.0),
        "title: Alpha | text: Alpha block": (1.0, 0.0),
        "task: sentence similarity | query: Alpha block": (1.0, 0.0),
    }

    def fake_embed_content(content, *, api_key, model, output_dimensionality):
        assert api_key == "gemini-secret"
        assert model == module.GEMINI_EMBEDDING_MODEL
        assert output_dimensionality == module.GEMINI_EMBEDDING_DIMENSIONALITY
        return vectors[content]

    sent: dict[str, object] = {}

    def fake_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        sent.update(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": body,
                "timeout": timeout,
            }
        )
        return fixture_page_metrics_response(
            url="https://example.com/alpha",
            text="Alpha block",
        )

    class FakeReranker:
        def compute_score(self, pairs):
            return [0.91]

    scores = module.compute_semantic_similarity_scores(
        KEYWORD,
        [{"label": "Alpha", "text": "Alpha block"}],
        api_key="gemini-secret",
        textrazor_api_key="textrazor-secret",
        textrazor_transport=fake_transport,
        embed_content=fake_embed_content,
        reranker=FakeReranker(),
    )

    assert sent["method"] == "POST"
    assert sent["url"] == "https://api.textrazor.com/"
    assert sent["headers"]["X-TextRazor-Key"] == "textrazor-secret"
    assert b"text=Alpha+block" in sent["body"]
    assert sent["timeout"] == 30.0
    assert scores[0]["page_similarity"]["textrazor_entity_confidence_score"] == {
        "raw_score": 7.5,
        "normalized_score": 7.5,
    }
    assert scores[0]["page_similarity"]["textrazor_entity_relevance_score"] == {
        "raw_score": 0.92,
        "normalized_score": 0.92,
    }


def test_compute_semantic_similarity_scores_falls_back_to_fixture_bge_when_live_dependency_missing(
    monkeypatch,
) -> None:
    module = load_module()

    vectors = {
        "task: search result | query: northwest houston realtors": (1.0, 0.0),
        "task: sentence similarity | query: northwest houston realtors": (1.0, 0.0),
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

    def fake_textrazor_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        return fixture_page_metrics_response(
            url="https://example.com/alpha",
            text="Best Northwest Houston Realtors for every home",
        )

    def raise_bge_error():
        raise module.BgeRerankerError("FlagEmbedding is unavailable")

    monkeypatch.setattr(module, "load_bge_reranker", raise_bge_error)
    scores = module.compute_semantic_similarity_scores(
        KEYWORD,
        [{"label": "Alpha", "text": "Best Northwest Houston Realtors for every home"}],
        api_key="gemini-secret",
        textrazor_api_key="textrazor-secret",
        textrazor_transport=fake_textrazor_transport,
        embed_content=fake_embed_content,
    )

    assert scores == [
        _score_row(
            "Alpha",
            {
                "bge": {"raw_score": 0.98, "normalized_score": 0.727108},
                "gemini_doc_retrieval": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
                "gemini_semantic_similarity": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
                "textrazor_entity_confidence_score": {
                    "raw_score": 7.5,
                    "normalized_score": 7.5,
                },
                "textrazor_entity_relevance_score": {
                    "raw_score": 0.92,
                    "normalized_score": 0.92,
                },
            },
        )
    ]


def test_compute_semantic_similarity_scores_falls_back_to_fixture_bge_when_live_loader_raises_unexpected_error(
    monkeypatch,
) -> None:
    module = load_module()

    vectors = {
        "task: search result | query: northwest houston realtors": (1.0, 0.0),
        "task: sentence similarity | query: northwest houston realtors": (1.0, 0.0),
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

    def fake_textrazor_transport(
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, object]:
        return fixture_page_metrics_response(
            url="https://example.com/alpha",
            text="Best Northwest Houston Realtors for every home",
        )

    def raise_unexpected_error():
        raise AttributeError("XLMRobertaTokenizer has no attribute prepare_for_model")

    monkeypatch.setattr(module, "load_bge_reranker", raise_unexpected_error)
    scores = module.compute_semantic_similarity_scores(
        KEYWORD,
        [{"label": "Alpha", "text": "Best Northwest Houston Realtors for every home"}],
        api_key="gemini-secret",
        textrazor_api_key="textrazor-secret",
        textrazor_transport=fake_textrazor_transport,
        embed_content=fake_embed_content,
    )

    assert scores == [
        _score_row(
            "Alpha",
            {
                "bge": {"raw_score": 0.98, "normalized_score": 0.727108},
                "gemini_doc_retrieval": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
                "gemini_semantic_similarity": {
                    "raw_score": 1.0,
                    "normalized_score": 1.0,
                },
                "textrazor_entity_confidence_score": {
                    "raw_score": 7.5,
                    "normalized_score": 7.5,
                },
                "textrazor_entity_relevance_score": {
                    "raw_score": 0.92,
                    "normalized_score": 0.92,
                },
            },
        )
    ]


def test_main_reports_gemini_provider_errors(monkeypatch) -> None:
    module = load_module()

    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")
    monkeypatch.setenv("TEXTRAZOR_API_KEY", "textrazor-secret")
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
